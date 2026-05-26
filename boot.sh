#!/usr/bin/env bash
# boot.sh — LNG GraphRAG
#
# Usage:
#   bash boot.sh          Start all services (Docker + web app + Cloudflare tunnel)
#   bash boot.sh setup    First-time tunnel registration

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Force UTF-8 output for Python on non-UTF-8 terminals (e.g., cp950 on Windows)
export PYTHONIOENCODING=utf-8

# Ollama: port 11434 is in Windows excluded range on this machine; use 11700
export OLLAMA_HOST=http://0.0.0.0:11700

TUNNEL_NAME="lng-graphrag"
APP_URL="https://your-domain.example.com"
CRED_FILE="$HOME/.cloudflared/lng-graphrag-tunnel.json"
CONFIG_FILE="$ROOT/cloudflared-config.yml"

echo ""
echo "  LNG GraphRAG  |  $(date)"
echo "  ============================================================"
echo ""

# ---------------------------------------------------------------------------
# Locate python
# ---------------------------------------------------------------------------
PYTHON=""
# Prefer venv Python so all dependencies are available
for candidate in \
    "$ROOT/.venv/Scripts/python" \
    "$ROOT/venv/Scripts/python" \
    python python3; do
    if [ -f "$candidate" ] || command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "  [ERROR] Python not found." >&2
    exit 1
fi
echo "  [OK] python      : $($PYTHON --version)"

# ---------------------------------------------------------------------------
# Locate cloudflared
# ---------------------------------------------------------------------------
CLOUDFLARED=""
if command -v cloudflared &>/dev/null; then
    CLOUDFLARED=cloudflared
elif [ -f "/c/Windows/System32/cloudflared.exe" ]; then
    CLOUDFLARED="/c/Windows/System32/cloudflared.exe"
fi

if [ -z "$CLOUDFLARED" ]; then
    echo "  [WARN] cloudflared not found — tunnel will not start."
    echo "         Download: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
else
    echo "  [OK] cloudflared : $CLOUDFLARED"
fi

# ---------------------------------------------------------------------------
# SETUP MODE  —  bash boot.sh setup
# ---------------------------------------------------------------------------
if [ "${1:-}" = "setup" ]; then
    echo ""
    echo "  [SETUP] Creating Cloudflare Tunnel '$TUNNEL_NAME'..."

    if [ -z "$CLOUDFLARED" ]; then
        echo "  [ERROR] cloudflared required for setup." >&2
        exit 1
    fi

    # Check login
    if [ ! -f "$HOME/.cloudflared/cert.pem" ]; then
        echo "  [INFO] Logging in to Cloudflare..."
        "$CLOUDFLARED" tunnel login
    fi

    # Create tunnel (skips if already exists)
    if ! "$CLOUDFLARED" tunnel info "$TUNNEL_NAME" &>/dev/null; then
        "$CLOUDFLARED" tunnel create "$TUNNEL_NAME"
        echo "  [OK] Tunnel created"
    else
        echo "  [OK] Tunnel already exists"
    fi

    # Find credential file
    TUNNEL_ID=$("$CLOUDFLARED" tunnel info "$TUNNEL_NAME" 2>&1 | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
    if [ -n "$TUNNEL_ID" ]; then
        cp "$HOME/.cloudflared/${TUNNEL_ID}.json" "$CRED_FILE" 2>/dev/null || true
        # Update config with correct tunnel ID
        sed -i "s/TUNNEL_ID_PLACEHOLDER/${TUNNEL_ID}/" "$CONFIG_FILE" 2>/dev/null || true
    fi

    # Register DNS
    "$CLOUDFLARED" tunnel route dns "$TUNNEL_NAME" your-domain.example.com
    echo "  [OK] DNS route registered: your-domain.example.com"

    echo ""
    echo "  Setup complete. Run 'bash boot.sh' to start all services."
    echo ""
    exit 0
fi

# ---------------------------------------------------------------------------
# Check .env
# ---------------------------------------------------------------------------
if [ ! -f "$ROOT/.env" ]; then
    echo "  [WARN] .env not found — app may not start correctly."
    echo "         Copy .env.example to .env and fill in your values."
    echo ""
fi

# ---------------------------------------------------------------------------
# Start Docker services (Neo4j + MySQL)
# ---------------------------------------------------------------------------
echo "  Starting Docker containers..."
if command -v docker &>/dev/null; then
    if docker compose -f "$ROOT/docker-compose.yml" up -d 2>&1; then
        echo "  [OK] Docker containers started"
        echo "  [INFO] Waiting 15s for Neo4j and MySQL to become healthy..."
        sleep 15
    else
        echo "  [WARN] Docker compose failed (is Docker Desktop running?) — Neo4j/MySQL unavailable."
        echo "         GraphRAG and auth features will not work, but basic serving continues."
    fi
else
    echo "  [WARN] docker not found — Neo4j/MySQL containers will not start."
fi

# ---------------------------------------------------------------------------
# Cleanup on Ctrl+C
# ---------------------------------------------------------------------------
PIDS=()
cleanup() {
    echo ""
    echo "  Stopping services..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    echo "  Done."
}
trap cleanup INT TERM

# ---------------------------------------------------------------------------
# Launch Ollama (embeddings server)
# ---------------------------------------------------------------------------
OLLAMA=""
for candidate in ollama "D:/Ollama/ollama.exe"; do
    if command -v "$candidate" &>/dev/null || [ -f "$candidate" ]; then
        OLLAMA="$candidate"
        break
    fi
done
if [ -n "$OLLAMA" ]; then
    OLLAMA_PORT="${OLLAMA_HOST##*:}"
    OLLAMA_PORT="${OLLAMA_PORT:-11700}"
    if curl -s "http://localhost:${OLLAMA_PORT}/api/tags" >/dev/null 2>&1; then
        echo "  [OK] Ollama already running"
    else
        echo "  Launching Ollama    (embeddings)  ..."
        "$OLLAMA" serve >/dev/null 2>&1 &
        PIDS+=($!)
        sleep 3
        echo "  [OK] Ollama started"
    fi
else
    echo "  [WARN] ollama not found — nomic embeddings will not work."
fi

# ---------------------------------------------------------------------------
# Launch Flask web app
# ---------------------------------------------------------------------------
echo "  Launching Web App   (Flask)      ..."
cd "$ROOT"
"$PYTHON" launch_web.py &
PIDS+=($!)

# ---------------------------------------------------------------------------
# Launch VOD scheduler (fetch new live stream replays periodically)
# ---------------------------------------------------------------------------
echo "  Launching Scheduler (VOD fetch)  ..."
"$PYTHON" "$ROOT/scheduler.py" &
PIDS+=($!)

# ---------------------------------------------------------------------------
# Launch Cloudflare Tunnel
# ---------------------------------------------------------------------------
if [ -n "$CLOUDFLARED" ] && [ -f "$CONFIG_FILE" ]; then
    echo "  Launching Tunnel    (cloudflared) ..."
    "$CLOUDFLARED" tunnel --config "$CONFIG_FILE" run "$TUNNEL_NAME" &
    PIDS+=($!)
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "  ============================================================"
echo "   Local"
echo "     Web App   >  http://localhost:5000"
echo "     Neo4j     >  http://localhost:17474"
echo ""
echo "   Public (Cloudflare Tunnel)"
echo "     App       >  $APP_URL"
echo "  ============================================================"
echo ""
echo "  Press Ctrl+C to stop."
echo "  First time? Run:  bash boot.sh setup"
echo ""

wait "${PIDS[@]}"
