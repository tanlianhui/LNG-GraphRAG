# Decision Log

## 2026-05-26 — Scheduler changed to daily 8 AM dry-run with health gates

**Decision:** Replace 6-hour interval full-pipeline scheduler with a daily 08:00 dry-run check gated on Docker + Ollama health.

**Why:** Current backlog is stable; no new videos expected soon. Auto-downloading would waste ASR/embedding compute on surprise uploads. User wants to review any new video before committing to ingestion. Health gates prevent silent failures where fetch runs but Neo4j/Ollama are unavailable, producing misleading "no new videos" or failed loads.

**How to apply:** When new videos appear in the daily log, user inspects the list and manually triggers download/ingest (`python fetch_new_vods.py --limit 1` etc.) or adds the video URL to a blacklist. Scheduler itself stays read-only.

---

## 2026-05-25 — Ollama port 11700 instead of default 11434

**Decision:** Set `OLLAMA_HOST=http://0.0.0.0:11700` in `boot.sh` and export to all child processes.

**Why:** Windows Hyper-V/WSL reserves port ranges including 11341–11640, which covers Ollama's default 11434. `ollama serve` fails with "access permissions" error. Port 11700 is outside all excluded ranges on this machine.

**How to apply:** Always use `OLLAMA_HOST` env var when calling Ollama CLI or starting the server. Do not hardcode 11434 anywhere.

---

## 2026-05-24 — --limit flag on fetch_new_vods + CSV None-key fix

**Decision:** Add `--limit N` to `fetch_new_vods.py` to cap per-run processing rather than always consuming all pending videos.

**Why:** Transcription + embedding for 7+ queued videos can take hours. Limiting to 2 on-demand runs lets the user ingest incrementally while the nightly scheduler handles the rest. The `--limit 0` default means scheduled runs still process everything.

**Decision:** Fix `update_csv_status` to strip `None` keys/fieldnames instead of raising ValueError.

**Why:** `append_to_csv` writes 4-column rows (with `upload_date`) to a 3-column CSV, so `csv.DictReader` maps the orphaned 4th field to key `None`. The correct fix is to sanitize at read-time rather than rewriting the CSV schema, since `upload_date` is already being stored and the mismatch is harmless.

**Decision:** Export `PYTHONIOENCODING=utf-8` in `boot.sh`.

**Why:** Windows cp950 terminals can't encode Unicode emojis used in Python script print statements. Setting the env var at boot.sh level fixes all child processes (Flask, scheduler, loaders) in one place rather than patching each script.

---

## 2026-04-28 — Whisper keyword biasing via initial_prompt

**Decision:** Inject channel vocabulary as Whisper's `initial_prompt` (`prompt_ids`) rather than fine-tuning or hotword forcing.

**Why:** Whisper's decoder is autoregressive; seeding its context with a natural-language sentence containing target terms (member names, game titles) causes the model to assign higher probability to those tokens during beam/greedy decoding — without forcing them or breaking phoneme alignment. Fine-tuning would require labelled data; hardcoded hotword forcing (e.g., forced_decoder_ids) produces unnatural insertions. `initial_prompt` is the canonical Whisper mechanism and is well-supported by the transformers pipeline.

**Alternative rejected:** Character-level hotword substitution post-ASR — too fragile, misses context. CTC prefix scoring — not available in Whisper architecture.

---

## 2026-04-28 — Separate post-processing script instead of in-place overwrite

**Decision:** `postprocess_transcriptions.py` saves `_postprocessed.txt` alongside the source file rather than overwriting `_combined.txt`.

**Why:** The raw `_combined.txt` is the primary ASR artifact and should be preserved for debugging and re-runs. A separate file lets the ingest pipeline be updated independently to prefer the cleaner version, and allows easy A/B comparison. In-place overwrite would make it impossible to re-run the LLM cleaner with a better prompt without re-running ASR.

**Alternative rejected:** Overwriting in place — loses ground truth. Suffix `_clean.txt` — less consistent with the existing `_merged.txt` naming.

---

