"""Writes one JSON line per question to data/logs/chat-YYYY-MM-DD.jsonl.
Used to find unanswered questions and improve the website/bot. Visitor IPs are stored only as a short hash.
Files older than LOG_DAYS are deleted automatically."""
import glob, hashlib, json, os, threading, time
from datetime import datetime, timezone

import config

_lock = threading.Lock()


def ip_hash(ip):
    return hashlib.sha256(f"echiphub-salt:{ip}".encode()).hexdigest()[:12]


def write(record):
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
        path = os.path.join(config.LOG_DIR, f"chat-{datetime.now():%Y-%m-%d}.jsonl")
        with _lock, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def cleanup():
    cutoff = time.time() - config.LOG_DAYS * 86400
    for p in glob.glob(os.path.join(config.LOG_DIR, "chat-*.jsonl")):
        if os.path.getmtime(p) < cutoff:
            os.remove(p)


def stats(days=7):
    rows = []
    for p in sorted(glob.glob(os.path.join(config.LOG_DIR, "chat-*.jsonl")))[-days:]:
        for line in open(p, encoding="utf-8"):
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    q = [r for r in rows if r.get("type") == "chat"]
    fb = [r for r in rows if r.get("type") == "feedback"]
    unanswered = [r["question"] for r in q if not r.get("confident")][-50:]
    return {"questions": len(q), "not_found": sum(1 for r in q if not r.get("confident")),
            "errors": sum(1 for r in q if r.get("error")),
            "avg_seconds": round(sum(r.get("ms", 0) for r in q) / max(1, len(q)) / 1000, 2),
            "helpful": sum(1 for r in fb if r.get("helpful")), "not_helpful": sum(1 for r in fb if not r.get("helpful")),
            "recent_unanswered_questions": unanswered}
