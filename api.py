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


def clean_citations(text: str) -> str:
    """Removes citations, converts HTML breaks/bullets to clean markdown, and cleans URLs."""
    if not text:
        return ""
    text = re.sub(r"\[\s*\d{1,2}\s*\]\([^)]*\)", "", text)
    text = re.sub(r"\[\s*\d{1,2}(?:\s*,\s*\d{1,2})*\s*\]", "", text)
    text = re.sub(r"(?<=\s)\(\d{1,2}\)(?=[.,\s]|$)", "", text)
    text = re.sub(r"\[\s*Source:?\s*[^\]]*\]", "", text, flags=re.I)

    # Convert HTML breaks to real newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)

    # Clean up angle-bracket URLs and ugly session tokens
    def _clean_url(m):
        raw = m.group(1).strip()
        if "sso.echiphub.in" in raw or any(k in raw for k in ("client_data", "tab_id", "session_code", "execution")):
            return "[eChipHub Portal](https://echiphub.in)"
        return raw

    text = re.sub(r"<(https?://[^>]+)>", _clean_url, text)

    # Convert bullet characters • to clean markdown bullets
    text = re.sub(r"(?:^|\n)[ \t]*[•●]\s*", r"\n- ", text)
    text = text.replace("• ", "- ").replace("• ", "- ")

    # Strip any follow-up tags or stray HTML tags
    text = re.sub(r"<follow_ups>[\s\S]*?(?:</follow_ups>|$)", "", text, flags=re.I)
    text = re.sub(r"</?(?:div|span|p|b|i|strong|em)\b[^>]*>", "", text, flags=re.I)

    # Spacing cleanup
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def generate_contextual_follow_ups(question: str, answer: str = "", hits: list = None) -> list[str]:
    """Generates smart contextual follow-up questions tailored to the query, answer, and retrieved topics."""
    combined = f"{question} {answer}".lower()
    candidates = []

    # 1. PDK / SCL
    if any(k in combined for k in ("pdk", "scl", "process design kit", "fabrication", "cmos", "node")):
        candidates = [
            "How do I request access to the SCL PDK?",
            "Which EDA tools are supported by the SCL PDK?",
            "Is the SCL PDK available for academic research?",
            "What is the difference between SCL 1.2 µm and 0.8 µm PDKs?"
        ]
    # 2. Workshops / Bootcamps
    elif any(k in combined for k in ("workshop", "bootcamp", "live", "schedule", "registration", "calicut", "jammu", "patna", "tirupati", "ranchi")):
        candidates = [
            "How can I register for the upcoming workshops?",
            "Which NIELIT centres offer live workshops?",
            "What are the eligibility prerequisites for the workshops?",
            "Are the workshops conducted online or in-person?"
        ]
    # 3. ChipCraft / RTL / Courses
    elif any(k in combined for k in ("chipcraft", "rtl", "soc", "course", "edtech", "modules", "curriculum", "signoff")):
        candidates = [
            "What are the prerequisites for ChipCraft?",
            "How do I enroll on the Edtech learning platform?",
            "Is a certificate awarded upon completing the course?",
            "What topics are covered in the RTL bootcamp?"
        ]
    # 4. Virtual Labs / Tools / VM
    elif any(k in combined for k in ("lab", "virtual", "vm", "eda tool", "server", "linux")):
        candidates = [
            "How can I log in to the eChipHub Virtual Labs?",
            "What EDA tools are pre-installed in the virtual labs?",
            "Who should I contact for lab access or credential issues?"
        ]
    # 5. Certificate Verification
    elif any(k in combined for k in ("verify", "verification", "certificate", "portal")):
        candidates = [
            "How do I verify a course certificate?",
            "Where can I find my verification code or ID?",
            "Who should I contact if certificate verification fails?"
        ]
    # 6. Community / Guidelines
    elif any(k in combined for k in ("community", "guideline", "forum", "conduct", "rules", "discussion")):
        candidates = [
            "How can I join the eChipHub community discussions?",
            "Where can I find official announcements and news?",
            "How do I report community guideline issues?"
        ]
    # 7. Events / News
    elif any(k in combined for k in ("event", "news", "hackathon", "contest", "announcement")):
        candidates = [
            "Are there any upcoming hackathons or events?",
            "Where can I read the latest eChipHub news?",
            "How can I participate in upcoming competitions?"
        ]
    else:
        candidates = [
            "Which workshops are coming up?",
            "What is the ChipCraft course?",
            "How do I get access to the PDK?"
        ]

    q_norm = re.sub(r"[^\w\s]", "", question.lower()).strip()
    def is_dup(cand: str) -> bool:
        c_norm = re.sub(r"[^\w\s]", "", cand.lower()).strip()
        if q_norm == c_norm:
            return True
        if len(q_norm) > 15 and (q_norm in c_norm or c_norm in q_norm):
            return True
        return False

    filtered = [c for c in candidates if not is_dup(c)]
    if len(filtered) < 2:
        for fb in ("Which workshops are coming up?", "What is the ChipCraft course?", "How do I get access to the PDK?"):
            if fb not in filtered and not is_dup(fb):
                filtered.append(fb)
            if len(filtered) == 3:
                break
    return filtered[:3]


