"""The chatbot web server.

    uvicorn api:app --port 8000          then open http://localhost:8000

POST /api/chat          {"message": "...", "history": [{"role": "user"|"assistant", "content": "..."}]}
                        -> {"id", "answer", "sources": [{"n", "title", "url"}], "found"}
POST /api/chat/stream   same input, answer streamed as Server-Sent Events: token ... done
POST /api/feedback      {"id": "...", "helpful": true|false, "comment": "..."}
GET  /health            is everything loaded?
GET  /admin/stats?token=ADMIN_TOKEN   questions, not-found questions, feedback (last 7 days)
GET  /                  demo page;  /static/widget.js = the chat bubble for the websites
"""
import asyncio, json, os, re, time, uuid
from collections import OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import chatlog
import config
import embeddings
import llm
import retrieval
import vector_store as vs

STATIC = os.path.join(config.ROOT, "static")
READY = {"ok": False, "detail": "starting"}


@asynccontextmanager
async def lifespan(app):
    chatlog.cleanup()
    try:
        await asyncio.to_thread(embeddings.warm_up)
        n = await asyncio.to_thread(vs.count)
        READY.update(ok=n > 0, chunks=n,
                     detail="ready" if n else "knowledge base is empty - run: python ingest.py")
    except Exception as e:
        READY.update(ok=False, detail=f"{type(e).__name__}: {e}")
    print(f"[{config.BOT_NAME}] {READY['detail']}")
    yield
    vs.close()


