# Changes

## 2026-05-26 — ASR: fix CUDA race condition and add per-file subprocess isolation

- **`simple_asr.py`** — removed `ThreadPoolExecutor` (threads sharing one CUDA model caused race conditions → `device-side assert triggered`). Processing is now sequential. Added pre-chunk validation (empty/all-zero/NaN audio). Added CUDA error recovery: on `RuntimeError` with "CUDA" in the message, clears GPU cache and retries the chunk on CPU, then moves the model back to GPU for subsequent chunks.
- **`run_batch_asr.py`** — each WAV is now processed in a fresh `subprocess` so a CUDA crash in one file cannot poison the CUDA context for subsequent files (was the cause of `no kernel image is available for execution on the device` appearing on all chunks of the second file). Removed `safe_execute` import of `process_audio_file` from same process; now calls `simple_asr.py` via `subprocess.run`.

---

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

## 2026-07-02 — UI refactor Phase 0 + shared kit (feature/ui-refresh)

- **De-monolith `templates/index.html`** (2367 → 322 lines): extracted inline `<style>`
  (901 lines) → `static/css/app.css` and inline `<script>` (1143 lines) → `static/js/app.js`.
  Linked both via `url_for('static', …)`. Zero visual change intended.
- Kept the one Jinja token inline: `<script>window.INITIAL_TAB = {{ active_tab|default(0) }}</script>`
  before `app.js`; `app.js` reads it with `?? 0` fallback.
- **Shared UI kit** added: `static/css/kit.css` + `static/js/kit.js` — `toast.{success,error,info}()`
  and `confirmDialog() -> Promise<boolean>`, plus skeleton classes. Gold/dark themed.
- **Replaced native dialogs** in `app.js`: `confirm()` (delete chunk) → `confirmDialog({danger})`;
  7× `alert()` → `toast.error/info` + `toast.success` (chunk save, quiz add).
- Added `KIT_SPEC.md` — cross-repo visual spec (tokens, Toast/ConfirmDialog/Skeleton/Button/
  EmptyState, per-repo accent map, React port checklist).
- Verified: `node --check` on both JS files, Jinja render smoke test (asset links + load order).
  Live app smoke test (Neo4j/MySQL up) still recommended before merge.

## 2026-07-02 — UI Phase 2: pipeline-rail shell + Ask-as-chat + graph viz

- **Shell redesign** (`static/css/redesign.css`, new): replaced legacy sidebar/header/stats-bar
  with a pipeline **rail** (Ingest · Library · ★Ask · Test) + **topbar** (breadcrumb, ⌘K omni,
  user chip). Stats moved into the rail as contextual count badges (Ingest=pending, Library=transcriptions).
- **Ask is now a chat surface**: `executeNLQuery` appends user/AI message bubbles, streams a
  thinking state, renders the answer with **citation chips** (click → opens Library + toast).
  Cypher demoted to a `⟩ developer` disclosure. NL/Cypher IDs (`nlQuery`, `cypherQuery`,
  `queryResults`) preserved.
- **Graph mini-viz**: cytoscape (CDN) renders a concentric graph of the answer's sources
  (query center → concept/chunk nodes); node/chip click opens the source.
- **Command palette (Ctrl/⌘K)**: fuzzy jump to any stage or run an Ask query; arrow/enter/esc nav.
- **User menu**: History + Admin 2FA + Logout moved into the rail user dropdown (History is no
  longer a hidden tab). Login/Register shown when logged out.
- JS fixes from the restructure: `toggleSidebar` no longer depends on removed hamburger button;
  `switchTab` targets `.rail-item` + toggles content by id + sets breadcrumb; `refreshAll` reads
  the active rail item; removed a duplicate Enter handler that double-sent NL queries.
- Verified: `node --check` clean, Jinja render, unique IDs, balanced tags, and a rebuilt Docker
  test container on :5001 (isolated, no cloudflared) serving the new shell (HTTP 200 on page + assets).

## 2026-07-02 — Chunk → YouTube timestamp seek (A+B+C, IFrame API)

- **A — controllable player**: replaced the static transcription `<iframe>` with a YouTube
  **IFrame API** player. Loaded `https://www.youtube.com/iframe_api`; added `onYouTubeIframeAPIReady`,
  a lazy `ytPlayer`, `loadVideoInPlayer(videoId, start)` (queues if API not ready), and
  `seekPlayer(seconds)`. `setTranscriptionYoutubeVideo(url, startSeconds)` now drives the player
  (loads at a native start offset) instead of setting `iframe.src`.
- **B — chunk seek**: `renderChunksWithEdit` now renders a ▶ button per chunk with a `start_time`;
  clicking it calls `seekPlayer(chunk.start_time)` to jump the player. (Timecodes were previously
  dead labels — no seek existed.)
- **C — Ask deep-open**: citation chips now call `openSource(i)` →
  `openTranscriptionByDoc(doc, start)`: fuzzy-matches the source's `doc` to a Library transcription
  (`findTranscriptionIndex`), opens it (loads chunks + video at the timestamp), scrolls it into
  view, and seeks. Falls back to a toast if the doc can't be matched. `switchTab` gained a
  `skipLoad` flag so the controlled open isn't clobbered by the tab's auto-refresh.
