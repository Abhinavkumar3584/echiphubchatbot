"""eChipHub Assistant - web server.

    uvicorn api:app --host 127.0.0.1 --port 8002        then open http://127.0.0.1:8002

POST /api/chat/stream   {"message": "...", "history": [{"role": "user"|"assistant", "content": "..."}]}
                        Server-Sent Events: status ... token ... done   (used by the chat widget)
POST /api/chat          same input, whole answer as JSON                (used by run.bat's test question)
POST /api/presence      {"id": random tab id, "open": true|false} from the widget while its chat window is open
GET  /api/active        {"chat_open": number of chat windows open right now}
GET  /health            is everything loaded?
GET  /                  test page;  /static/widget.js = the chat bubble for the websites

Privacy: no chats, answers or logs are stored. Only the error type of a failed model call is printed.
Open chat windows are counted from a random id per browser tab, kept in memory only until the chat is closed
(or ACTIVE_WINDOW_SECONDS without a ping): no IP address, name or question is linked to it.
"""
import asyncio
import json
import os
import re
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import embeddings
import guardrails
import llm
import retrieval
import vector_store as vs

STATIC = os.path.join(config.ROOT, "static")
READY = {"ok": False, "detail": "starting", "chunks": 0}


@asynccontextmanager
async def lifespan(app):
    try:
        await asyncio.to_thread(embeddings.warm_up)
        llm.warm_up()
        n = await asyncio.to_thread(vs.count)
        READY.update(ok=n > 0, chunks=n, detail="ready" if n else "knowledge base is empty - run ingest")
    except Exception as e:
        READY.update(ok=False, detail=f"{type(e).__name__}: {e}")
    print(f"[{config.BOT_NAME}] {READY['detail']}", flush=True)
    yield
    vs.close()


