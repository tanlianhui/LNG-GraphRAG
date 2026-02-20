#!/usr/bin/env python3
"""
Ensure Neo4j is running, then load all transcriptions with embeddings into Neo4j.
Supports --embedding nomic | openai | both; stored as nomic_embeddings and/or openai_embeddings on Chunk/Concept nodes.
"""
import os
import sys
import subprocess
import asyncio
import time
from pathlib import Path

# Load .env before any imports that use it
from dotenv import load_dotenv
load_dotenv()


def docker_available() -> bool:
    """Check if Docker daemon is reachable."""
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def neo4j_container_running() -> bool:
    """Check if lng-neo4j container is running."""
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}", "--filter", "name=lng-neo4j"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return "lng-neo4j" in (r.stdout or "")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def start_neo4j() -> bool:
    """Start Neo4j via docker-compose. Returns True if started or already running."""
    if neo4j_container_running():
        return True
    compose = "docker compose" if subprocess.run(["docker", "compose", "version"], capture_output=True).returncode == 0 else "docker-compose"
    try:
        subprocess.run(
            [compose.split()[0], "compose", "up", "-d"] if compose.startswith("docker compose") else [compose, "up", "-d"],
            cwd=Path(__file__).parent,
            check=True,
            capture_output=True,
            timeout=120,
        )
    except Exception:
        try:
            subprocess.run(
                ["./setup_neo4j.sh"],
                cwd=Path(__file__).parent,
                shell=True,
                timeout=120,
            )
        except Exception:
            pass
    for _ in range(30):
        if neo4j_container_running():
            return True
        time.sleep(2)
    return False


def ensure_nomic_model() -> None:
    """Ensure Ollama has nomic-embed-text (pull if missing)."""
    try:
        r = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if "nomic-embed-text" in (r.stdout or ""):
            return
        print("📥 Pulling Ollama model nomic-embed-text (one-time)...")
        subprocess.run(
            ["ollama", "pull", "nomic-embed-text"],
            cwd=Path(__file__).parent,
            timeout=300,
        )
    except FileNotFoundError:
        print("⚠️  ollama not found in PATH; ensure Ollama is installed and 'ollama pull nomic-embed-text' has been run.")
    except subprocess.TimeoutExpired:
        print("⚠️  ollama pull timed out; if the model is already present, loading will still work.")


async def main_async(embedding_backend: str = "nomic", clean_db: bool = False, dump_after: bool = False) -> None:
    print("=" * 60)
    print("🎙️  LNG Transcriptions → Embeddings → Neo4j")
    print("=" * 60)
    print(f"📌 Embedding: {embedding_backend} (node properties: nomic_embeddings, openai_embeddings)")
    if clean_db:
        print("📌 Clean DB: yes (existing graph data will be removed first)")

    if not docker_available():
        print("❌ Docker is not running or not available.")
        print("   Start Docker Desktop (or the Docker daemon), then run this script again.")
        sys.exit(1)

    if not neo4j_container_running():
        print("🚀 Starting Neo4j (docker)...")
        try:
            compose_cmd = ["docker", "compose", "up", "-d"]
            if subprocess.run(["docker", "compose", "version"], capture_output=True).returncode != 0:
                compose_cmd = ["docker-compose", "up", "-d"]
            subprocess.run(compose_cmd, cwd=Path(__file__).parent, check=True, timeout=90)
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to start Neo4j: {e}")
            sys.exit(1)
        # Wait for Neo4j to accept connections
        for i in range(30):
            await asyncio.sleep(2)
            if neo4j_container_running():
                print("⏳ Waiting for Neo4j to be ready...")
                await asyncio.sleep(5)
                break
        if not neo4j_container_running():
            print("❌ Neo4j container did not start. Run: ./setup_neo4j.sh")
            sys.exit(1)
    else:
        print("✅ Neo4j container is already running.")

    if embedding_backend in ("nomic", "both"):
        ensure_nomic_model()

    # Delegate to the existing loader (embedding_backend → nomic_embeddings and/or openai_embeddings)
    from load_transcriptions_to_neo4j import main as load_main
    await load_main(embedding_backend=embedding_backend, clean_db=clean_db)

    # So you never have to re-run embeddings after a Neo4j rebuild: dump now, restore later.
    print("\n" + "=" * 60)
    print("💾 Never re-run embeddings after Neo4j rebuild")
    print("=" * 60)
    print("  1. Run a dump now (recommended):  python dump_neo4j.py")
    print("  2. After any Neo4j Docker rebuild (new container/volume):  python restore_neo4j.py")
    print("     Do NOT run this embedding script again — restore brings back the graph with embeddings.")
    print("  3. To keep data across rebuilds without restore: avoid 'docker compose down -v' (keeps neo4j_data volume).")
    if dump_after:
        print("\n📦 Running dump_neo4j.py now...")
        try:
            subprocess.run(
                [sys.executable, str(Path(__file__).parent / "dump_neo4j.py")],
                cwd=Path(__file__).parent,
                check=True,
                timeout=300,
            )
            print("✅ Dump completed. After Neo4j rebuild, run: python restore_neo4j.py")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"⚠️  Dump failed or skipped: {e}. Run manually: python dump_neo4j.py")
    print("=" * 60 + "\n")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Ensure Neo4j is running and load transcriptions with embeddings (nomic and/or openai)."
    )
    parser.add_argument(
        "--embedding",
        choices=["nomic", "openai", "both"],
        default="nomic",
        help="Which embeddings to store on nodes: nomic_embeddings, openai_embeddings, or both (default: nomic)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Wipe existing graph data before loading (removes old chunk_embeddings; reload with nomic/openai)",
    )
    parser.add_argument(
        "--dump-after",
        action="store_true",
        help="Run dump_neo4j.py after load so you can restore after Neo4j rebuild without re-running embeddings",
    )
    args = parser.parse_args()
    asyncio.run(main_async(embedding_backend=args.embedding, clean_db=args.clean, dump_after=args.dump_after))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
