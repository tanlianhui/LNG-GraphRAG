# Deployment Guide — LNG GraphRAG

## Architecture

```
[Your PC (on)]
  Docker: Neo4j (17687) + MySQL (3306)
  Flask web app (5000)  ─── tunnel ──────▶  your-domain.example.com
```

The entire stack runs locally. Cloudflare Tunnel provides public HTTPS access.  
When PC is **off**, the service is unavailable.

---

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| Docker Desktop | Neo4j + MySQL | https://www.docker.com/products/docker-desktop |
| Python 3.10+ | Flask app | https://www.python.org |
| cloudflared | Tunnel | https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads |
| Git Bash | Runs boot.sh | https://git-scm.com |

---

## One-time Setup

### 1. Copy and fill in `.env`
```bash
cp .env.example .env
# Set at minimum:
#   NEO4J_URI=bolt://localhost:17687
#   OPENAI_API_KEY=sk-...   (if using OpenAI embeddings/LLM)
```

### 2. Start Docker services
```bash
docker compose up -d
```
Wait ~30 seconds for Neo4j to finish initialising before running the app.

### 3. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Cloudflare Tunnel

The tunnel `lng-graphrag` (ID: `<your-tunnel-id>`) is already created.  
The config file is at `cloudflared-config.yml` in this directory.

Register the DNS route (already done, but safe to re-run):
```bash
cloudflared tunnel route dns <your-tunnel-id> your-domain.example.com
```

---

## Running the services

### Start everything (manual)
```bash
bash boot.sh
```
This starts Docker containers, waits for health, starts Flask on :5000, and runs the Cloudflare Tunnel.

### Auto-start at Windows login
A startup script is installed at:
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\lng-graphrag.vbs
```
Logs are written to `E:\projects\LNG-GraphRAG\boot.log`.

---

## URLs

| Service | URL |
|---------|-----|
| Web app (public) | https://your-domain.example.com |
| Web app (local) | http://localhost:5000 |
| Neo4j Browser | http://localhost:17474 |
| Adminer (MySQL) | http://localhost:8080 |

---

## Testing after setup

1. Start services: `bash boot.sh`
2. Open http://localhost:5000 — the dashboard should load
3. Open https://your-domain.example.com — same dashboard via tunnel
4. Run a query to verify Neo4j is connected
5. Check `boot.log` if anything fails: `tail -f boot.log`

---

## Stopping

Press **Ctrl+C** in the terminal running `boot.sh`.  
Docker containers continue running (use `docker compose stop` to stop them too).
