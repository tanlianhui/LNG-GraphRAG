#!/usr/bin/env python3
"""
Automatically restore Neo4j database from dump if available
This script can be run after Neo4j container starts to restore from the latest dump
"""
import os
import subprocess
import sys
from pathlib import Path
import time

# Configuration
CONTAINER_NAME = "lng-neo4j"
DUMP_DIR = "./neo4j"
DB_NAME = "neo4j"  # Community Edition uses "neo4j" as default

def check_container_running():
    """Check if container is running"""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True
        )
        return CONTAINER_NAME in result.stdout
    except:
        return False

def wait_for_neo4j_ready(max_attempts=30):
    """Wait for Neo4j to be ready"""
    print("⏳ Waiting for Neo4j to be ready...")
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
                return True
        except:
            pass
        
        if attempt < max_attempts - 1:
            print(f"   Attempt {attempt + 1}/{max_attempts}...")
            time.sleep(2)
    
    return False

def find_latest_dump(dump_path: Path):
    """Find the latest dump file"""
    # Try latest.dump symlink first
    latest_link = dump_path / "latest.dump"
    if latest_link.exists() and latest_link.is_symlink():
        target = latest_link.resolve()
        if target.exists():
            return target
    
    # Find most recent dump file
    dump_files = sorted(dump_path.glob("neo4j_dump_*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)
    if dump_files:
        return dump_files[0]
    
    return None

def check_database_empty():
    """Check if database is empty (no documents)"""
    try:
        result = subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "cypher-shell", 
             "-u", "neo4j", "-p", "lng-graphrag-password",
             "MATCH (d:Document) RETURN count(d) as count"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            # Parse output to get count
            for line in result.stdout.split('\n'):
                if '|' in line and 'count' not in line.lower():
                    try:
                        count = int(line.split('|')[1].strip())
                        return count == 0
                    except:
                        pass
        return True  # Assume empty if we can't check
    except:
        return True  # Assume empty if check fails

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Auto-restore Neo4j database from dump")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force restore even if database is not empty"
    )
    parser.add_argument(
        "--skip-empty-check",
        action="store_true",
        help="Skip empty database check (assume database needs restore)"
    )
    args = parser.parse_args()
    
    print("=" * 50)
    print("🎙️  LNG GraphRAG - Auto Restore Neo4j")
    print("=" * 50)
    print()
    
    # Check if container is running
    if not check_container_running():
        print(f"❌ Container '{CONTAINER_NAME}' is not running.")
        print(f"   Please start Neo4j first with: ./setup_neo4j.sh")
        sys.exit(1)
    
    # Wait for Neo4j to be ready
    if not wait_for_neo4j_ready():
        print("❌ Neo4j is not ready. Please check container logs.")
        sys.exit(1)
    
    # Check if database is empty (unless forced or skip check)
    if not args.force and not args.skip_empty_check:
        print("🔍 Checking if database is empty...")
        is_empty = check_database_empty()
        if not is_empty:
            print("ℹ️  Database is not empty. Skipping restore.")
            print("   Use --force to restore anyway, or --skip-empty-check to skip this check.")
            return 0
    
    # Find dump file
    dump_path = Path(DUMP_DIR)
    if not dump_path.exists():
        print(f"ℹ️  No dump directory found: {dump_path}")
        print(f"   Skipping restore. Database will start empty.")
        return 0
    
    dump_file = find_latest_dump(dump_path)
    if not dump_file:
        print(f"ℹ️  No dump files found in {dump_path}")
        print(f"   Skipping restore. Database will start empty.")
        return 0
    
    print(f"📦 Found dump file: {dump_file.name}")
    print()
    
    # Import restore functions from restore_neo4j.py
    try:
        # Add current directory to path to import restore_neo4j
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from restore_neo4j import stop_neo4j, restore_database
        
        # Restore database
        print("🔄 Restoring database from dump...")
        success = restore_database(dump_file)
        
        if success:
            print()
            print("⏳ Waiting for Neo4j to be ready after restore...")
            if wait_for_neo4j_ready():
                print("✅ Auto-restore completed successfully!")
                return 0
            else:
                print("⚠️  Restore completed but Neo4j may not be fully ready yet.")
                return 0
        else:
            print("❌ Auto-restore failed!")
            return 1
    except ImportError as e:
        print(f"⚠️  Could not import restore functions: {e}")
        print("   Falling back to calling restore_neo4j.py directly...")
        result = subprocess.run(
            [sys.executable, "restore_neo4j.py", "--dump-file", dump_file.name],
            input="yes\n" if args.force else None
        )
        return result.returncode

if __name__ == "__main__":
    sys.exit(main())

