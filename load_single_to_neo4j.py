#!/usr/bin/env python3
"""
Load a single transcription (or a single WAV) into the existing Neo4j database.
Does not wipe the DB — adds/updates only this document's chunks and concepts.
Use this for:
  - Adding one new _combined.txt to an existing graph
  - Uploading one WAV: runs ASR to produce _combined.txt, then loads it
"""
import os
import sys
import asyncio
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# OPENAI_API_KEY is required for concept generation (LLM) and for --embedding openai|both
if "OPENAI_API_KEY" not in os.environ:
    print("⚠️  OPENAI_API_KEY not set (needed for concept generation and for --embedding openai|both)")
    print("   Set it in .env or export; use --embedding nomic if you only need nomic embeddings.")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from graphrag.own_graph_rag import load_files_neo4j_graphrag

DB_NAME = "lng_transcriptions"
TRANSCRIPTIONS_DIR = Path("./transcriptions")


async def load_one(path: Path, embedding_backend: str, db_name: str):
    """Load a single transcription file into Neo4j (no DB clean)."""
    url_mapping = {}
    csv_path = Path("./VODs/videos.csv")
    if csv_path.exists():
        import csv
        doc_name = path.name
        base = path.stem.replace("_combined", "")
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                title = (row.get("title") or "").strip()
                if title == base or doc_name.startswith(title):
                    url_mapping[doc_name] = (row.get("url") or "").strip()
                    break

    await load_files_neo4j_graphrag(
        path=str(path.resolve()),
        db_name=db_name,
        node_labels=[],
        rel_labels=[],
        prompt_template="",
        generate_concepts=True,
        background_tasks=None,
        url_mapping_dict=url_mapping or None,
        embedding_backend=embedding_backend,
    )


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Load a single transcription or WAV into existing Neo4j (no DB wipe)."
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Path to a _combined.txt transcription file, or to a .wav file (ASR will run first).",
    )
    parser.add_argument(
        "--embedding",
        choices=["nomic", "openai", "both"],
        default="nomic",
        help="Embeddings to store: nomic_embeddings, openai_embeddings, or both (default: nomic)",
    )
    parser.add_argument(
        "--db",
        default=DB_NAME,
        help=f"Logical DB name (default: {DB_NAME}); Community Edition uses default 'neo4j'.",
    )
    args = parser.parse_args()

    path = args.file.resolve()
    if not path.exists():
        print(f"❌ File not found: {path}")
        sys.exit(1)

    # If WAV: run ASR to produce _combined.txt
    if path.suffix.lower() == ".wav":
        print("Running ASR on WAV to produce combined transcription...")
        from simple_asr import process_audio_file
        from utils import safe_execute
        success, _, err = safe_execute(process_audio_file, str(path), True)  # keep_audio=True
        if not success:
            print(f"❌ ASR failed: {err}")
            sys.exit(1)
        # simple_asr writes to same dir as audio: {audio_dir}/{stem}_combined.txt
        combined = path.parent / f"{path.stem}_combined.txt"
        if not combined.exists():
            print(f"❌ Expected output not found: {combined}")
            sys.exit(1)
        path = combined
        print(f"✅ Transcription: {path}")

    if path.suffix.lower() != ".txt" or "_combined" not in path.stem:
        print("⚠️  Expected a _combined.txt file or a .wav file. Proceeding with given file anyway.")

    print("Loading into Neo4j (existing DB, no clean)...")
    asyncio.run(load_one(path, args.embedding, args.db))
    print("✅ Done. Single document added to Neo4j.")


if __name__ == "__main__":
    main()
