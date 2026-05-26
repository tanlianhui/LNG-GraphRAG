# Changes

## 2026-05-26 — Scheduler: daily 8 AM dry-run check with service health gates

- **`scheduler.py`** — rewritten. Changed from 6-hour full-pipeline runs to a daily 08:00 dry-run check.
  - Checks Docker containers (`lng-neo4j`, `lng-mysql`, `lng-adminer`) are running before proceeding.
  - Checks Ollama health (`/api/tags`) before proceeding; aborts if Ollama is down.
  - Runs `fetch_new_vods.py --dry-run` — lists any new videos found but does **not** download or process them. User reviews the list and decides on whitelist status.
  - Also runs a health check on startup (boot validation).
  - Removed `FETCH_INTERVAL_HOURS` env var (no longer relevant).

---

## 2026-05-25 — Ingest 【LNG】2026APR and 【LNG】2026MAY (with embeddings)

- **`【LNG】2026APR 反正都會變成大便 時間到了就換下一位`** — 608 chunks + nomic embeddings loaded into Neo4j.
- **`【LNG】2026MAY 哪有嬰兒天天哭 哪有嘟狗天天輸 嘟狗不盧`** — WAV downloaded, ASR (111 chunks), 458 chunks + nomic embeddings loaded into Neo4j.
- Both entries in `VODs/videos.csv` with status `completed`.
- Ollama port changed to 11700 (`OLLAMA_HOST=http://0.0.0.0:11700`) — port 11434 is in Windows excluded range on this machine. Fixed in `boot.sh` and propagated via env to all child processes.

---

## 2026-05-24 — fetch_new_vods: --limit flag + CSV None-key bug fix

- **`fetch_new_vods.py`** — added `--limit N` argument; caps how many new videos are processed per run (0 = all, default). Useful for one-off backfills without triggering full batch.
- **`VODs/download_from_youtube.py`** — fixed `update_csv_status`: filtered `None` from fieldnames, strip `None` keys from rows, added `extrasaction='ignore'` to DictWriter. Bug manifested when `append_to_csv` wrote a 4-column row (with `upload_date`) to a 3-column CSV header, causing DictReader to map the 4th field to key `None`. Also replaced `⚠️` emoji in error print with ASCII `[WARN]` to avoid `UnicodeEncodeError` on cp950 terminals.
- **Scheduler** — already wired into `boot.sh` (`scheduler.py` runs every 6 h by default, configurable via `FETCH_INTERVAL_HOURS` in `.env`). No change needed; daily-or-better check is guaranteed on `bash boot.sh`.

---

## 2026-04-28 — ASR keyword biasing and transcription post-processing

- **`asr_keywords.py`** (new) — vocabulary module with LNG Gaming members, game titles, and channel terms. Exported as `INITIAL_PROMPT` string for Whisper's decoder context.
- **`simple_asr.py`** — `process_audio_file()` now loads the keyword prompt and passes `prompt_ids` to every `model.generate()` call via `process_chunk_async`, biasing Breeze-ASR-25 toward channel-specific vocabulary. Prompt token count is added to the `max_length` budget so content length is not reduced.
- **`postprocess_transcriptions.py`** (new) — LLM post-processing for existing `_combined.txt` (or `_merged.txt`) files. Rule-based pre-clean removes hallucinated repetitions (CJK char repeated 4+ times, `那個` repeated 3+ times); LLM pass adds punctuation and corrects proper nouns. Output saved as `_postprocessed.txt` in the same format. Supports `--filter`, `--skip-existing`, `--source merged`, `--dry-run`.

---

## 2026-04-26 — Migrate quiz tables from MySQL to SQLite

- **`quiz_db.py`** — rewritten to use `sqlite3` against `lng_graphrag.db` instead of MySQL. Syntax changes: `?` placeholders, `RANDOM()`, `ON CONFLICT ... DO UPDATE SET` for upsert, `INTEGER PRIMARY KEY AUTOINCREMENT`, `row_factory=sqlite3.Row` for dict access. `get_pending_questions` no longer JOINs the MySQL `users` table (returns `created_by` ID instead of username).
- **`web_app.py`** — `_init_quiz_tables_once()` no longer gates on `auth_configured()` since SQLite is always available.
- Old MySQL `questions`, `user_question_stats`, `question_attempts` tables dropped.

---

## 2026-04-26 — Fix fetch_new_vods to also check /videos tab

- **`fetch_new_vods.py`** — was only checking `@LNGworkshop/streams` (5 results); now also checks `@LNGworkshop/videos` (622 videos) and merges by video ID. Regular uploads like `【LNG】2026APR...` were being missed entirely.

---

## 2026-04-26 — Phase 1 quiz/test system

### What changed

- **`quiz_db.py`** (new) — DB layer: `init_quiz_tables()`, `get_questions()`, `record_attempt()`, `get_user_quiz_stats()`, `count_active_questions()`, `add_question()`, `get_pending_questions()`, `update_question_status()`.  Three tables: `questions`, `user_question_stats` (composite PK, upserted), `question_attempts` (append-only log).
- **`generate_quiz_questions.py`** (new) — standalone LLM script: reads `./transcriptions/*_combined.txt`, generates facts/content × easy/hard questions, inserts with `status=active`. Supports `--dry-run`, `--max-files`, `--per-chunk`.
- **`web_app.py`** — added `_init_quiz_tables_once()` (called via `@app.before_request`); 8 new quiz API routes: `/api/quiz/count`, `/api/quiz/questions`, `/api/quiz/answer`, `/api/quiz/stats`, `/api/quiz/add-question`, `/api/quiz/admin/pending`, `/api/quiz/admin/review`.
- **`templates/index.html`** — new **📚 Test** tab (tab 4): setup screen (type/level/mode/count selectors with live question counts), question screen (progress dots, option buttons, green/red highlight, explanation), summary screen (score, stars, retry wrong), add-question form (pending review for non-admins, auto-active for admins), admin review panel.

### Generate questions
```bash
python generate_quiz_questions.py --max-files 3 --per-chunk 2
```

---

## 2026-04-26 — Sort by upload date + scheduled live replay fetcher

### What changed

- **`VODs/download_from_youtube.py`** — added `upload_date` (YYYYMMDD) as 4th CSV column; rewrote `update_csv_status()` and `ensure_video_in_csv()` to use `DictReader`/`DictWriter` for column-safe updates.
- **`web_app.py`** — `get_download_status()` now returns `upload_date` per video; `get_title_to_url_map()` returns `{url, upload_date}` dict; `get_transcription_files()` sorts by `upload_date` desc (falls back to filename).
- **`templates/index.html`** — Downloads table now shows an Upload Date column; added "上傳日期 ↓↑" toggle button that re-sorts the table client-side without a server round-trip.
- **`fetch_new_vods.py`** (new) — standalone script: fetches `@LNGworkshop/streams`, finds videos absent from `videos.csv`, downloads them, runs ASR, loads to Neo4j.  Supports `--dry-run`, `--no-asr`, `--no-neo4j`.
- **`scheduler.py`** (new) — background loop that runs `fetch_new_vods.py` every `FETCH_INTERVAL_HOURS` hours (default 6; set in `.env`).
- **`boot.sh`** — starts `scheduler.py` alongside Flask and Cloudflare Tunnel.

---

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
