# eChipHub Assistant

A chatbot for the eChipHub websites that answers only from the websites' own text and shows which page each answer came from.

```
 eChipHub websites                                                         visitor
        |                                                                     ^
  1. extractor/   reads + cleans the pages     -> output/pages/*.json         |
  2. ingest.py    BGE + BM25 embeddings        -> Qdrant vector database      |
  3. api.py       question -> search Qdrant -> Groq writes the answer -> chat bubble (static/widget.js)
```

| Part | Tool | Cost |
|---|---|---|
| Reading the websites | Crawl4AI + the cleaning rules in `extractor/rules.py` | free |
| Embeddings | `BAAI/bge-small-en-v1.5` (meaning) + `Qdrant/bm25` (exact words), on your CPU | free |
| Vector database | Qdrant (built-in local database in data/qdrant) | free |
| Answers | Groq `openai/gpt-oss-20b`, falls back to `openai/gpt-oss-120b` | about $0.075 / $0.30 per million tokens in / out |

---

## 1. Setup on your Windows laptop (once)

1. Install Python 3.12 if you don't have it: `winget install Python.Python.3.12`
2. Unzip this folder, for example to `F:\echiphub-assistant`.
3. Double-click **`setup.bat`**. It installs everything and creates the `.env` file.
4. Open `.env` in Notepad and paste your Groq key: `GROQ_API_KEY=gsk_...`
   (create one at https://console.groq.com/keys).

## 2. Build the knowledge and start the bot

| Double-click | What happens | Time |
|---|---|---|
| **`1-extract.bat`** | Asks your Keycloak ID + password, reads all 5 websites, keeps only real pages | 10-20 min |
| **`2-load.bat`** | Turns the pages into embeddings and stores them in Qdrant. The first time it downloads the BGE model (~70 MB) | 1-2 min |
| **`check.bat`** | Checks Python, packages, Groq key, models, pages and database. Every line should say `OK` | 1 min |
| **`3-start.bat`** | Starts the bot and opens http://localhost:8000. Click the green chip at the bottom right | - |

**Already extracted with the earlier `echiphub-extractor`?** Copy its `output` folder into this folder,
then run `1-extract.bat build` (cleans again, no internet) and continue with `2-load.bat`.

After extracting, **delete `output\session.json`**. It works like your password.

## 3. Check the answer quality

Double-click **`test.bat`**. It asks the 23 questions in `golden.csv` and shows:
- whether the right page was found (`OK`, `LOW` or `MISS`) and its rank;
- whether the 3 off-topic questions are refused;
- a suggested value for `MIN_SCORE`.

`test.bat --answers` also asks Groq and checks each answer contains the expected words (costs a few paise).
Add your own real questions to `golden.csv`, especially ones visitors actually ask.

**`MIN_SCORE`** (in `.env`) is the similarity below which the bot says "I couldn't find that" without calling Groq.
- Too high: real questions get "not found".
- Too low: off-topic questions reach Groq. The model still refuses them, so this mainly costs money.

Start with 0.50 and use the value `test.bat` suggests.

## 4. Updating the knowledge

When the websites change: `1-extract.bat` (reads only new pages), then `2-load.bat` (updates only changed pages
and removes deleted ones). Stop `3-start.bat` before `2-load.bat`: the built-in database allows one program at a time.

To change what is kept or removed from the websites, edit `extractor/rules.py` and run `1-extract.bat build`.
Every page and the reason for its group is listed in `output/report/filter_report.csv`.

## 5. Add the chat bubble to websites or test locally

Open http://localhost:8000 directly to test the chatbot.

To embed the chat bubble in any web page, add this line before `</body>`:
```html
<script src="http://localhost:8000/static/widget.js" defer></script>
```
Every website or local host using the bubble must be listed in `ALLOWED_ORIGINS` in `.env` (e.g. `http://localhost:8000,http://127.0.0.1:8000`).

## 6. Settings (`.env`)

| Setting | Default | Meaning |
|---|---|---|
| `GROQ_API_KEY` | - | your Groq key (required) |
| `GROQ_MODEL` / `GROQ_FALLBACK_MODEL` | gpt-oss-20b / gpt-oss-120b | main and backup answer model |
| `REASONING_EFFORT` | low | low = fastest; medium/high = slower, sometimes better |
| `QDRANT_URL` | empty | empty = built-in database in `data/qdrant` (local) |
| `EMBED_MODEL` | BAAI/bge-small-en-v1.5 | `BAAI/bge-base-en-v1.5` is a bit better and 3x slower; `2-load.bat` rebuilds by itself after a change |
| `MIN_SCORE` | 0.50 | see section 3 |
| `TOP_K` | 6 | pieces of website text given to the model per question |
| `ALLOWED_ORIGINS` | eChipHub sites + localhost | websites allowed to use the bubble |
| `RATE_LIMIT_PER_MINUTE` | 12 | questions per visitor per minute |
| `ADMIN_TOKEN` | empty | set a long random text, then open `/admin/stats?token=...` |
| `SUPPORT_CONTACT` | support-edtech@nielit.ac.in | given when the answer is not on the websites |

All settings with comments: `config.py`.

## 7. What the bot does to stay correct and safe

- **Answers only from the website text** and puts a source number after each fact; the bubble links each number to its page.
- **Says "not found"** when nothing similar is found, without calling Groq.
- **Refuses off-topic questions** (general knowledge, homework, coding).
- **Follow-up questions** ("when does it start?") are rewritten into a full question before searching.
- **Website text is treated as data:** instructions hidden in a page are ignored.
- **The Groq key stays on the server.** The bubble only talks to your server.
- **Limits:** questions per minute per visitor, question length, and allowed websites. Login-only pages are not included.
- **Logs** in `data/logs/` hold the questions, the pages found, and answers. Visitor IPs are stored only as a short hash,
  and logs are deleted after 30 days (`LOG_DAYS`). Use `/admin/stats` to see questions the bot could not answer.
  Add those topics to the website or to `golden.csv`.

## 8. Files

| File | Job |
|---|---|
| `extractor/extract.py`, `cleaner.py`, `rules.py` | read and clean the websites |
| `ingest.py` | pages -> pieces of ~220 words along the headings -> embeddings -> Qdrant |
| `embeddings.py` | BGE + BM25 with FastEmbed (ONNX, CPU) |
| `vector_store.py` | Qdrant: storage + hybrid search (meaning + exact words, merged) |
| `retrieval.py` | picks the best pieces (max 3 per page), decides "found / not found" |
| `llm.py` | Groq calls, prompts, fallback model, follow-up rewriting |
| `api.py` | web server: `/api/chat`, `/api/chat/stream`, `/api/feedback`, `/health`, `/admin/stats` |
| `chatlog.py` | question logs and stats |
| `static/widget.js`, `static/index.html` | the chat bubble and the test page |
| `evaluate.py`, `golden.csv` | quality test |
| `check_setup.py` | setup check |

## 9. Problems

| You see | Do this |
|---|---|
| `pip` fails with `getaddrinfo failed` | no internet or a proxy: `set HTTPS_PROXY=http://proxy:port`, then run `setup.bat` again |
| `check.bat`: Groq model not available | put one of the models it lists into `GROQ_MODEL` |
| `2-load.bat`: database is in use | close `3-start.bat` first |
| Embedding model download fails | the first run needs access to huggingface.co |
| The bubble doesn't appear on a website | the website is missing from `ALLOWED_ORIGINS`, or its security policy blocks the script (see section 6) |
| Real questions get "not found" | run `test.bat`, lower `MIN_SCORE`, check the page is in `output/report/filter_report.csv` as Real / useful |
| Answer is wrong or old | the website text is old: update the page, then `1-extract.bat` + `2-load.bat` |
