# Claude Code — Project Rules

## Stack
- Backend: Flask + Neo4j (graph DB) + MySQL (auth/pipeline) + Docker Compose
- Web UI: Jinja2 templates (templates/)
- AI: Breeze-ASR-25 (Whisper-based Mandarin ASR), LangChain + Neo4j GraphRAG
- Python: standard venv / pip | Docker: `docker compose -f docker-compose.yml`

## Service ports (local)
| Service      | Port  | Notes                              |
|-------------|-------|------------------------------------|
| Flask app   | 5000  | `python launch_web.py`             |
| Neo4j HTTP  | 17474 | Browser: http://localhost:17474    |
| Neo4j Bolt  | 17687 | `bolt://localhost:17687`           |
| MySQL       | 3306  | User: lng_user / lng-graphrag-password |
| Adminer     | 8080  | MySQL admin UI                     |

## Public URL
- `https://your-domain.example.com` via Cloudflare Tunnel (tunnel ID: <your-tunnel-id>)
- Start with: `bash boot.sh`
- First-time setup: `bash boot.sh setup`

## Documentation (always do this after every change)
After completing any feature, fix, or config change:
1. **`CHANGES.md`** — append a dated section (`## YYYY-MM-DD`) describing what changed and how.
2. **`decision.md`** — append an entry explaining *why* the decision was made (tradeoffs, context, alternatives rejected).

Never skip these updates, even for small changes.

## Git flow (FDD — Feature-Driven Development)
Branch naming and merge rules:

| Work type | Branch | Merges into |
|---|---|---|
| New feature | `feature/<short-name>` | `dev` |
| Release prep | `release/<version>` | `main` + `dev` |
| Hotfix | `hotfix/<short-name>` | `main` + `dev` |
| Bugfix | `bugfix/<short-name>` | `dev` |

Commit message format:
```
<type>(<scope>): <imperative summary>

<optional body — what and why, not how>
```
Types: `feat`, `fix`, `hotfix`, `refactor`, `docs`, `chore`, `test`

**Always ask the user for permission before committing or pushing.**

## Code style
- Keep changes minimal and focused — no unrequested refactors or extra comments.
- No security vulnerabilities (no SQL injection, XSS, command injection, etc.).
- Validate only at system boundaries (user input, external APIs).