## 2026-04-26 — Quiz data in SQLite, not MySQL

**Decision:** Move `questions`, `user_question_stats`, `question_attempts` from MySQL to `lng_graphrag.db` (SQLite).

**Why:** MySQL is for user auth and sessions — shared, networked state that genuinely needs a server. Quiz questions and per-user stats are app content data with no cross-service access requirement; they belong alongside `files`, `downloads`, and `processing_jobs` in SQLite. Keeping them in MySQL added Docker dependency, connection overhead, and an unnecessary coupling between content and auth layers.

**Alternative rejected:** Keep in MySQL for consistency with auth tables — rejected because the two concerns are distinct and SQLite is already the established store for app data in this project.

---

## 2026-04-26 — fetch_new_vods: check both /streams and /videos tabs

**Decision:** Fetch from both `@LNGworkshop/streams` and `@LNGworkshop/videos`, deduplicate by video ID.

**Why:** Regular uploads (`was_live: False`) appear only on `/videos`; live replays appear on `/streams`. Checking only `/streams` (5 results) silently missed the main content library. The `/videos` tab has 622 entries.

**Alternative rejected:** Scraping the main channel URL — it may not distinguish between tabs consistently across yt-dlp versions.

---

## 2026-04-26 — Quiz: two-table stats design (aggregate + log)

### Context
Need to efficiently skip already-answered questions in random selection, and track per-user accuracy as a proxy for question difficulty.

### Decision — `user_question_stats` as composite-PK aggregate + `question_attempts` as append-only log

**Chosen:** `user_question_stats (user_id, question_id)` with composite PK stores `attempt_count` + `correct_count`, upserted on every answer.  `question_attempts` is an append-only log for history.  Random "skip answered" query uses `LEFT JOIN ... IS NULL` on the composite PK — O(log n) on the index, not a table scan.

**Why:** One upsert per answer keeps the aggregate current without ever needing to GROUP BY a growing log.  The log is retained for future analytics (time-of-day patterns, session replay) without coupling it to the hot query path.

**Alternative rejected:** Using only `question_attempts` and computing `MIN(answered_at) IS NOT NULL` per (user,question) — would require full scan or GROUP BY on every question-fetch.

---

## 2026-04-26 — Quiz: correct_answer not sent in question list response

### Context
The frontend fetches a batch of questions at session start, then checks answers question by question.

### Decision — strip `correct_answer` from `/api/quiz/questions`, reveal only in `/api/quiz/answer`

**Why:** If correct answers are in the initial payload, client-side JS can expose them (devtools, etc.).  The answer route is the single authoritative check; it also atomically records the attempt — so there's no way to submit a "correct" answer without going through the server.

---

## 2026-04-26 — Use /streams tab URL for live replay detection

### Context
The user asked to auto-fetch "直播回放" (live stream replays) from the LNG official channel. yt-dlp's `extract_flat=True` does not reliably expose `was_live` / `live_status` metadata, so filtering by that field is fragile.

### Decision — use `@LNGworkshop/streams` instead of `/videos`

**Chosen:** `fetch_new_vods.py` hits `https://www.youtube.com/@LNGworkshop/streams` which is YouTube's dedicated streams/live tab — it only lists live stream replays by definition. No title-pattern or metadata heuristic needed.

**Why:** The streams tab is the canonical live-replay list; it avoids false positives from regular uploads.

**Alternative rejected:** Filtering `/videos` by `live_status == 'was_live'` — unreliable with flat extraction and requires an extra metadata fetch per video.

---

## 2026-04-26 — Client-side sort, server-side upload_date

### Context
User wants to sort by YouTube upload time with a reversible toggle.

### Decision — store upload_date in CSV, sort JS client-side

**Chosen:** `upload_date` (YYYYMMDD string from yt-dlp) stored in `videos.csv` as a 4th column.  The Downloads table sorts the already-loaded `allVideos` array in JS — no extra API call needed.  The `/api/download-status` response already contains all video data, so the sort is zero-cost.

