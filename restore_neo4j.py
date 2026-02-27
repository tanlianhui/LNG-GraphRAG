#!/usr/bin/env python3
"""
Restore Neo4j database from ./neo4j folder
"""
import os
import subprocess
import sys
from pathlib import Path

# Configuration
CONTAINER_NAME = "lng-neo4j"
DUMP_DIR = "./neo4j"
DB_NAME = "neo4j"  # Community Edition uses "neo4j" as default
NEO4J_IMAGE = "neo4j:5.15-community"  # Match docker-compose

def check_docker_running(require_running: bool = False):
    """Check if Docker is running and container exists. If require_running, container must be up."""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        if CONTAINER_NAME not in (result.stdout or "").strip():
            print(f"❌ Container '{CONTAINER_NAME}' not found.")
            print(f"   Please start Neo4j first with: ./setup_neo4j.sh")
            return False
        if require_running:
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=True,
            )
            if CONTAINER_NAME not in (result.stdout or "").strip():
                print(f"❌ Container '{CONTAINER_NAME}' is not running.")
                print(f"   Start it with: docker start {CONTAINER_NAME}")
                return False
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error checking Docker: {e}")
        return False
    except FileNotFoundError:
        print("❌ Docker not found. Please install Docker.")
        return False


def _get_data_volume_name():
    """Get the Docker volume name mounted at /data for CONTAINER_NAME."""
    r = subprocess.run(
        [
            "docker", "inspect", CONTAINER_NAME,
            "--format", "{{range .Mounts}}{{if eq .Destination \"/data\"}}{{.Name}}{{end}}{{end}}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    name = (r.stdout or "").strip()
    if not name:
        raise RuntimeError("Could not find Neo4j data volume for container. Is it created by docker-compose?")
    return name

def _neo4j_status():
    """Return True if Neo4j server is running inside the container."""
    r = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "neo4j", "status"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return r.returncode == 0 and "running" in (r.stdout or "").lower()


def _stop_neo4j_in_container():
    """Stop the Neo4j server process inside the container (container keeps running)."""
    import time
    print("🛑 Stopping Neo4j server (container stays up)...")
    for attempt in range(4):
        subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "neo4j", "stop"],
            capture_output=True,
            timeout=30,
        )
        time.sleep(5)
        if not _neo4j_status():
            return True
        # Last resort: kill the Neo4j Java process so load can run
        if attempt >= 2:
            print("   Stopping Neo4j process directly...")
            r = subprocess.run(
                ["docker", "exec", CONTAINER_NAME, "sh", "-c", "pkill -f 'org.neo4j' || true"],
                capture_output=True,
                timeout=10,
            )
            time.sleep(5)
            if not _neo4j_status():
                return True
    return False