app = FastAPI(title=config.BOT_NAME, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"], max_age=3600)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ------------------------------------------------------------------ input (sizes are limited)
class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


class Ping(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{16,32}$")     # random per browser tab, made by the widget
    open: bool = False


# ------------------------------------------------------------------ rate limit (memory only)
_hits = defaultdict(deque)


def client_ip(request: Request):
    # uvicorn runs with --proxy-headers behind Nginx, so this is the visitor's real address
    return request.client.host if request.client else "unknown"


def rate_limit(ip):
    now, q = time.time(), _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= config.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(429, "Too many questions in a minute. Please wait a moment and try again.")
    q.append(now)
    if len(_hits) > 20000:                      # forget old visitors
        for k in [k for k, v in _hits.items() if not v or now - v[-1] > 120]:
            _hits.pop(k, None)


# ------------------------------------------------------------------ open chat windows (memory only)
_open_chats = {}                                # tab id -> last ping time
_pings = defaultdict(deque)                     # per-address ping limit, so the count cannot be inflated


def chat_open_count():
    cut = time.time() - config.ACTIVE_WINDOW_SECONDS
    for k in [k for k, t in _open_chats.items() if t < cut]:
        _open_chats.pop(k, None)
    return len(_open_chats)


def check_ready():
    if not READY["ok"]:
        raise HTTPException(503, f"The assistant is not ready: {READY['detail']}")


# ------------------------------------------------------------------ answer helpers
GREETING = re.compile(r"^\s*(hi+|hello|hey|namaste|good (morning|afternoon|evening)|thanks?|thank you|ok(ay)?|bye)"
                      r"[\s!.?]*$", re.I)
BUSY = "The answer service is busy right now. Please try again in a minute."


def not_found_text():
    return (f"I couldn't find that on the {config.SITE_NAME} websites. I can help with courses, workshops and "
            f"bootcamps, labs, the PDK, events and the community. For anything else, please write to "
            f"{config.SUPPORT_CONTACT}.")


def greeting_text(msg):
    if re.match(r"^\s*(thanks?|thank you)", msg, re.I):
        return f"You're welcome! Ask me anything else about {config.SITE_NAME}."
    if re.match(r"^\s*bye", msg, re.I):
        return "Goodbye! Come back any time."
    return (f"Hello! I'm the {config.BOT_NAME}. Ask me about {config.SITE_NAME} courses, upcoming workshops and "
            f"bootcamps, labs, the PDK or the community.")


def clean_answer(text):
    """Removes source numbers, HTML bits and login-session links the model may copy from the website text."""
    if not text:
        return ""
    text = re.sub(r"\[\s*\d{1,2}\s*\]\([^)]*\)", "", text)
    text = re.sub(r"\[\s*\d{1,2}(?:\s*,\s*\d{1,2})*\s*\]", "", text)
    text = re.sub(r"(?<=\s)\(\d{1,2}\)(?=[.,\s]|$)", "", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<(https?://[^>]+)>", lambda m: "https://echiphub.in" if re.search(
        r"sso\.echiphub\.in|client_data|tab_id|session_code|execution", m.group(1)) else m.group(1), text)
    text = re.sub(r"</?(?:div|span|p|b|i|strong|em)\b[^>]*>", "", text, flags=re.I)
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def source_list(srcs, limit=8):
    return [{"n": n, "title": t, "url": u} for n, t, u in srcs[:limit]]


def guarded(body: ChatIn, ip):
    """Guardrails first: returns (fixed reply or None, found, cleaned body)."""
    g = guardrails.check_request(ip, body.message, [t.model_dump() for t in body.history])
    if g.reply:
        return g.reply, g.found, body
    body = ChatIn(message=g.message, history=g.history)          # personal data masked
    if GREETING.match(body.message):
        return greeting_text(body.message), True, body
    return None, True, body


def history_of(body: ChatIn):
    return [{"role": t.role, "content": t.content[:1500]} for t in body.history][-config.HISTORY_TURNS:]


def messages_for(question, history, hits):
    return ([{"role": "system", "content": llm.system_prompt()}] + history +
            [{"role": "user", "content": llm.user_message(question, retrieval.context_block(hits))}])


# ------------------------------------------------------------------ endpoints
@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    ip, rid = client_ip(request), uuid.uuid4().hex[:12]
    rate_limit(ip)
    fixed, found, body = guarded(body, ip)
    if fixed:
        return {"id": rid, "answer": fixed, "sources": [], "found": found}
    check_ready()
    history = history_of(body)
    question = await llm.standalone_question(body.message[:config.MAX_QUESTION_CHARS], history)
    hits = await asyncio.to_thread(retrieval.search, question)
    if not retrieval.confident(hits):
        return {"id": rid, "answer": not_found_text(), "sources": [], "found": False}
    try:
        answer, _ = await llm.complete(messages_for(question, history, hits))
    except llm.LLMError as e:
        print(f"[llm] {e}", flush=True)
        raise HTTPException(502, BUSY)
    answer = clean_answer(guardrails.check_output(answer, guardrails.context_text(hits)))
    return {"id": rid, "answer": answer, "sources": source_list(retrieval.sources(hits)), "found": True}


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream")
async def chat_stream(body: ChatIn, request: Request):
    """Streams progress steps ("status"), then the answer ("token" pieces), then "done" with the sources."""
    ip, rid = client_ip(request), uuid.uuid4().hex[:12]
    rate_limit(ip)
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

    async def single(text, found):
        yield sse("token", {"t": text})
        yield sse("done", {"id": rid, "sources": [], "found": found})

    fixed, found, body = guarded(body, ip)
    if fixed:
        return StreamingResponse(single(fixed, found), media_type="text/event-stream", headers=headers)
    check_ready()

    async def run():
        history = history_of(body)
        if history and config.REWRITE_FOLLOWUPS:
            yield sse("status", {"step": "understand", "text": "Understanding your question"})
        question = await llm.standalone_question(body.message[:config.MAX_QUESTION_CHARS], history)
        yield sse("status", {"step": "search", "text": f"Searching the {config.SITE_NAME} websites"})
        hits = await asyncio.to_thread(retrieval.search, question)
        if not retrieval.confident(hits):
            async for part in single(not_found_text(), False):
                yield part
            return
        pages = retrieval.sources(hits)
        yield sse("status", {"step": "found", "text": f"Found {len(pages)} reference{'s' if len(pages) != 1 else ''}"})
        yield sse("status", {"step": "write", "text": "Writing the answer"})
        guard = guardrails.StreamGuard(guardrails.context_text(hits))   # links, e-mails, leaks
        try:
            async for piece in llm.stream(messages_for(question, history, hits)):
                safe = guard.feed(piece)
                if safe:
                    yield sse("token", {"t": safe})
                if guard.blocked:
                    break
        except llm.LLMError as e:
            print(f"[llm] {e}", flush=True)
            yield sse("error", {"message": BUSY})
        tail = guard.block_text if guard.blocked else guard.flush()
        if tail:
            yield sse("token", {"t": tail})
        yield sse("done", {"id": rid, "sources": source_list(pages), "found": True})

    return StreamingResponse(run(), media_type="text/event-stream", headers=headers)


@app.post("/api/presence")
async def presence(ping: Ping, request: Request):
    ip, now = client_ip(request), time.time()
    q = _pings[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= 120:                           # one tab pings ~2 times a minute; offices and labs share one address
        raise HTTPException(429, "Too many pings")
    q.append(now)
    if ping.open:
        _open_chats[ping.id] = now
    else:
        _open_chats.pop(ping.id, None)            # chat closed: stops counting at once
    if len(_pings) > 20000:
        for k in [k for k, v in _pings.items() if not v or now - v[-1] > 120]:
            _pings.pop(k, None)
    return {"ok": True}


@app.get("/api/active")
async def active():
    return JSONResponse({"chat_open": chat_open_count()}, headers={"Cache-Control": "no-store"})


@app.get("/health")
async def health():
    return JSONResponse({"ok": READY["ok"], "detail": READY["detail"], "chunks": READY["chunks"],
                         "model": config.LLM_MODEL, "embeddings": config.EMBED_MODEL},
                        status_code=200 if READY["ok"] else 503)


@app.get("/")
async def home():
    return FileResponse(os.path.join(STATIC, "index.html"))