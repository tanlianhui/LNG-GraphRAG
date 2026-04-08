# Decision Log

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
