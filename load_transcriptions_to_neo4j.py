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

# Set OpenAI API key if not already set (still needed for ChatOpenAI LLM in concept generation)
if "OPENAI_API_KEY" not in os.environ:
    print("⚠️  Warning: OPENAI_API_KEY not set. Please set it before running:")
    print("   export OPENAI_API_KEY='your-api-key'")
    print("   Note: OpenAI is used for LLM (concept generation), while Ollama handles embeddings")
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


async def load_transcription_file(file_path: Path, db_name: str):
    """Load a single transcription file into Neo4j"""
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
            url_mapping_dict=url_mapping if url_mapping else None
        )
        
        print(f"✅ Successfully loaded: {file_path.name}")
        return True
        
    except Exception as e:
        print(f"❌ Error loading {file_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main function to load all transcriptions"""
    print("="*60)
    print("🎙️  LNG Transcription GraphRAG Loader")
    print("="*60)
    
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
    
    # Prepare database
    print(f"\n🔧 Preparing Neo4j database '{DB_NAME}'...")
    try:
        result = prepare_database(DB_NAME, clean_old_data=CLEAN_DB)
        print(f"✅ {result}")
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
        
        success = await load_transcription_file(file_path, DB_NAME)
        
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
    print(f"\n💡 Database '{DB_NAME}' is ready for queries!")
    print(f"🌐 Access Neo4j Browser at: http://localhost:7474")
    print(f"🔌 Bolt connection: bolt://localhost:7687")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

