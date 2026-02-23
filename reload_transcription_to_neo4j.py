#!/usr/bin/env python3
"""
Re-load a re-transcribed txt file into Neo4j by deleting all Chunk nodes for that
document (by document_name) and re-creating them from the transcription file.

Use this after re-running ASR (e.g. simple_asr.py or run_batch_asr.py) so Neo4j
chunk nodes match the new transcript.

Example:
  python reload_transcription_to_neo4j.py transcriptions/【LNG】2026JAN 豬神降臨_combined.txt
  python reload_transcription_to_neo4j.py "transcriptions/My Video_combined.txt" --embedding nomic
"""
import os
import sys
import asyncio
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

if "OPENAI_API_KEY" not in os.environ:
    print("⚠️  OPENAI_API_KEY not set (needed for concept generation and for --embedding openai|both)")
    print("   Set it in .env or export; use --embedding nomic if you only need nomic embeddings.")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from graphrag.own_graph_rag import reload_document_in_neo4j

DB_NAME = "lng_transcriptions"
TRANSCRIPTIONS_DIR = Path("./transcriptions")


def get_url_mapping_for(path: Path) -> dict:
    url_mapping = {}
    csv_path = Path("./VODs/videos.csv")
    if not csv_path.exists():
        return url_mapping
    import csv
    doc_name = path.name
    base = path.stem.replace("_combined", "")
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            title = (row.get("title") or "").strip()
            if title == base or doc_name.startswith(title):
                url_mapping[doc_name] = (row.get("url") or "").strip()
                break
    return url_mapping


async def main(file_path: Path, embedding_backend: str, db_name: str):
    path = file_path.resolve()
    if not path.is_file():
        print(f"❌ File not found: {path}")
        sys.exit(1)
    url_mapping = get_url_mapping_for(path)
    result = await reload_document_in_neo4j(
        path=str(path),
        db_name=db_name,
        embedding_backend=embedding_backend,
        url_mapping_dict=url_mapping or None,
    )
    if result.get("success"):
        print(f"✅ {result.get('message', 'Reload complete')}")
    else:
        print(f"❌ {result.get('error', 'Reload failed')}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Re-load a re-transcribed file into Neo4j: delete chunks by document_name, then create from file."
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Path to a _combined.txt transcription file (e.g. transcriptions/Video_combined.txt).",
    )
    parser.add_argument(
        "--embedding",
        choices=["nomic", "openai", "both"],
        default="nomic",
        help="Embeddings to store on new chunks/concepts (default: nomic)",
    )
    parser.add_argument(
        "--db",
        default=DB_NAME,
        help=f"Logical DB name (default: {DB_NAME}).",
    )
    args = parser.parse_args()
    asyncio.run(main(args.file, args.embedding, args.db))