- Verified: `node --check`, Jinja render (IFrame API + player div present), rebuilt :5001 test
  container (HTTP 200). Live seek needs a transcription with a YouTube URL + Neo4j data to confirm end-to-end.

## 2026-07-02 — Fix: right-panel video blank in Docker (videos.csv not in container)

- **Root cause**: `get_transcription_files()` maps each transcription → its YouTube `url` by joining
  against `VODs/videos.csv`, but `.dockerignore` excludes `VODs/`, so the CSV was absent in every
  container — `/api/transcriptions` returned `url: ''` for all 398 rows. No url → no player created →
  chunk ▶ hit "no player". (Pre-existing; only surfaced now that the player consumes `url`.)
- **Fix**: mount the CSV read-only into the app container — added
  `./VODs/videos.csv:/app/VODs/videos.csv:ro` to the compose `app` service. With it mounted,
  281/398 transcriptions resolve a URL (remaining 117 are a title↔csv-title mismatch, separate data issue).
- **Frontend hardening**: `getYoutubeId` now parses watch/youtu.be/shorts/embed, bare ids, and
  `watch?…&v=` (v not first param). `renderChunksWithEdit` only renders the ▶ seek button when the
  transcription actually has a playable video (`hasVideo`), so no misleading ▶ on url-less rows.

## 2026-07-02 — ASR quality: beam search, self-consistency, richer keyword prompt, Taiwan-LLM cleanup

Reduce ASR typos without human labelling. Four changes:

1. **Beam search (`simple_asr.py`)** — decoding was greedy (`num_beams=1`); now defaults to
   beam width 5 via `ASR_NUM_BEAMS` env. Fewer acoustic errors at some speed cost.
2. **Self-consistency (`simple_asr.py`)** — set `ASR_SELF_CONSISTENCY=1` to also run a greedy
   pass per chunk. Where beam and greedy disagree, both candidates are written to a
   `transcriptions/<title>_candidates.txt` sidecar (`<<BEAM>>` / `<<GREEDY>>` blocks) for the
   cleanup step to reconcile. `_combined.txt` stays the beam result (backward compatible).
3. **Richer keyword prompt (`asr_keywords.py`)** — `INITIAL_PROMPT` rebuilt as a natural
   Traditional-Chinese sentence listing all 14 member handles + more game titles (kept under
   Whisper's ~224-token prompt cap; slang dropped from the acoustic prompt since the LLM pass
   fixes it better).
4. **Taiwan-LLM cleanup (`postprocess_transcriptions.py`)** — correction pass now defaults to a
   local transformers backend running Taiwan-LLM-7B-v2.0-chat (`yentinglin/...`, best Taiwanese
   Mandarin). The model ships safetensors only (no GGUF), so it's run via `transformers.pipeline`
   with the tokenizer's chat template, not Ollama. New `TransformersChat` adapter exposes the same
   `.invoke(messages) → .content` interface; pipeline loads lazily and is reused. Backend is
   selectable via `ASR_CLEAN_BACKEND=transformers|ollama|openai` (default transformers),
   model via `ASR_CLEAN_MODEL`. New `--use-candidates` flag reconciles the self-consistency
   sidecar (`llm_reconcile_chunk`) before cleaning.

**Deps**: already in `requirements.txt` (transformers 4.57.1, accelerate 1.10.1, torch 2.5.1).

**Recommended run**:
```
set ASR_SELF_CONSISTENCY=1 && python run_batch_asr.py
python postprocess_transcriptions.py --use-candidates
```
(cleanup auto-downloads the Taiwan-LLM weights on first run; needs GPU/VRAM for the 7B model.)

Verified: `py_compile` on all three modules; `INITIAL_PROMPT` renders at 154 chars (under cap).
Not yet run end-to-end against audio (needs GPU + first-run model download).

## 2026-07-02 — Recover all 117 "missing" transcription URLs (normalized join)

- **Recreated live `lng-app`** with the videos.csv mount (`docker compose up -d app`, existing image):
  live right-panel video works again (281/398 via exact match).
- **Root cause of the 117**: transcription FILENAMES substitute filesystem-illegal chars — `/` becomes
  `⧸` (U+29F8, a math *symbol*) — so exact string match against `videos.csv` titles missed them.
  None were actually absent from the CSV.
- **Fix**: `get_title_to_url_map` now also indexes titles by a normalized key, and
  `get_transcription_files` falls back to it. `_normalize_title` keeps only alphanumerics + CJK
  (drops punctuation/symbols/brackets/spaces), so `⧸`≡`/`. Digits kept → "1/2" vs "2/2" stay distinct.
- **Result**: 398/398 transcriptions resolve their URL in the rebuilt test container. Verified each of
  the 3 hardest matched the exact CSV row, and **0 normalized keys map to >1 distinct URL** (no
  collisions) — so the fuzzy join is unambiguous. No online/YouTube lookup was needed.

## 2026-07-02 — fix_cjk_spacing.py: restore CJK↔Latin spaces after LLM cleanup