app = FastAPI(title=config.BOT_NAME, lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"], max_age=3600)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ------------------------------------------------------------------ input
class Turn(BaseModel):
    role: str
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[Turn] = []


class FeedbackIn(BaseModel):
    id: str = Field(max_length=64)
    helpful: bool
    comment: str = Field("", max_length=1000)


# ------------------------------------------------------------------ protection
_hits = defaultdict(deque)


def client_ip(request: Request):
    if config.TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
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


_cache = OrderedDict()


def cache_get(key):
    v = _cache.get(key)
    if v and time.time() - v[0] < config.CACHE_MINUTES * 60:
        return v[1]
    _cache.pop(key, None)
    return None


def cache_put(key, value):
    _cache[key] = (time.time(), value)
    while len(_cache) > 500:
        _cache.popitem(last=False)


# ------------------------------------------------------------------ the answer
GREETING = re.compile(r"^\s*(hi+|hello|hey|namaste|good (morning|afternoon|evening)|thanks?|thank you|ok(ay)?|bye)"
                      r"[\s!.?]*$", re.I)


def not_found_text():
    return (f"I couldn't find that on the {config.SITE_NAME} websites. I can help with courses, workshops and "
            f"bootcamps, labs, the PDK, events and the community. For anything else, please write to "
            f"{config.SUPPORT_CONTACT}.")


def greeting_text(msg):
    if re.match(r"^\s*(thanks?|thank you)", msg, re.I):
        return "You're welcome! Ask me anything else about eChipHub."
    if re.match(r"^\s*bye", msg, re.I):
        return "Goodbye! Come back any time."
    return (f"Hello! I'm the {config.BOT_NAME}. Ask me about eChipHub courses, upcoming workshops and bootcamps, "
            f"labs, the PDK or the community.")


def cited_sources(answer, srcs):
    used = {int(n) for n in re.findall(r"\[(\d{1,2})\]", answer)}
    return [{"n": n, "title": t, "url": u} for n, t, u in srcs if n in used]


def check_ready():
    """Raises 503 if the database is empty or not reachable. Automatically initializes
    on serverless platforms (like Vercel) where ASGI lifespan may not run."""
    global READY
    if not READY.get("ok"):
        try:
            embeddings.warm_up()
            n = vs.count()
            if n > 0:
                READY.update(ok=True, chunks=n, detail="ready")
            else:
                READY.update(ok=False, chunks=0, detail="knowledge base is empty - run: python ingest.py")
        except Exception as e:
            READY.update(ok=False, detail=f"{type(e).__name__}: {e}")
    if not READY.get("ok"):
        raise HTTPException(503, f"The assistant is not ready: {READY.get('detail')}")


async def prepare(body: ChatIn):
    """Returns (question used for search, hits, found, messages for the model)."""
    msg = body.message.strip()[:config.MAX_QUESTION_CHARS]
    history = [{"role": t.role, "content": t.content[:1500]} for t in body.history
               if t.role in ("user", "assistant")][-config.HISTORY_TURNS:]
    question = await llm.standalone_question(msg, history)
    hits = await asyncio.to_thread(retrieval.search, question)
    found = retrieval.confident(hits)
    messages = [{"role": "system", "content": llm.system_prompt()}]
    messages += history
    messages.append({"role": "user", "content": llm.user_message(msg if not history else
                                                               f"{msg}\n(Full question: {question})",
                                                               retrieval.context_block(hits))})
    return msg, question, history, hits, found, messages


def log_chat(ip, rid, msg, question, hits, found, answer, t0, model="", error="", cached=False):
    chatlog.write({"type": "chat", "id": rid, "visitor": chatlog.ip_hash(ip), "question": msg,
                   "search_question": question if question != msg else "", "confident": found,
                   "top": [{"url": h.url, "sim": round(h.similarity, 3)} for h in hits[:4]],
                   "answer": answer[:2000], "model": model, "cached": cached, "error": error,
                   "ms": int((time.time() - t0) * 1000)})


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    ip, t0, rid = client_ip(request), time.time(), uuid.uuid4().hex[:12]
    rate_limit(ip)
    if GREETING.match(body.message):
        return {"id": rid, "answer": greeting_text(body.message), "sources": [], "found": True}
    check_ready()
    key = None if body.history else body.message.strip().lower()
    if key and (hit := cache_get(key)):
        log_chat(ip, rid, body.message, body.message, [], True, hit["answer"], t0, cached=True)
        return {**hit, "id": rid}
    msg, question, history, hits, found, messages = await prepare(body)
    if not found:
        log_chat(ip, rid, msg, question, hits, False, "", t0)
        return {"id": rid, "answer": not_found_text(), "sources": [], "found": False}
    try:
        answer, model = await llm.complete(messages)
    except llm.LLMError as e:
        log_chat(ip, rid, msg, question, hits, found, "", t0, error=str(e))
        raise HTTPException(502, "The answer service is busy right now. Please try again in a minute.")
    out = {"answer": answer, "sources": cited_sources(answer, retrieval.sources(hits)), "found": True}
    if key:
        cache_put(key, out)
    log_chat(ip, rid, msg, question, hits, found, answer, t0, model)
    return {**out, "id": rid}


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream")
async def chat_stream(body: ChatIn, request: Request):
    ip, t0, rid = client_ip(request), time.time(), uuid.uuid4().hex[:12]
    rate_limit(ip)

    async def fixed(answer, found, sources=()):
        yield sse("token", {"t": answer})
        yield sse("done", {"id": rid, "sources": list(sources), "found": found})

    if GREETING.match(body.message):
        return StreamingResponse(fixed(greeting_text(body.message), True), media_type="text/event-stream")
    check_ready()
    key = None if body.history else body.message.strip().lower()
    if key and (hit := cache_get(key)):
        log_chat(ip, rid, body.message, body.message, [], True, hit["answer"], t0, cached=True)
        return StreamingResponse(fixed(hit["answer"], True, hit["sources"]), media_type="text/event-stream")
    msg, question, history, hits, found, messages = await prepare(body)
    if not found:
        log_chat(ip, rid, msg, question, hits, False, "", t0)
        return StreamingResponse(fixed(not_found_text(), False), media_type="text/event-stream")

    async def run():
        parts, error = [], ""
        try:
            async for piece in llm.stream(messages):
                parts.append(piece)
                yield sse("token", {"t": piece})
        except llm.LLMError as e:
            error = str(e)
            yield sse("error", {"message": "The answer service is busy right now. Please try again in a minute."})
        answer = "".join(parts)
        srcs = cited_sources(answer, retrieval.sources(hits))
        if answer and not error and key:
            cache_put(key, {"answer": answer, "sources": srcs, "found": True})
        log_chat(ip, rid, msg, question, hits, found, answer, t0, config.GROQ_MODEL, error)
        yield sse("done", {"id": rid, "sources": srcs, "found": True})

    return StreamingResponse(run(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/feedback")
async def feedback(body: FeedbackIn, request: Request):
    rate_limit(client_ip(request))
    chatlog.write({"type": "feedback", "id": body.id, "helpful": body.helpful, "comment": body.comment[:1000]})
    return {"ok": True}


@app.get("/health")
async def health():
    try:
        check_ready()
    except HTTPException:
        pass
    return JSONResponse({"ok": READY.get("ok", False), "detail": READY.get("detail"),
                         "chunks": READY.get("chunks", 0), "model": config.GROQ_MODEL,
                         "embeddings": config.EMBED_MODEL}, status_code=200 if READY.get("ok") else 503)


@app.get("/admin/stats")
async def stats(token: str = ""):
    if not config.ADMIN_TOKEN or token != config.ADMIN_TOKEN:
        raise HTTPException(404)
    return await asyncio.to_thread(chatlog.stats)


@app.get("/")
async def home():
    return FileResponse(os.path.join(STATIC, "index.html"))
