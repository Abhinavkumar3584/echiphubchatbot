# eChipHub Assistant

RAG chat assistant for the eChipHub websites. A visitor's question is searched in the scraped website text
(local Qdrant, hybrid meaning + keyword search) and answered by **Amazon Nova Lite on Amazon Bedrock** (Asia-Pacific inference profile, called from Mumbai).
Rule-based guardrails check every question and answer. No chats, answers or logs are stored.

## Files

| File | Purpose |
|---|---|
| `api.py` | Web server: `/api/chat/stream` (widget), `/api/chat`, `/health`, test page |
| `guardrails.py` | Input checks (injection, abuse, self-harm, daily limit, personal-data masking) and output checks (links, e-mails, leaks) |
| `llm.py` | Prompt and Amazon Bedrock calls (Converse API, streaming, fallback model) |
| `retrieval.py`, `embeddings.py`, `vector_store.py` | Hybrid search: BGE-small + BM25 in local Qdrant |
| `config.py` | All settings (override in `.env`) |
| `scraper_master.py`, `ingest.py` | Laptop only: scrape the sites, build the knowledge base |
| `eval_rag.py` | Laptop only: checks that search finds the right pages |
| `static/widget.js` | Chat bubble for any website (Shadow DOM) |
| `bat_deploy/*.bat` | Windows scripts that run everything on the server over SSH |
| `iam-policy-bedrock.json` | Least-privilege IAM policy for the Bedrock user |

## First-time setup (Windows laptop, folder `F:\chat`)

1. `copy .env.example .env` and fill in the AWS keys and scraper login.
2. `bat_deploy\setup.bat` - laptop environment, code and settings on the server.
3. Send the AWS keys to the server once (they never go into the .bat files):
   ```powershell
   $ak = (Read-Host "Access key ID").Trim(); $sk = (Read-Host "Secret access key").Trim()
   [IO.File]::WriteAllText("$env:TEMP\aws.txt", "AWS_ACCESS_KEY_ID=$ak`nAWS_SECRET_ACCESS_KEY=$sk`n")
   scp -i "$HOME\.ssh\wp.pem" "$env:TEMP\aws.txt" ubuntu@3.111.220.155:/tmp/aws.txt; Remove-Item "$env:TEMP\aws.txt"
   ssh -i "$HOME\.ssh\wp.pem" ubuntu@3.111.220.155 'cd ~/chatbot && sed -i -E /^AWS_\(ACCESS_KEY_ID\|SECRET_ACCESS_KEY\)=/d .env && cat /tmp/aws.txt >> .env && rm -f /tmp/aws.txt && chmod 600 .env && grep -c ^AWS_ .env'
   ```
   It prints `2`. The access key ID has 20 characters (starts with `AKIA`), the secret 40.
4. `bat_deploy\extract.bat` - scrape the websites into `echiphubdata`.
5. `bat_deploy\ingest.bat` - build the knowledge base and switch the server to it.
6. `bat_deploy\run.bat` - restart and test. Live at https://chat-test.echiphub.in

Later: code change -> `setup.bat` + `run.bat`; website content change -> `extract.bat` + `ingest.bat`.

## Add the chatbot to a website

```html
<script src="https://chat-test.echiphub.in/static/widget.js" async></script>
```
(WordPress: WPCode -> Code Snippets -> Header & Footer -> Footer.) Add the site's origin to `ALLOWED_ORIGINS`.

## Security

- AWS keys only in `.env` (laptop and server, `chmod 600`); IAM user limited to invoking Nova Lite.
- CORS allow-list, 12 questions/minute and 100/day per visitor, input size limits, no API docs exposed.
- Guardrails: prompt injection, abuse, self-harm (Tele-MANAS helpline), personal data masked before Bedrock,
  only eChipHub/NIELIT links and real e-mail addresses in answers.
- Requests go to AWS Mumbai; the `apac.` profile may process them in other Asia-Pacific regions. Nothing about visitors
  or chats is stored, and personal data is masked before any request.