- **`fix_cjk_spacing.py`** (new) — the Taiwan-LLM cleanup runs through a BPE tokenizer
  (`clean_up_tokenization_spaces`) that drops the space between Chinese and English/number runs
  ("google他" → should be "google 他", "random的" → "random 的"). This standalone pass reinserts
  spaces at CJK↔Latin boundaries. Idempotent (safe to re-run, and safe to run on files the
  postprocess job already finished while it's still processing others). Skips `=== Chunk N [..s] ===`
  headers so timestamps aren't mangled. Flags: `--filter`, `--suffix` (default `_postprocessed`),
  `--letters-only` (leave digit+CJK tight, e.g. keep "5顆"), `--dry-run`.
- Run after the postprocess job finishes: `python fix_cjk_spacing.py`
- Verified: unit-tested on google/random/mixed-English/digit cases + header preservation + idempotency.

**Note (not a change, discovered):** cleaned `_postprocessed.txt` does NOT surface on the website —
`web_app.py:get_transcription_files` lists only `_combined.txt`; Neo4j/GraphRAG is a separate ingest.
Surfacing the cleaned text is a pending follow-up (promote to `_combined`, or point the app/ingest at
`_postprocessed`).

## 2026-07-02 — Web UI serves cleaned transcriptions when present

- **`web_app.py`** — `get_transcription_file_path()` resolution priority is now
  manual edit > `_postprocessed.txt` (Taiwan-LLM cleaned + CJK-spaced) > raw `_combined.txt`.
  Previously it only checked edit then combined, so LLM-cleaned text never surfaced on the site.
  `get_transcription_files()` char-count now measures the served file so the listing reflects the
  cleaned length. Transcription id stays the `_combined.txt` name (frontend unchanged); only the
  served content changes. Neo4j/GraphRAG ingest is still separate (unchanged).

## 2026-07-02 — rebuild_transcriptions.py + full re-ASR of broken transcriptions

- **Audit finding**: 382/398 `_combined.txt` were transcribed before the 30s chunk cap → whole
  streams as one chunk → Whisper's ~448-token cap truncated them (worst: 4.8h chunk → text `你`).
  Only 16 files structurally sound. `_postprocessed.txt` presence ≠ good (many were cheap_clean
  copies; real cleaning = has CJK punctuation).
- **`rebuild_transcriptions.py`** (new) — finds files with any chunk >`--threshold` (60s),
  ensures the WAV (downloads from `videos.csv` URL via `download_from_youtube` if missing, reusing
  web_app's NFKC+alnum title normalization to bridge filename↔csv drift), then re-runs
  `simple_asr.py` (beam=5). Resumable (skips files already ≤threshold). Flags: `--threshold`,
  `--no-download`, `--filter`, `--limit`, `--dry-run`. Of 382: 93 had WAV, 289 needed download, all
  mapped to a URL.
- **Env fix (important)**: ASR/GPU work must use `.venv/Scripts/python.exe` (Py3.12, torch cu128,
  torchaudio, CUDA True). Bare `python` = `C:\Python314` (torch CPU, no torchaudio) — it silently
  ran the Taiwan-LLM cleanup on CPU (the earlier "hang"). Documented in project memory.
- Smoke-tested: `LNG日常：LOL拳擊節` 61.81s/103chars → 30s chunks/308chars of real content.
- Full rebuild launched in background (`rebuild.log`). After it finishes: delete stale
  `_postprocessed.txt`, re-run `postprocess_transcriptions.py` (via venv), then `fix_cjk_spacing.py`.

## 2026-07-02 — 16 structurally-good files: quality audit

- Verified the 16 files with all chunks ≤60s. 11 are LLM-cleaned (readable; residual homophones are
  game-jargon-level, e.g. Lux champion name, `下路`); 5 recent files (2025DEC–2026APR) are chunked
  correctly but were never cleaned (contain `嗯嗯嗯…` hallucinations + `[Error in chunk]` markers) —
  they need the cleanup pass, not re-ASR.

## 2026-07-03 — Correct LNG member roster (6 constant + guests) across ASR + cleanup

- Confirmed roster: 6 CONSTANT members 小六、六探、鳥屎、Leggy、八毛、老王; rare guests
  展邱、奶哥、悅悅、顏顏、蕾蕾、探探、天神. Prior list had wrong guesses (乃哥→奶哥; 大毛/梁兄/阿旺/托老師/素雲 not real).
- **`asr_keywords.py`** — split into `CONSTANT_MEMBERS`/`GUEST_MEMBERS`, added `MISHEARD={'巴毛':'八毛'}`.
  `INITIAL_PROMPT` now leads with the 6 constant ("固定成員") then guests ("偶爾會提到") for stronger biasing.
- **`postprocess_transcriptions.py`** — cleanup `SYSTEM_PROMPT` glossary updated to the real roster with an
  explicit 巴毛→八毛 correction; `cheap_clean` now applies `MISHEARD` deterministically (not via the LLM).
- In-flight rebuild picks this up per new file (each simple_asr subprocess re-imports asr_keywords).