def find_dump_file(dump_path: Path, dump_file: str = None):
    """Find the dump file to restore"""
    if dump_file:
        # Use specified file
        dump_file_path = dump_path / dump_file
        if not dump_file_path.exists():
            print(f"❌ Dump file not found: {dump_file_path}")
            return None
        return dump_file_path
    
    # Try to find latest.dump symlink
    latest_link = dump_path / "latest.dump"
    if latest_link.exists() and latest_link.is_symlink():
        target = latest_link.resolve()
        if target.exists():
            print(f"📦 Found latest dump: {target}")
            return target
    
    # Find most recent dump file
    dump_files = sorted(dump_path.glob("neo4j_dump_*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)
    if dump_files:
        print(f"📦 Found most recent dump: {dump_files[0]}")
        return dump_files[0]
    
    print(f"❌ No dump files found in {dump_path}")
    return None

def _restore_in_container(dump_file: Path) -> bool:
    """Restore by stopping only the Neo4j server inside the container, then load, then start.
    Container stays running the whole time. Returns True on success."""
    dump_name = dump_file.name
    container_dump = f"/dumps/{DB_NAME}.dump"
    try:
        subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "mkdir", "-p", "/dumps"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["docker", "cp", str(dump_file), f"{CONTAINER_NAME}:{container_dump}"],
            check=True,
            capture_output=True,
        )
        if not _stop_neo4j_in_container():
            print("⚠️  Could not stop Neo4j server in container.")
            return False
        import time
        time.sleep(2)
        subprocess.run(
            [
                "docker", "exec", CONTAINER_NAME,
                "neo4j-admin", "database", "load", DB_NAME,
                "--from-path=/dumps",
                "--overwrite-destination=true",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "rm", "-f", container_dump],
            check=False,
            capture_output=True,
        )
        print("🚀 Starting Neo4j server...")
        r = subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "neo4j", "start"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0 and "already running" not in (r.stderr or r.stdout or "").lower():
            raise subprocess.CalledProcessError(r.returncode, r.args, r.stdout, r.stderr)
        print("✅ Database restored successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ In-container restore failed: {e}")
        if getattr(e, "stderr", None):
            print(f"   {e.stderr}")
        return False


def _restore_via_stop_container(dump_file: Path) -> bool:
    """Restore by stopping the whole container, loading in a one-off container, then starting again."""
    import time
    dump_path = dump_file.resolve().parent
    dump_name = dump_file.name
    try:
        volume_name = _get_data_volume_name()
        print("🛑 Stopping Neo4j container...")
        subprocess.run(
            ["docker", "stop", CONTAINER_NAME],
            check=True,
            capture_output=True,
            timeout=60,
        )
        time.sleep(2)
        print("🔄 Restoring database (one-off container)...")
        load_cmd = (
            'cp "/dumps/$DUMP_NAME" /dumps/neo4j.dump && '
            "neo4j-admin database load neo4j --from-path=/dumps --overwrite-destination=true"
        )
        subprocess.run(
            [
                "docker", "run", "--rm",
                "-e", f"DUMP_NAME={dump_name}",
                "-v", f"{volume_name}:/data",
                "-v", f"{dump_path}:/dumps",
                NEO4J_IMAGE,
                "sh", "-c", load_cmd,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        print("🚀 Starting Neo4j container...")
        subprocess.run(
            ["docker", "start", CONTAINER_NAME],
            check=True,
            capture_output=True,
            timeout=30,
        )
        print("✅ Database restored successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error restoring database: {e}")
        if getattr(e, "stderr", None):
            print(f"   Error output: {e.stderr}")
        try:
            subprocess.run(
                ["docker", "start", CONTAINER_NAME],
                check=False,
                capture_output=True,
                timeout=30,
            )
        except Exception:
            pass
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        try:
            subprocess.run(
                ["docker", "start", CONTAINER_NAME],
                check=False,
                capture_output=True,
                timeout=30,
            )
        except Exception:
            pass
        return False


def restore_database(dump_file: Path, stop_container: bool = False) -> bool:
    """Restore Neo4j database from dump.
    By default: stop only the Neo4j server inside the container, load, then start (container stays up).
    If stop_container=True or in-container fails: stop the whole container, load in one-off, start container."""
    print(f"📥 Restoring Neo4j database '{DB_NAME}' from {dump_file.name}...")
    if stop_container:
        return _restore_via_stop_container(dump_file)
    # Prefer in-container (stop Neo4j process only)
    if _restore_in_container(dump_file):
        return True
    print("   Falling back to stop-container method...")
    return _restore_via_stop_container(dump_file)

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Restore Neo4j database from dump. By default stops only the Neo4j server inside the container (container stays up)."
    )
    parser.add_argument(
        "--dump-file",
        type=str,
        help="Specific dump file to restore (default: latest or most recent)",
    )
    parser.add_argument(
        "--stop-container",
        action="store_true",
        help="Stop the whole Docker container to restore (use if in-container restore fails with 'database is in use')",
    )
    args = parser.parse_args()
    
    print("=" * 50)
    print("🎙️  LNG GraphRAG - Neo4j Database Restore")
    print("=" * 50)
    print()
    
    # Check Docker; for in-container restore the container must be running
    if not check_docker_running(require_running=not args.stop_container):
        sys.exit(1)
    
    # Find dump file
    dump_path = Path(DUMP_DIR)
    if not dump_path.exists():
        print(f"❌ Dump directory not found: {dump_path}")
        print(f"   Please run dump_neo4j.py first to create a dump.")
        sys.exit(1)
    
    dump_file = find_dump_file(dump_path, args.dump_file)
    if not dump_file:
        sys.exit(1)
    
    print()
    print(f"⚠️  WARNING: This will overwrite the current database '{DB_NAME}'!")
    response = input("   Are you sure you want to continue? (y/n): ")
    if response.lower() not in ['yes', 'y']:
        print("❌ Restore cancelled.")
        sys.exit(0)
    
    print()
    
    # Restore database (in-container by default; fallback to stop-container if that fails)
    success = restore_database(dump_file, stop_container=args.stop_container)
    
    if success:
        print()
        print("=" * 50)
        print("✅ Restore completed successfully!")
        print("=" * 50)
        print("⏳ Waiting for Neo4j to be ready...")
        
        # Wait for Neo4j to be ready
        import time
        max_attempts = 30
        for attempt in range(max_attempts):
            try:
                result = subprocess.run(
                    ["docker", "exec", CONTAINER_NAME, "cypher-shell", 
                     "-u", "neo4j", "-p", "lng-graphrag-password", "RETURN 1"],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    print("✅ Neo4j is ready!")
                    break
            except:
                pass
            
            if attempt < max_attempts - 1:
                print(f"   Attempt {attempt + 1}/{max_attempts}...")
                time.sleep(2)
        
        print()
        print("🌐 Neo4j Browser: http://localhost:17474 (or 7474 if using default ports)")
        return 0
    else:
        print()
        print("=" * 50)
        print("❌ Restore failed!")
        print("=" * 50)
        return 1

if __name__ == "__main__":
    sys.exit(main())

