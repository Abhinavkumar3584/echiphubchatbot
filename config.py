"""All chatbot settings. Change them in the .env file (see .env.example), not here.
Every value below is the default used when .env does not set it."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

try:                                    # .env next to this file (never commit it: it holds your API key)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass


def _env(name, default):
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    if isinstance(default, bool):
        return v.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        return int(v)
    if isinstance(default, float):
        return float(v)
    return v.strip()


# ---------------------------------------------------------------- the bot
BOT_NAME = _env("BOT_NAME", "eChipHub Assistant")
SITE_NAME = _env("SITE_NAME", "eChipHub")
SUPPORT_CONTACT = _env("SUPPORT_CONTACT", "support-edtech@nielit.ac.in")

# ---------------------------------------------------------------- answers: Groq
GROQ_API_KEY = _env("GROQ_API_KEY", "")
GROQ_BASE_URL = _env("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = _env("GROQ_MODEL", "openai/gpt-oss-20b")                  # fast + cheap
GROQ_FALLBACK_MODEL = _env("GROQ_FALLBACK_MODEL", "openai/gpt-oss-120b")  # used if the main one fails
REASONING_EFFORT = _env("REASONING_EFFORT", "low")                    # low | medium | high
TEMPERATURE = _env("TEMPERATURE", 0.2)
MAX_ANSWER_TOKENS = _env("MAX_ANSWER_TOKENS", 1200)                   # includes the model's hidden reasoning
GROQ_TIMEOUT = _env("GROQ_TIMEOUT", 40.0)

# ---------------------------------------------------------------- embeddings (run locally, free)
EMBED_MODEL = _env("EMBED_MODEL", "BAAI/bge-small-en-v1.5")           # 384 numbers per text, fast on CPU
SPARSE_MODEL = _env("SPARSE_MODEL", "Qdrant/bm25")                    # keyword search (names, codes, dates)
QUERY_PREFIX = _env("QUERY_PREFIX", "Represent this sentence for searching relevant passages: ")
MODEL_DIR = _env("MODEL_DIR", os.path.join(ROOT, "data", "models"))

# ---------------------------------------------------------------- vector database: Qdrant
QDRANT_URL = _env("QDRANT_URL", "")            # empty = built-in local database in data/qdrant (no server)
QDRANT_PATH = _env("QDRANT_PATH", os.path.join(ROOT, "data", "qdrant"))
QDRANT_API_KEY = _env("QDRANT_API_KEY", "")
COLLECTION = _env("COLLECTION", "echiphub")

# ---------------------------------------------------------------- knowledge (from the extractor)
PAGES_DIR = _env("PAGES_DIR", os.path.join(ROOT, "output", "pages"))
CHUNK_WORDS = _env("CHUNK_WORDS", 220)          # size of one piece of text
CHUNK_OVERLAP = _env("CHUNK_OVERLAP", 40)       # words repeated between two pieces of a long section
MIN_CHUNK_WORDS = _env("MIN_CHUNK_WORDS", 6)

# ---------------------------------------------------------------- search
TOP_K = _env("TOP_K", 6)                        # pieces of text given to the model
CANDIDATES = _env("CANDIDATES", 30)             # pieces looked at by each search before merging
MAX_PER_PAGE = _env("MAX_PER_PAGE", 3)          # at most this many pieces from one page
MIN_SCORE = _env("MIN_SCORE", 0.50)             # below this similarity: "I don't know" (tune with evaluate.py)
MAX_CONTEXT_CHARS = _env("MAX_CONTEXT_CHARS", 9000)

# ---------------------------------------------------------------- web server
ALLOWED_ORIGINS = [o.strip() for o in _env(
    "ALLOWED_ORIGINS",
    "https://echiphub.in,https://www.echiphub.in,https://events.echiphub.in,"
    "https://edx.echiphub.in,https://community.echiphub.in,https://labs.echiphub.in,http://localhost:8000,http://127.0.0.1:8000"
).split(",") if o.strip()]
RATE_LIMIT_PER_MINUTE = _env("RATE_LIMIT_PER_MINUTE", 12)   # questions per visitor per minute
MAX_QUESTION_CHARS = _env("MAX_QUESTION_CHARS", 500)
HISTORY_TURNS = _env("HISTORY_TURNS", 4)                     # earlier messages used for follow-up questions
TRUST_PROXY = _env("TRUST_PROXY", False)                     # True behind reverse proxy (reads X-Forwarded-For)
CACHE_MINUTES = _env("CACHE_MINUTES", 60)                    # same first question -> same answer, no Groq call
ADMIN_TOKEN = _env("ADMIN_TOKEN", "")                        # for /admin/stats; empty = disabled

# ---------------------------------------------------------------- logs
LOG_DIR = _env("LOG_DIR", os.path.join(ROOT, "data", "logs"))
LOG_DAYS = _env("LOG_DAYS", 30)                              # older log files are deleted
