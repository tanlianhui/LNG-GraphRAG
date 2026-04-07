# Decision Log

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
