#!/usr/bin/env python3
"""
Load transcriptions into Neo4j using GraphRAG
"""
import os
import sys
import asyncio
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# Set OpenAI API key if not already set (needed for ChatOpenAI LLM in concept generation and for openai embeddings when used)
if "OPENAI_API_KEY" not in os.environ:
    print("⚠️  Warning: OPENAI_API_KEY not set. Please set it before running:")
    print("   export OPENAI_API_KEY='your-api-key'")
    print("   Note: OpenAI is used for LLM (concept generation) and optionally for openai_embeddings (--embedding openai|both)")
    sys.exit(1)

# Add graphrag directory to path
graphrag_path = Path(__file__).parent / "graphrag"
if graphrag_path.exists():
    sys.path.insert(0, str(graphrag_path.parent))

from graphrag.own_graph_rag import (
    load_files_neo4j_graphrag,
    prepare_database,
    extract_text_from_file
)

# Configuration
DB_NAME = "lng_transcriptions"
TRANSCRIPTIONS_DIR = Path("./transcriptions")
CLEAN_DB = False  # Set to True to clean existing database


async def load_transcription_file(file_path: Path, db_name: str, embedding_backend: str = "nomic"):
    """Load a single transcription file into Neo4j.
    embedding_backend: 'nomic' | 'openai' | 'both' — stored as nomic_embeddings and/or openai_embeddings on nodes."""
    try:
        print(f"\n{'='*60}")
        print(f"📄 Processing: {file_path.name}")
        print(f"{'='*60}")
        
        # Get video URL from CSV if available
        url_mapping = {}
        csv_path = Path("./VODs/videos.csv")
        if csv_path.exists():
            import csv
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    title = row.get('title', '')
                    url = row.get('url', '')
                    # Match transcription filename (remove _combined.txt)
                    transcription_name = file_path.stem.replace('_combined', '')
                    if title == transcription_name or file_path.stem.startswith(title):
                        url_mapping[file_path.name] = url
                        break
        
        # Load file into Neo4j
        await load_files_neo4j_graphrag(
            path=str(file_path),
            db_name=db_name,
            node_labels=[],  # Add custom node labels if needed
            rel_labels=[],  # Add custom relationship labels if needed
            prompt_template="",  # Add custom prompt template if needed
            generate_concepts=True,  # Generate concepts from transcriptions
            background_tasks=None,  # Run synchronously
            url_mapping_dict=url_mapping if url_mapping else None,
            embedding_backend=embedding_backend,
        )
        
        print(f"✅ Successfully loaded: {file_path.name}")
        return True
        
    except Exception as e:
        print(f"❌ Error loading {file_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main(embedding_backend: str = "nomic", clean_db: bool = False):
    """Main function to load all transcriptions.
    embedding_backend: 'nomic' | 'openai' | 'both' — which embeddings to store (nomic_embeddings, openai_embeddings).
    clean_db: if True, wipe existing graph data before loading (ensures only nomic_embeddings/openai_embeddings, no legacy chunk_embeddings)."""
    print("="*60)
    print("🎙️  LNG Transcription GraphRAG Loader")
    print("="*60)
    print(f"📌 Embedding backend: {embedding_backend} (node properties: nomic_embeddings, openai_embeddings)")
    if clean_db:
        print("📌 Clean DB: yes (existing graph data will be removed first)")
    
    # Check if transcriptions directory exists
    if not TRANSCRIPTIONS_DIR.exists():
        print(f"❌ Transcriptions directory not found: {TRANSCRIPTIONS_DIR}")
        sys.exit(1)
    
    # Get all transcription files
    transcription_files = list(TRANSCRIPTIONS_DIR.glob("*_combined.txt"))
    
    if not transcription_files:
        print(f"❌ No transcription files found in {TRANSCRIPTIONS_DIR}")
        sys.exit(1)
    
    print(f"\n📊 Found {len(transcription_files)} transcription files")
    
    # Check Neo4j connection first
    print(f"\n🔍 Checking Neo4j connection...")
    max_retries = 10
    retry_count = 0
    neo4j_ready = False
    
    while retry_count < max_retries:
        try:
            import neo4j
            NEO4J_URI = f'bolt://{os.environ.get("NEO4J_IP", "localhost")}:7687'
            NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "neo4j")
            NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "lng-graphrag-password")
            
            driver = neo4j.GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
                connection_timeout=5
            )
            driver.verify_connectivity()
            driver.close()
            neo4j_ready = True
            print(f"✅ Neo4j is ready!")
            break
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                print(f"   Waiting for Neo4j... ({retry_count}/{max_retries})")
                await asyncio.sleep(3)
            else:
                print(f"❌ Neo4j is not available after {max_retries} attempts")
                print(f"💡 Please start Neo4j first: ./setup_neo4j.sh")
                print(f"   Or check if it's running: docker ps | grep neo4j")
                sys.exit(1)
    
    # Prepare database (Community Edition has only default DB "neo4j"; we use it for "lng_transcriptions")
    print(f"\n🔧 Preparing Neo4j (logical database: '{DB_NAME}')...")
    try:
        result = prepare_database(DB_NAME, clean_old_data=clean_db or CLEAN_DB)
        print(f"✅ {result}")
        # Clarify for Docker/Community users: data lives in default database "neo4j"
        from graphrag.own_graph_rag import get_database_name
        actual = get_database_name(DB_NAME)
        if actual != DB_NAME:
            print(f"   ℹ️  Using default database '{actual}' (Community Edition has no separate '{DB_NAME}' database).")
    except Exception as e:
        print(f"❌ Error preparing database: {e}")
        sys.exit(1)
    
    # Load each transcription file
    print(f"\n🚀 Starting to load transcriptions...")
    print(f"💡 This may take a while depending on the number of files and API rate limits")
    
    successful = 0
    failed = 0
    
    for i, file_path in enumerate(transcription_files, 1):
        print(f"\n[{i}/{len(transcription_files)}] Loading: {file_path.name}")
        
        success = await load_transcription_file(file_path, DB_NAME, embedding_backend=embedding_backend)
        
        if success:
            successful += 1
        else:
            failed += 1
        
        # Add a small delay to avoid rate limiting
        if i < len(transcription_files):
            await asyncio.sleep(2)
    
    # Summary
    print("\n" + "="*60)
    print("📊 Loading Summary")
    print("="*60)
    print(f"✅ Successful: {successful}")
    print(f"❌ Failed: {failed}")
    print(f"📄 Total: {len(transcription_files)}")
    from graphrag.own_graph_rag import get_database_name
    actual_db = get_database_name(DB_NAME)
    print(f"\n💡 Data is in Neo4j database '{actual_db}' (logical name: {DB_NAME}). Ready for queries!")
    print(f"🌐 Access Neo4j Browser at: http://localhost:7474")
    print(f"🔌 Bolt connection: bolt://localhost:7687")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Load transcriptions into Neo4j with embeddings")
    parser.add_argument(
        "--embedding",
        choices=["nomic", "openai", "both"],
        default="nomic",
        help="Which embeddings to compute and store: nomic_embeddings, openai_embeddings, or both (default: nomic)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Wipe existing graph data before loading (use once to remove old chunk_embeddings and reload with nomic/openai)",
    )
    args = parser.parse_args()
    try:
        asyncio.run(main(embedding_backend=args.embedding, clean_db=args.clean))
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