**Why:** YYYYMMDD sorts lexicographically = chronologically, so no date parsing needed.  Client-side toggle is instant UX.

**Alternative rejected:** Server-side sort query param — adds roundtrip and complexity for a list that's already fully loaded.

---

## 2026-04-08 — Create .env with port 17687 for Neo4j

### Context
`.env` was missing entirely (boot.sh warned about it on every start). `load_single_to_neo4j.py` defaulted to `bolt://localhost:7687` but Docker maps Neo4j Bolt to `17687` on this machine to avoid Windows port conflicts.

### Decision — create .env from .env.example with correct port

**Chosen:** `NEO4J_URI=bolt://localhost:17687` plus MySQL credentials matching `docker-compose.yml`. Committed `.env` so the project is self-contained on this machine.

**Note:** `.env` contains no secrets beyond the local Docker passwords already in `docker-compose.yml`.

---

## 2026-04-08 — Transcription list: character count over file size

### Context
File size in MB is not meaningful to users browsing transcriptions. Character count directly conveys how much content is in each document, and is more accurate for CJK text where word boundaries differ from whitespace.

### Decision — count characters on the server at list time

**Chosen:** Read each `_combined.txt` file during `get_transcription_files()` and count characters with `len(content)`. More meaningful than word count for Mandarin transcriptions. Cost is acceptable since the list is small and files are read sequentially.

**Rejected:** Storing count in a sidecar file — unnecessary complexity for this scale.

---

## 2026-04-08 — Auto-start: 2-minute login delay for Docker readiness

### Context
The existing `lng-graphrag.vbs` startup script fired immediately at login, before Docker Desktop finished initialising. `docker compose up -d` would fail, and `set -e` in boot.sh killed the process before Flask or cloudflared started.

### Decision — sleep 2 minutes in the VBScript launcher

**Chosen:** `WScript.Sleep 120000` at the top of `lng-graphrag.vbs`. Docker Desktop is already in the Run registry so it starts concurrently; 2 minutes is enough for it to be fully ready on typical hardware.

**Rejected:** Task Scheduler with built-in trigger delay — requires admin rights to register; the Startup folder VBScript already existed and is simpler.

---

## 2026-04-08 — boot.sh: make Docker failure non-fatal

### Context
Transcriptions were not loading on the public URL. Root cause: Docker Desktop was not running, causing `docker compose up -d` to exit non-zero. With `set -e` active in boot.sh, this killed the entire script before Flask or cloudflared could start.

### Decision — warn and continue rather than abort

**Chosen:** Wrap `docker compose up -d` in an `if` to capture the exit code, print a warning on failure, and continue. Flask serves transcriptions from the filesystem and does not require Neo4j/MySQL to be up for basic operation.

**Rejected:** Removing `set -e` globally — too broad, would mask other real errors.

---

## 2026-04-08 — Cloudflare Tunnel for public access; local stack unchanged

### Context
User wants LNG-GraphRAG accessible at `your-domain.example.com` whenever the PC is on.

### Decision 1 — Cloudflare Tunnel, no cloud migration

**Chosen:** Run Neo4j + MySQL + Flask locally; expose via Cloudflare Tunnel.

**Why:** The stack depends on Neo4j graph queries with complex Cypher + LangChain orchestration and local Breeze-ASR-25 model. Migrating to cloud would require Neo4j AuraDB (paid), a cloud Python host, and significant refactoring. The user's use case is personal/research, and the PC is the primary compute node.

**Why not expose ports directly:** Dynamic home IP + no open ports. Cloudflare Tunnel provides stable HTTPS without firewall changes.

### Decision 2 — Separate cloudflared config file per project

**Chosen:** `cloudflared-config.yml` in the project root, run with `--config` flag.

**Why:** The existing `~/.cloudflared/config.yml` already belongs to `screenshot-meme-qa`. Each project having its own config keeps concerns separated and makes it easy to stop one tunnel without affecting the other.

### Decision 3 — Startup via Windows Startup folder VBScript

Same rationale as screenshot-meme-qa: user-writable, no admin rights needed.
