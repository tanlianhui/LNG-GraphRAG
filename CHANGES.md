# Changes

## 2026-04-08 — Transcriptions tab: show character count instead of file size

### What changed

- **`web_app.py`** `get_transcription_files()` — reads each file and counts characters (`len(content)`); returns `char_count` instead of `size`/`size_mb`.
- **`templates/index.html`** — displays `📝 X,XXX chars` instead of `📊 X.XX MB` in the transcription list metadata.

---

## 2026-04-08 — Add 【LNG】2026MAR 食糞者的黃金律法震撼美味 to database

### What changed

- Downloaded, transcribed (Breeze-ASR-25, CPU), and loaded into Neo4j.
- 632 chunks, 210,348 characters, nomic embeddings. Concept generation skipped (no OPENAI_API_KEY).
- Entry added to `VODs/videos.csv` as completed.

---

## 2026-04-08 — boot.sh: auto-start Ollama; fix load_single_to_neo4j WAV path

### What changed

- **`boot.sh`** — added Ollama startup block: checks if already running, starts `ollama serve` if not. Required for nomic embeddings during Neo4j ingestion.
- **`load_single_to_neo4j.py`** — fixed WAV→transcript path: now looks in `./transcriptions/` first (where `simple_asr` writes), falls back to WAV's own directory.

---

## 2026-04-08 — Fix auto-start: add 2-minute delay + survive Docker not-ready

### What changed

- **`lng-graphrag.vbs`** (Startup folder) — added `WScript.Sleep 120000` (2-minute delay) so Docker Desktop has time to fully start before `boot.sh` runs. Previously it fired immediately at login and docker-compose would fail.
- **`boot.sh`** — Docker `compose up -d` failure is now non-fatal (warns and continues). Previously `set -e` caused the whole script to exit when Docker wasn't ready.

---

## 2026-04-08 — Fix boot.sh Docker failure crashing startup

### What changed

- **`boot.sh`** — Docker `compose up -d` failure is now non-fatal. When Docker Desktop isn't running, boot.sh logs a warning and continues to start Flask and the Cloudflare tunnel. Previously, `set -e` caused the script to exit on Docker failure, leaving the site completely unreachable.

---

## 2026-04-08 — Cloudflare Tunnel + boot script + auto-start

### What changed

- **`boot.sh`** — new launch script that starts Docker (Neo4j + MySQL via `docker-compose.yml`), waits 15 s for health, starts `python launch_web.py` (Flask on :5000), then starts the Cloudflare Tunnel.
- **`cloudflared-config.yml`** — tunnel config for `lng-graphrag` (ID: `<your-tunnel-id>`), routing `your-domain.example.com → http://localhost:5000`.
- **`CLAUDE.md`** — project rules (FDD git flow, doc conventions, stack reference).
- **`DEPLOYMENT.md`** — step-by-step setup guide.
- **Windows Startup VBScript** installed at `%APPDATA%\...\Startup\lng-graphrag.vbs` — runs `boot.sh` silently on Windows login.
- Cloudflare DNS CNAME registered: `your-domain.example.com → <tunnel>`.

## 2026-04-08 — Fix launch_web.py Unicode crash on Windows + boot.sh venv fix

- `launch_web.py`: added `sys.stdout.reconfigure(encoding="utf-8")` to avoid cp950 UnicodeEncodeError; removed emoji from print statements.
- `boot.sh`: updated Python lookup to prefer `.venv/Scripts/python` before falling back to system Python.
