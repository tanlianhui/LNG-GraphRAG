#!/usr/bin/env python3
"""
Dump Neo4j database to ./neo4j folder
"""
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

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

def create_dump_directory():
    """Create dump directory if it doesn't exist"""
    dump_path = Path(DUMP_DIR)
    dump_path.mkdir(parents=True, exist_ok=True)
    return dump_path

def dump_database(dump_path: Path):
    """Dump Neo4j database using neo4j-admin"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_file = dump_path / f"neo4j_dump_{timestamp}.dump"
    
    print(f"📦 Dumping Neo4j database '{DB_NAME}' to {dump_file}...")
    
    try:
        # Use neo4j-admin database dump command
        # Note: For Community Edition, we use the default "neo4j" database
        cmd = [
            "docker", "exec", CONTAINER_NAME,
            "neo4j-admin", "database", "dump", DB_NAME,
            "--to-path=/dumps",
            f"--overwrite-destination=true"
        ]
        
        # First, create /dumps directory in container if it doesn't exist
        subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "mkdir", "-p", "/dumps"],
            check=True,
            capture_output=True
        )
        
        # Run dump command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Copy dump file from container to host
        container_dump_path = f"/dumps/{DB_NAME}.dump"
        subprocess.run(
            ["docker", "cp", f"{CONTAINER_NAME}:{container_dump_path}", str(dump_file)],
            check=True,
            capture_output=True
        )
        
        # Clean up container dump file
        subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "rm", "-f", container_dump_path],
            check=False,
            capture_output=True
        )
        
        print(f"✅ Database dumped successfully to: {dump_file}")
        
        # Create a symlink to latest dump
        latest_link = dump_path / "latest.dump"
        if latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(dump_file.name)
        print(f"✅ Created symlink: {latest_link} -> {dump_file.name}")
        
        return dump_file
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error dumping database: {e}")
        if e.stderr:
            print(f"   Error output: {e.stderr}")
        return None

def main():
    """Main function"""
    print("=" * 50)
    print("🎙️  LNG GraphRAG - Neo4j Database Dump")
    print("=" * 50)
    print()
    
    # Check Docker
    if not check_docker_running():
        sys.exit(1)
    
    # Create dump directory
    dump_path = create_dump_directory()
    print(f"📁 Dump directory: {dump_path.absolute()}")
    print()
    
    # Dump database
    dump_file = dump_database(dump_path)
    
    if dump_file:
        print()
        print("=" * 50)
        print("✅ Dump completed successfully!")
        print("=" * 50)
        print(f"📦 Dump file: {dump_file}")
        print(f"📁 Location: {dump_path.absolute()}")
        print()
        print("💡 To restore this dump, run:")
        print(f"   python restore_neo4j.py")
        return 0
    else:
        print()
        print("=" * 50)
        print("❌ Dump failed!")
        print("=" * 50)
        return 1

if __name__ == "__main__":
    sys.exit(main())

