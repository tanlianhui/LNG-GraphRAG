# Decision Log

## 2026-05-26 — ASR sequential processing and subprocess isolation

**Decision:** Replace `ThreadPoolExecutor(max_workers=4)` in chunk processing with a sequential loop; run each WAV file in a subprocess from the batch runner.

**Why:** `ThreadPoolExecutor` with 4 threads sharing one CUDA model is not thread-safe — concurrent CUDA kernel launches from multiple threads trigger device-side assertions. CUDA errors are also "sticky": once `device-side assert triggered` fires (e.g. chunk 139 of 2026 MAY), the CUDA context is poisoned and every subsequent CUDA call in the same process returns `no kernel image is available for execution on the device` — this is why 2026 APR failed on all chunks in the same run. Subprocess isolation gives each file a clean CUDA context.

**How to apply:** Do not re-introduce `ThreadPoolExecutor` for CUDA inference. If parallelism is needed, use separate processes (`multiprocessing` or `subprocess`), not threads.

---

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

### Decision — Extract CSS/JS from index.html before any redesign (Phase 0)

**Why:** The 2367-line single-file template made every UI change high-risk and unreviewable.
Splitting CSS/JS into `static/` first (pure move, no behavior change) shrinks the template to
markup only, enables browser caching, and lets later phases (graph viz, chat panel) land as
small diffs. Kept `INITIAL_TAB` inline because it is the only Jinja-injected value the JS needs.

**Alternatives rejected:** (a) redesign in place — too risky in one giant file; (b) rewrite the
dashboard in React — out of scope, Flask/Jinja stack works and the task is UI/UX, not a rebuild.

### Decision — Copy-in shared kit, vanilla reference in lng

**Why:** User chose copy-in over a published package (repos stay independent, no monorepo/registry
setup). lng is Jinja/vanilla so its kit is plain JS+CSS; that same API (`toast.*`, `confirmDialog`)
is the contract the React repos re-implement. Native `alert/confirm/prompt` removed because they
block the main thread, can't be themed, and break the mobile flow on the other apps.

### Decision — Phase 2 layout: pipeline rail + Ask-as-hero (over "keep tabs")

**Why:** The app's payoff is asking the knowledge graph, but GraphRAG was tab 3 of 5 flat tabs
behind a tall header + a global stats bar that only meant anything on the Download tab. Reframing
the nav as the actual pipeline (Ingest→Library→Ask→Test), moving stats into the rail where they're
contextual, and turning Ask into a chat with source-linking citations puts the value front-and-center
and reclaims vertical space. User picked this over the lower-risk "restyle in place" option.

**Alternatives rejected:** (a) keep 5-tab shell, restyle only — less rethink but preserves the
buried-hero + noisy-global-stats problems; (b) Ask-first landing that hides the pipeline — loses the
ingest/library workflow that feeds the graph.

**Graph viz:** chose cytoscape (CDN, no build step) for the Ask result mini-graph. The NL endpoint
returns chunks, not edges, so v1 draws a derived star (query→sources); real concept↔concept graph
stays on the Cypher path as a follow-up. Citation-chip → source currently switches to Library +
toasts the doc/timestamp; deep-seek into the exact chunk/player is a planned follow-up.

### Decision — YouTube IFrame API (not URL start-param) for chunk seek

**Why:** Chunks already carry start/end times but nothing used them to move the video — no seek
function existed. Chose the IFrame API over reloading `…/embed?start=<sec>` because the API seeks
in-place (`player.seekTo`) with no reload/re-buffer flicker, and lets a reused player jump between
timestamps smoothly as the user clicks different chunks or Ask citations. Cost: an async API-ready
handshake (handled via `onYouTubeIframeAPIReady` + a pending-video queue) and swapping the static
iframe for an API-managed element.

**Ask→source mapping:** the NL endpoint returns `doc` names, not Library indices, so matching is
fuzzy (filename/title, extension-stripped, substring fallback). If a source's `doc` has no matching
transcription (or that transcription has no YouTube URL), the chip degrades to an informational toast
rather than failing silently. A stricter chunk-id-level anchor would need the NL endpoint to return
the source chunk id — a possible backend follow-up.

### Decision — mount videos.csv (not bake it into the image)

**Why:** The web app needs `VODs/videos.csv` for the transcription→YouTube-URL join, but `VODs/` is
`.dockerignore`d (host-only media). Chose a read-only bind mount over un-ignoring the file in the
build context so the CSV stays live — the ASR pipeline appends rows as new videos download, and a
mount reflects that without an image rebuild. The 117 transcriptions still lacking a URL are a
title-normalisation mismatch between the transcription filename and the csv `title` column — a
separate data-cleanup task, not a packaging one.

### Decision — ASR quality improvements without human labelling (2026-07-02)

**Context:** ASR output (Breeze-ASR-25 / Whisper) had homophone typos and no punctuation. Goal:
better transcripts without manual labelling.

**Why beam search over greedy:** `num_beams=1` was leaving easy accuracy on the table. Beam=5 is
the standard zero-labelling accuracy bump; per-chunk audio is ≤30s so the dynamic `max_new_tokens`
budget (448 − prompt − 8) still leaves ample room. Left configurable (`ASR_NUM_BEAMS`) to trade
speed back on slow hardware.

