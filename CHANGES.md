# Changes

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
