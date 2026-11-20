"""All chatbot settings. Change them in the .env file next to this file (see .env.example), not here.
Every value below is the default used when .env does not set it."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

try:                                    # .env holds the AWS keys: never commit it
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

# ---------------------------------------------------------------- answers: Amazon Bedrock (Converse API)
# Credentials: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in .env (IAM user with Bedrock invoke rights)
AWS_REGION = _env("AWS_REGION", "ap-south-1")                         # Mumbai (apac. profile may use other APAC regions)
LLM_MODEL = _env("LLM_MODEL", "apac.amazon.nova-lite-v1:0")         # Amazon Nova Lite (Asia-Pacific profile)
LLM_FALLBACK_MODEL = _env("LLM_FALLBACK_MODEL", "none")              # a second model to try, or "none"
TEMPERATURE = _env("TEMPERATURE", 0.0)
MAX_ANSWER_TOKENS = _env("MAX_ANSWER_TOKENS", 600)                    # answers are ~80 words
ANSWER_WORDS = _env("ANSWER_WORDS", 80)                               # target answer length in words
LLM_TIMEOUT = _env("LLM_TIMEOUT", 60)                                 # seconds per model call
LLM_MAX_CONCURRENCY = _env("LLM_MAX_CONCURRENCY", 200)                # answers generated at the same time
REWRITE_FOLLOWUPS = _env("REWRITE_FOLLOWUPS", True)                   # follow-ups rewritten by the model

# ---------------------------------------------------------------- embeddings (run locally on the CPU, free)
EMBED_MODEL = _env("EMBED_MODEL", "BAAI/bge-small-en-v1.5")           # meaning
SPARSE_MODEL = _env("SPARSE_MODEL", "Qdrant/bm25")                    # exact words (names, codes, dates)
QUERY_PREFIX = _env("QUERY_PREFIX", "Represent this sentence for searching relevant passages: ")
MODEL_DIR = _env("MODEL_DIR", os.path.join(ROOT, "data", "models"))

# ---------------------------------------------------------------- vector database: Qdrant (local files)
QDRANT_PATH = _env("QDRANT_PATH", os.path.join(ROOT, "data", "qdrant"))
COLLECTION = _env("COLLECTION", "echiphub")

# ---------------------------------------------------------------- knowledge (scraped JSON files)
DATA_DIR = _env("DATA_DIR", os.path.join(ROOT, "echiphubdata"))
CHUNK_WORDS = _env("CHUNK_WORDS", 220)          # size of one piece of text
CHUNK_OVERLAP = _env("CHUNK_OVERLAP", 40)       # words repeated between two pieces of a long section
MIN_CHUNK_WORDS = _env("MIN_CHUNK_WORDS", 6)

# ---------------------------------------------------------------- search
TOP_K = _env("TOP_K", 12)                       # pieces of text given to the model
CANDIDATES = _env("CANDIDATES", 30)             # pieces looked at by each search before merging
MAX_PER_PAGE = _env("MAX_PER_PAGE", 2)          # at most this many pieces from one page
MIN_SCORE = _env("MIN_SCORE", 0.52)             # below this similarity: "not found" (off-topic gate)
MAX_CONTEXT_CHARS = _env("MAX_CONTEXT_CHARS", 6500)

# ---------------------------------------------------------------- web server
ALLOWED_ORIGINS = [o.strip() for o in _env(
    "ALLOWED_ORIGINS",
    "https://echiphub.in,https://www.echiphub.in,https://events.echiphub.in,https://edx.echiphub.in,"
    "https://community.echiphub.in,https://labs.echiphub.in"
).split(",") if o.strip()]
RATE_LIMIT_PER_MINUTE = _env("RATE_LIMIT_PER_MINUTE", 12)   # questions per visitor per minute
MAX_QUESTION_CHARS = _env("MAX_QUESTION_CHARS", 500)
HISTORY_TURNS = _env("HISTORY_TURNS", 4)                     # earlier messages used for follow-up questions
ACTIVE_WINDOW_SECONDS = _env("ACTIVE_WINDOW_SECONDS", 75)    # an open chat counts this long after its last ping