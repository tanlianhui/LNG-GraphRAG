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

def check_docker_running():
    """Check if Docker is running and container exists"""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True
        )
        if CONTAINER_NAME not in result.stdout:
            print(f"❌ Container '{CONTAINER_NAME}' not found.")
            print(f"   Please start Neo4j first with: ./setup_neo4j.sh")
            return False
        
        # Check if container is running
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True
        )
        if CONTAINER_NAME not in result.stdout:
            print(f"❌ Container '{CONTAINER_NAME}' is not running.")
            print(f"   Please start it with: docker start {CONTAINER_NAME}")
            return False
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error checking Docker: {e}")
        return False
    except FileNotFoundError:
        print("❌ Docker not found. Please install Docker.")
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

def stop_neo4j():
    """Stop Neo4j service in container"""
    print("🛑 Stopping Neo4j service...")
    try:
        subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "neo4j", "stop"],
            check=True,
            capture_output=True,
            timeout=30
        )
        # Wait a bit for Neo4j to fully stop
        import time
        time.sleep(3)
        return True
    except subprocess.TimeoutExpired:
        print("⚠️  Neo4j stop command timed out, continuing...")
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Error stopping Neo4j (may already be stopped): {e}")
        return True

def restore_database(dump_file: Path):
    """Restore Neo4j database from dump file"""
    print(f"📥 Restoring Neo4j database '{DB_NAME}' from {dump_file.name}...")
    
    try:
        # Create /dumps directory in container
        subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "mkdir", "-p", "/dumps"],
            check=True,
            capture_output=True
        )
        
        # Copy dump file to container
        container_dump_path = f"/dumps/{DB_NAME}.dump"
        print(f"📤 Copying dump file to container...")
        subprocess.run(
            ["docker", "cp", str(dump_file), f"{CONTAINER_NAME}:{container_dump_path}"],
            check=True,
            capture_output=True
        )
        
        # Stop Neo4j before restore
        stop_neo4j()
        
        # Restore database using neo4j-admin
        print(f"🔄 Restoring database...")
        cmd = [
            "docker", "exec", CONTAINER_NAME,
            "neo4j-admin", "database", "load", DB_NAME,
            "--from-path=/dumps",
            f"--overwrite-destination=true"
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Clean up container dump file
        subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "rm", "-f", container_dump_path],
            check=False,
            capture_output=True
        )
        
        # Start Neo4j
        print(f"🚀 Starting Neo4j service...")
        subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "neo4j", "start"],
            check=True,
            capture_output=True,
            timeout=30
        )
        
        print(f"✅ Database restored successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error restoring database: {e}")
        if e.stderr:
            print(f"   Error output: {e.stderr}")
        if e.stdout:
            print(f"   Output: {e.stdout}")
        
        # Try to start Neo4j even if restore failed
        try:
            subprocess.run(
                ["docker", "exec", CONTAINER_NAME, "neo4j", "start"],
                check=False,
                capture_output=True,
                timeout=30
            )
        except:
            pass
        
        return False

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Restore Neo4j database from dump")
    parser.add_argument(
        "--dump-file",
        type=str,
        help="Specific dump file to restore (default: latest or most recent)"
    )
    args = parser.parse_args()
    
    print("=" * 50)
    print("🎙️  LNG GraphRAG - Neo4j Database Restore")
    print("=" * 50)
    print()
    
    # Check Docker
    if not check_docker_running():
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
    response = input("   Are you sure you want to continue? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("❌ Restore cancelled.")
        sys.exit(0)
    
    print()
    
    # Restore database
    success = restore_database(dump_file)
    
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
        print("🌐 Neo4j Browser: http://localhost:7474")
        return 0
    else:
        print()
        print("=" * 50)
        print("❌ Restore failed!")
        print("=" * 50)
        return 1

if __name__ == "__main__":
    sys.exit(main())