**Why self-consistency as a sidecar, not inline:** picking the better of two candidates needs
world/context knowledge → an LLM job, not an acoustic one. Emitting `_candidates.txt` alongside
the unchanged `_combined.txt` keeps every existing consumer (ingest, Neo4j load) working, and lets
the reconciliation happen in the cleanup pass where the channel glossary already lives. Only
divergent chunks are stored, so the sidecar stays small.

**Why Taiwan-LLM-7B-v2.0-chat for cleanup, served via transformers:** user requested it for best
Taiwanese-Mandarin handling of homophones/slang. Initially planned Ollama, but the HF repo ships
only safetensors (no GGUF), so an Ollama Modelfile path was dropped. Run instead via
`transformers.pipeline` using the tokenizer's built-in chat template (the model's documented usage).
A small `TransformersChat` adapter exposes the same `.invoke(messages) → .content` interface the
script already used, so `llm_clean_chunk` / `llm_reconcile_chunk` are untouched. GPU pressure is a
non-issue because cleanup runs as a separate pass after ASR finishes — Whisper isn't resident.
Backend stays swappable (`ASR_CLEAN_BACKEND`) so Ollama/OpenAI remain fallbacks.

**Alternatives rejected:** Ollama serving (no GGUF available for this model);
temperature-sampled N-way voting for self-consistency (more compute, greedy-vs-beam already
surfaces most divergences cheaply).

### Decision — recover missing URLs by normalized join, not by editing videos.csv or scraping YouTube

**Why:** All 117 "missing" URLs were already present in videos.csv — the mismatch was purely the
`/`→`⧸` filename substitution (plus minor punctuation drift). Normalizing the join (alphanumeric+CJK
only) recovers 100% with zero data edits and no risk of grabbing the wrong video from a web search.
Verified safe: 0 normalized keys collide to multiple URLs. Rejected: (a) editing videos.csv — mutates
source data, fragile; (b) YouTube search per title — unnecessary and error-prone (could bind a wrong
video). Digits are preserved in the normal form specifically so multi-part streams ("- 1 / 2" vs
"- 2 / 2") don't collapse together.

### Decision — CJK↔Latin spacing as a separate idempotent pass (2026-07-02)

**Context:** Taiwan-LLM cleanup output loses spaces between Chinese and English/numbers because the
model's BPE tokenizer applies `clean_up_tokenization_spaces` (destructive for BPE). User did not want
to stop the in-flight 398-file run.

**Why a separate script, not a fix inside postprocess:** the run was already underway and reloading
the pipeline with `clean_up_tokenization_spaces=False` would have discarded progress. A post-hoc,
idempotent spacing pass fixes finished files without touching the running job and can be re-run freely
(a boundary that already has a space is skipped). Also keeps concerns separate: spacing is
deterministic regex, not LLM work.

**Why digits are spaced by default (with `--letters-only` opt-out):** matches the common "pangu"
convention and handles cases like versioned titles; but Chinese measure-word phrases ("5顆") read
fine tight, so the opt-out exists.

**Follow-up noted:** `_postprocessed.txt` is invisible to the web UI (`get_transcription_files` reads
only `_combined.txt`) and to Neo4j (separate ingest). Wiring the cleaned files into the site/graph is
a deliberate, still-pending step — not automatic.

### Decision — web UI prefers _postprocessed, keyed by the _combined id (2026-07-02)

**Decision:** Serve `_postprocessed.txt` when it exists (below manual edits, above raw `_combined`),
without changing the transcription id the frontend uses.

**Why:** Keeps the raw ASR output as on-disk ground truth (per the earlier no-in-place-overwrite
decision) while still showing the cleaner text to users. Keying the lookup on the existing
`_combined.txt` filename means no frontend or edit-flow changes — the resolver swaps the backing file
transparently. Chose this over promoting/renaming `_postprocessed`→`_combined` (destructive, loses
ground truth) and over a frontend toggle (extra UI for no clear benefit).

### Decision — full re-ASR rebuild of broken transcriptions (2026-07-02)

**Context:** User chose the full-rebuild option after learning 382/398 transcriptions are truncated by
pre-cap giant chunks. Fix requires re-transcribing, which requires the source WAV (289 were deleted).

**Decisions:**
- **Rebuild via a dedicated resumable script** (`rebuild_transcriptions.py`) rather than ad-hoc
  commands: 382 files × multi-hour audio is a multi-hour/day job that will hit YouTube download
  failures (SABR/nsig, private/deleted videos), so it must survive restarts (skip already-rebuilt
  files by re-checking max chunk seconds) and continue past per-file failures.
- **Re-use `_normalize_title` (NFKC + alnum-only)** for the filename→videos.csv URL match — exact
  match misses ~30% because filenames substitute `/`→`⧸` (U+29F8) etc.
- **beam=5, self-consistency OFF for the bulk run** — beam is the quality win; self-consistency would
  double an already-huge compute bill for marginal gain at this scale.
- **Cleanup kept as a separate later stage** (Taiwan-LLM postprocess + CJK spacing) — decouples the
  slow GPU ASR from the LLM pass and lets each be re-run independently.

**Env correction:** all ASR/GPU/cleanup must run under `.venv/Scripts/python.exe`. The bare `python`
(`C:\Python314`) is CPU-only torch with no torchaudio; it had been silently running the Taiwan-LLM
cleanup on CPU (the apparent hang). Recorded in memory so it isn't rediscovered the hard way.