def extract_follow_ups(raw_answer: str, question: str, hits: list = None) -> tuple[str, list[str]]:
    """Extracts follow-up questions from <follow_ups>...</follow_ups> and provides contextual fallback."""
    follow_ups = []
    m = re.search(r"<follow_ups>([\s\S]*?)(?:</follow_ups>|$)", raw_answer, re.I)
    if m:
        for line in m.group(1).splitlines():
            q = re.sub(r"^[\s\-*•\d.)]+", "", line).strip().strip("\"'")
            if 4 <= len(q) <= 120:
                if not q.endswith("?"):
                    q += "?"
                if q not in follow_ups:
                    follow_ups.append(q)

    q_norm = re.sub(r"[^\w\s]", "", question.lower()).strip()
    def is_dup(cand: str) -> bool:
        c_norm = re.sub(r"[^\w\s]", "", cand.lower()).strip()
        if q_norm == c_norm:
            return True
        if len(q_norm) > 15 and (q_norm in c_norm or c_norm in q_norm):
            return True
        return False

    follow_ups = [q for q in follow_ups if not is_dup(q)]

    if len(follow_ups) < 2:
        fallback = generate_contextual_follow_ups(question, raw_answer, hits)
        for fb in fallback:
            if fb not in follow_ups:
                follow_ups.append(fb)
            if len(follow_ups) >= 3:
                break

    clean_answer = re.sub(r"<follow_ups>[\s\S]*?(?:</follow_ups>|$)", "", raw_answer, flags=re.I).strip()
    return clean_answer, follow_ups[:3]


def cited_sources(answer, srcs, max_sources=8):
    """Builds top unique source pages for the Sources section below the message."""
    if not srcs:
        return []
    used = {int(n) for n in re.findall(r"\[(\d{1,2})\]", answer)}
    if used:
        filtered = [s for s in srcs if s[0] in used]
        if filtered:
            return [{"n": n, "title": t, "url": u} for n, t, u in filtered[:max_sources]]
    return [{"n": n, "title": t, "url": u} for n, t, u in srcs[:max_sources]]


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
    messages.append({"role": "user", "content": llm.user_message(question or msg,
                                                               retrieval.context_block(hits))})
    return msg, question, history, hits, found, messages


