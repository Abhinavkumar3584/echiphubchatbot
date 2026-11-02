"""Checks that everything is ready, with a clear fix for each problem.   python check_setup.py"""
import glob, importlib, os, sys

OK, BAD, WARN = "  OK   ", "  FIX  ", "  NOTE "
problems = 0


def say(mark, text, fix=""):
    global problems
    print(mark + text + (f"\n         -> {fix}" if fix else ""))
    problems += mark == BAD


print("\nChecking the eChipHub Assistant setup\n")
v = sys.version_info
if (3, 10) <= v[:2] <= (3, 13):
    say(OK, f"Python {v.major}.{v.minor}")
else:
    say(BAD, f"Python {v.major}.{v.minor}", "use Python 3.12:  winget install Python.Python.3.12  then  py -3.12 -m venv .venv")

for mod, pkg in [("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("httpx", "httpx"), ("qdrant_client", "qdrant-client"),
                 ("fastembed", "fastembed"), ("dotenv", "python-dotenv")]:
    try:
        importlib.import_module(mod); say(OK, f"package {pkg}")
    except Exception as e:
        say(BAD, f"package {pkg} missing ({type(e).__name__})", "python -m pip install -r requirements.txt")
if problems:
    sys.exit(f"\n{problems} problem(s). Fix them and run this again.")

import config

if not os.path.exists(os.path.join(config.ROOT, ".env")):
    say(BAD, ".env file missing", "copy .env.example to .env and put your Groq key in it")
if not config.GROQ_API_KEY or not config.GROQ_API_KEY.startswith("gsk_"):
    say(BAD, "GROQ_API_KEY not set in .env", "create a key at https://console.groq.com/keys and add GROQ_API_KEY=gsk_... to .env")
else:
    import httpx
    try:
        r = httpx.get(f"{config.GROQ_BASE_URL}/models", headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"}, timeout=20)
        if r.status_code == 401:
            say(BAD, "Groq says the API key is wrong", "create a new key at https://console.groq.com/keys")
        elif r.status_code == 200:
            ids = {m["id"] for m in r.json().get("data", [])}
            say(OK, "Groq API key works")
            for m in (config.GROQ_MODEL, config.GROQ_FALLBACK_MODEL):
                if m and m not in ids:
                    say(BAD, f"Groq model '{m}' is not available to your account",
                        "set GROQ_MODEL in .env to one of: " + ", ".join(sorted(i for i in ids if "whisper" not in i)[:8]))
                elif m:
                    say(OK, f"Groq model {m}")
        else:
            say(BAD, f"Groq answered HTTP {r.status_code}", r.text[:150])
    except Exception as e:
        say(BAD, f"cannot reach Groq ({type(e).__name__})", "check the internet connection / proxy (HTTPS_PROXY)")

pages = glob.glob(os.path.join(config.PAGES_DIR, "**", "*.json"), recursive=True)
if pages:
    say(OK, f"{len(pages)} clean pages in {config.PAGES_DIR}")
else:
    say(BAD, f"no pages in {config.PAGES_DIR}", "run the extractor:  python extractor/extract.py run")

try:
    import embeddings
    print("         loading the embedding models (the first time this downloads ~70 MB)...")
    embeddings.warm_up()
    say(OK, f"embedding models {config.EMBED_MODEL} + {config.SPARSE_MODEL}")
except Exception as e:
    say(BAD, f"embedding models could not be loaded: {str(e)[:200]}",
        "check the internet connection the first time (models come from huggingface.co)")

try:
    import vector_store as vs
    where = config.QDRANT_URL or config.QDRANT_PATH
    n = vs.count()
    if n:
        say(OK, f"Qdrant ({where}): {n} pieces of text loaded")
    else:
        say(WARN, f"Qdrant ({where}) is empty", "run:  python ingest.py")
    vs.close()
except Exception as e:
    say(BAD, f"Qdrant: {str(e)[:250]}", "if the chatbot is running, stop it first (local mode allows one program at a time)")

print(f"\n{'Everything is ready. Start the chatbot:  uvicorn api:app --port 8000' if not problems else f'{problems} problem(s) - fix them and run this again.'}\n")