def log_chat(*args, **kwargs):
    """Server-side chat persistence is completely disabled."""
    pass


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    ip, t0, rid = client_ip(request), time.time(), uuid.uuid4().hex[:12]
    rate_limit(ip)
    if GREETING.match(body.message):
        fu = generate_contextual_follow_ups(body.message)
        return {"id": rid, "answer": greeting_text(body.message), "sources": [], "found": True, "follow_ups": fu}
    check_ready()
    key = None if body.history else body.message.strip().lower()
    if key and (hit := cache_get(key)):
        log_chat(ip, rid, body.message, body.message, [], True, hit["answer"], t0, cached=True)
        return {**hit, "id": rid}
    msg, question, history, hits, found, messages = await prepare(body)
    if not found:
        log_chat(ip, rid, msg, question, hits, False, "", t0)
        fu = ["Explore available courses?", "Which workshops are coming up?", "How do I contact support?"]
        return {"id": rid, "answer": not_found_text(), "sources": [], "found": False, "follow_ups": fu}
    try:
        answer, model = await llm.complete(messages)
    except llm.LLMError as e:
        log_chat(ip, rid, msg, question, hits, found, "", t0, error=str(e))
        raise HTTPException(502, "The answer service is busy right now. Please try again in a minute.")
    srcs = cited_sources(answer, retrieval.sources(hits))
    clean_ans, follow_ups = extract_follow_ups(answer, msg, hits)
    clean_ans = clean_citations(clean_ans)
    out = {"answer": clean_ans, "sources": srcs, "found": True, "follow_ups": follow_ups}
    if key:
        cache_put(key, out)
    log_chat(ip, rid, msg, question, hits, found, clean_ans, t0, model)
    return {**out, "id": rid}


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream")
async def chat_stream(body: ChatIn, request: Request):
    ip, t0, rid = client_ip(request), time.time(), uuid.uuid4().hex[:12]
    rate_limit(ip)

    async def fixed(answer, found, sources=(), follow_ups=()):
        yield sse("token", {"t": answer})
        yield sse("done", {"id": rid, "sources": list(sources), "found": found, "follow_ups": list(follow_ups)})

    if GREETING.match(body.message):
        fu = generate_contextual_follow_ups(body.message)
        return StreamingResponse(fixed(greeting_text(body.message), True, follow_ups=fu), media_type="text/event-stream")
    check_ready()
    key = None if body.history else body.message.strip().lower()
    if key and (hit := cache_get(key)):
        log_chat(ip, rid, body.message, body.message, [], True, hit["answer"], t0, cached=True)
        fu = hit.get("follow_ups") or generate_contextual_follow_ups(body.message, hit.get("answer", ""))
        return StreamingResponse(fixed(hit["answer"], True, hit.get("sources", []), follow_ups=fu), media_type="text/event-stream")
    msg, question, history, hits, found, messages = await prepare(body)
    if not found:
        log_chat(ip, rid, msg, question, hits, False, "", t0)
        fu = ["Explore available courses?", "Which workshops are coming up?", "How do I contact support?"]
        return StreamingResponse(fixed(not_found_text(), False, follow_ups=fu), media_type="text/event-stream")

    async def run():
        parts, error = [], ""
        try:
            async for piece in llm.stream(messages):
                parts.append(piece)
                yield sse("token", {"t": piece})
        except llm.LLMError as e:
            error = str(e)
            yield sse("error", {"message": "The answer service is busy right now. Please try again in a minute."})
        raw_answer = "".join(parts)
        srcs = cited_sources(raw_answer, retrieval.sources(hits))
        clean_ans, follow_ups = extract_follow_ups(raw_answer, msg, hits)
        clean_ans = clean_citations(clean_ans)
        if clean_ans and not error and key:
            cache_put(key, {"answer": clean_ans, "sources": srcs, "found": True, "follow_ups": follow_ups})
        log_chat(ip, rid, msg, question, hits, found, clean_ans, t0, config.GROQ_MODEL, error)
        yield sse("done", {"id": rid, "sources": srcs, "found": True, "follow_ups": follow_ups})

    return StreamingResponse(run(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/feedback")
async def feedback(body: FeedbackIn, request: Request):
    rate_limit(client_ip(request))
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


@app.get("/api/stats")
async def public_stats():
    s = await asyncio.to_thread(chatlog.stats)
    return {
        "ok": READY.get("ok", False),
        "detail": READY.get("detail", "ready"),
        "chunks": READY.get("chunks", 0),
        "service_status": "Running" if READY.get("ok") else "Offline",
        "vector_db": "Qdrant Vector Engine",
        "vector_db_status": "Healthy" if READY.get("ok") else "Error",
        "llm_model": config.GROQ_MODEL,
        "llm_status": "Connected",
        "embeddings": config.EMBED_MODEL,
        "embeddings_status": "Operational",
        "total_chats": s.get("total_chats", 0),
        "active_users": s.get("active_users", 1),
        "avg_latency": f"{s.get('avg_seconds', 0)}s"
    }


@app.get("/admin/stats")
async def stats(token: str = ""):
    if not config.ADMIN_TOKEN or token != config.ADMIN_TOKEN:
        raise HTTPException(404)
    return await asyncio.to_thread(chatlog.stats)


@app.get("/")
async def home():
    return FileResponse(os.path.join(STATIC, "index.html"))
