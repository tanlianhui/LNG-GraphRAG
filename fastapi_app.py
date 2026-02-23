"""
FastAPI application exposing LNG-GraphRAG functions as REST endpoints.

Run with: uvicorn fastapi_app:app --host 0.0.0.0 --port 8000

Endpoints cover:
- Download status and transcription listing
- Transcription content and chunks (read/update/delete/reload)
- GraphRAG: natural-language and Cypher queries
- Neo4j: load document, update/delete chunk, delete document chunks, reload document
"""

import os
import sys
import csv
import asyncio
from pathlib import Path
from typing import Optional

# Project root on path for graphrag and env
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Config (mirrors web_app paths)
# -----------------------------------------------------------------------------
TRANSCRIPTIONS_DIR = os.path.join(_ROOT, "transcriptions")
EDIT_DIR = os.path.join(_ROOT, "transcriptions", "edit")
VODS_CSV = os.path.join(_ROOT, "VODs", "videos.csv")
VODS_DIR = os.path.join(_ROOT, "VODs")


def _get_download_status():
    """Return list of videos with status and transcription existence."""
    videos = []
    if not os.path.exists(VODS_CSV):
        return videos
    with open(VODS_CSV, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            title = (row.get("title") or "").strip()
            url = (row.get("url") or "").strip()
            status = row.get("status", "pending")
            transcription_file = os.path.join(TRANSCRIPTIONS_DIR, f"{title}_combined.txt")
            transcription_exists = os.path.exists(transcription_file)
            wav_file = os.path.join(VODS_DIR, f"{title}.wav")
            videos.append({
                "title": title,
                "url": url,
                "status": status,
                "transcription_exists": transcription_exists,
                "wav_exists": os.path.exists(wav_file),
            })
    return videos


def _get_transcription_file_path(filename: str) -> Optional[str]:
    edit_name = filename.replace("_combined.txt", "_combined_edit.txt")
    edit_path = os.path.join(EDIT_DIR, edit_name)
    if os.path.exists(edit_path):
        return edit_path
    orig = os.path.join(TRANSCRIPTIONS_DIR, filename)
    return orig if os.path.exists(orig) else None


def _get_transcription_files():
    """List transcription files with size and URL from videos.csv."""
    out = []
    if not os.path.exists(TRANSCRIPTIONS_DIR):
        return out
    title_to_url = {}
    if os.path.exists(VODS_CSV):
        with open(VODS_CSV, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                t = (row.get("title") or "").strip()
                if t:
                    title_to_url[t] = (row.get("url") or "").strip()
    for name in os.listdir(TRANSCRIPTIONS_DIR):
        if not name.endswith("_combined.txt"):
            continue
        path = os.path.join(TRANSCRIPTIONS_DIR, name)
        if not os.path.isfile(path):
            continue
        title = name.replace("_combined.txt", "")
        size = os.path.getsize(path)
        out.append({
            "filename": name,
            "title": title,
            "path": path,
            "size": size,
            "size_mb": round(size / (1024 * 1024), 2),
            "url": title_to_url.get(title, ""),
        })
    out.sort(key=lambda x: x["filename"], reverse=True)
    return out


def _get_transcription_content(filename: str) -> Optional[str]:
    path = _get_transcription_file_path(filename)
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# -----------------------------------------------------------------------------
# Pydantic request/response models
# -----------------------------------------------------------------------------
class TranscriptionUpdateBody(BaseModel):
    """Request body for updating a single chunk in a transcription."""
    filename: str = Field(..., description="Transcription filename, e.g. 'Video_combined.txt'")
    chunk_id: int = Field(..., description="Chunk index (0-based)")
    new_text: str = Field(..., description="New text content for the chunk")
    embedding: str = Field("nomic", description="Embedding backend for Neo4j: nomic, openai, or both")


class TranscriptionDeleteBody(BaseModel):
    """Request body for deleting a single chunk from Neo4j."""
    filename: str = Field(..., description="Transcription filename (document_name in Neo4j)")
    chunk_id: int = Field(..., description="Chunk index (0-based) to delete")


class TranscriptionReloadBody(BaseModel):
    """Request body for re-loading a re-transcribed file into Neo4j."""
    filename: str = Field(..., description="Transcription filename, e.g. 'Video_combined.txt'")
    embedding: str = Field("nomic", description="Embedding backend: nomic, openai, or both")


class NLQueryBody(BaseModel):
    """Request body for natural-language GraphRAG query."""
    query: str = Field(..., description="Natural language question about the knowledge graph")


class CypherQueryBody(BaseModel):
    """Request body for direct Cypher query."""
    query: str = Field(..., description="Cypher query string to execute on Neo4j")


class LoadDocumentBody(BaseModel):
    """Request body for loading a single transcription file into Neo4j."""
    path: str = Field(..., description="Path to _combined.txt file (relative to project or absolute)")
    db_name: str = Field("lng_transcriptions", description="Logical Neo4j database name")
    embedding_backend: str = Field("nomic", description="nomic, openai, or both")


class UpdateChunkBody(BaseModel):
    """Request body for updating a chunk's text and embeddings in Neo4j."""
    document_name: str = Field(..., description="Document filename (e.g. Video_combined.txt)")
    chunk_id: int = Field(..., description="Chunk index (0-based)")
    new_text: str = Field(..., description="New chunk text")
    db_name: str = Field("lng_transcriptions", description="Logical Neo4j database name")
    embedding_backend: str = Field("nomic", description="nomic, openai, or both")


class DeleteChunkBody(BaseModel):
    """Request body for deleting a single chunk node from Neo4j."""
    document_name: str = Field(..., description="Document filename")
    chunk_id: int = Field(..., description="Chunk index (0-based)")
    db_name: str = Field("lng_transcriptions", description="Logical Neo4j database name")


class DeleteDocumentChunksBody(BaseModel):
    """Request body for deleting all chunk nodes for a document."""
    document_name: str = Field(..., description="Document filename (e.g. Video_combined.txt)")
    db_name: str = Field("lng_transcriptions", description="Logical Neo4j database name")


class ReloadDocumentBody(BaseModel):
    """Request body for reloading a document in Neo4j (delete chunks then re-load from file)."""
    path: str = Field(..., description="Path to transcription file")
    db_name: str = Field("lng_transcriptions", description="Logical Neo4j database name")
    embedding_backend: str = Field("nomic", description="nomic, openai, or both")


# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------
app = FastAPI(
    title="LNG GraphRAG API",
    description="REST API for transcriptions, Neo4j chunk operations, and GraphRAG queries.",
    version="1.0.0",
)


# ----- Download & transcriptions (read-only) -----

@app.get(
    "/download-status",
    summary="Get download status",
    description="Returns the list of videos from VODs/videos.csv with status and whether transcription/WAV exists.",
)
async def get_download_status():
    data = _get_download_status()
    completed = sum(1 for v in data if v.get("transcription_exists") or v.get("status") == "completed")
    return {
        "success": True,
        "videos": data,
        "total": len(data),
        "completed": completed,
        "pending": sum(1 for v in data if v.get("status") == "pending" and not v.get("transcription_exists")),
        "failed": sum(1 for v in data if v.get("status") == "failed" and not v.get("transcription_exists")),
        "with_transcriptions": sum(1 for v in data if v.get("transcription_exists")),
    }


@app.get(
    "/transcriptions",
    summary="List transcription files",
    description="Returns metadata for all _combined.txt files in the transcriptions directory.",
)
async def get_transcriptions():
    files = _get_transcription_files()
    return {"success": True, "transcriptions": files, "total": len(files)}


@app.get(
    "/transcription/{filename:path}",
    summary="Get transcription content",
    description="Returns raw content of a transcription file (uses edit file if present).",
)
async def get_transcription_content(filename: str):
    filename = os.path.basename(filename)
    if not filename.endswith("_combined.txt"):
        raise HTTPException(status_code=400, detail="Filename must end with _combined.txt")
    content = _get_transcription_content(filename)
    if content is None:
        raise HTTPException(status_code=404, detail="Transcription file not found")
    return {"success": True, "filename": filename, "content": content}


@app.get(
    "/transcription/{filename:path}/chunks",
    summary="Get parsed chunks",
    description="Returns parsed chunks (chunk_id, text, start_time, end_time) for a transcription file.",
)
async def get_transcription_chunks(filename: str):
    filename = os.path.basename(filename)
    if not filename.endswith("_combined.txt"):
        raise HTTPException(status_code=400, detail="Filename must end with _combined.txt")
    path = _get_transcription_file_path(filename)
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Transcription file not found")
    graphrag_path = os.path.join(_ROOT, "graphrag")
    if graphrag_path not in sys.path:
        sys.path.insert(0, graphrag_path)
    from own_graph_rag import parse_transcription_chunks
    chunks = parse_transcription_chunks(path)
    return {"success": True, "filename": filename, "chunks": chunks, "total_chunks": len(chunks)}


# ----- Transcription update / delete / reload (write) -----

@app.post(
    "/transcription/update",
    summary="Update a chunk",
    description="Updates a chunk's text in the edit file and in Neo4j (regenerates embeddings).",
)
async def update_transcription(body: TranscriptionUpdateBody):
    filename = os.path.basename(body.filename)
    if not filename.endswith("_combined.txt"):
        raise HTTPException(status_code=400, detail="Filename must end with _combined.txt")
    path = os.path.join(TRANSCRIPTIONS_DIR, filename)
    if not os.path.isfile(path):
        path = _get_transcription_file_path(filename)
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Transcription file not found")
    graphrag_path = os.path.join(_ROOT, "graphrag")
    if graphrag_path not in sys.path:
        sys.path.insert(0, graphrag_path)
    from own_graph_rag import (
        get_transcription_file_path,
        parse_transcription_chunks,
        write_full_transcription_to_edit_file,
        write_edit_record_to_history,
        update_chunk_in_neo4j,
    )
    edit_dir = os.path.join(_ROOT, "transcriptions", "edit")
    edit_history_dir = os.path.join(_ROOT, "transcriptions", "edit_history")
    current_path = get_transcription_file_path(filename, TRANSCRIPTIONS_DIR, edit_dir)
    chunks = parse_transcription_chunks(current_path) if current_path else []
    if body.chunk_id >= len(chunks):
        raise HTTPException(status_code=400, detail="chunk_id out of range")
    ok = write_full_transcription_to_edit_file(
        TRANSCRIPTIONS_DIR, edit_dir, edit_history_dir,
        filename, body.chunk_id, body.new_text,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to write edit to file")
    write_edit_record_to_history(edit_history_dir, filename, body.chunk_id, chunks[body.chunk_id]["text"], body.new_text, "api")
    db_name = os.getenv("NEO4J_DB_NAME", "lng_transcriptions")
    result = await update_chunk_in_neo4j(
        document_name=filename,
        chunk_id=body.chunk_id,
        new_text=body.new_text,
        db_name=db_name,
        embedding_backend=body.embedding,
    )
    if not result.get("success"):
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Edit saved to file; Neo4j update failed: " + result.get("error", ""),
                "neo4j_updated": False,
            },
        )
    return {"success": True, "message": "Chunk updated", "neo4j_updated": True}


@app.post(
    "/transcription/delete",
    summary="Delete a chunk from Neo4j",
    description="Deletes the chunk node for the given document_name and chunk_id from Neo4j. Does not modify files.",
)
async def delete_transcription_chunk(body: TranscriptionDeleteBody):
    filename = os.path.basename(body.filename)
    if not filename.endswith("_combined.txt"):
        raise HTTPException(status_code=400, detail="Filename must end with _combined.txt")
    db_name = os.getenv("NEO4J_DB_NAME", "lng_transcriptions")
    graphrag_path = os.path.join(_ROOT, "graphrag")
    if graphrag_path not in sys.path:
        sys.path.insert(0, graphrag_path)
    from own_graph_rag import delete_chunk_in_neo4j
    result = await delete_chunk_in_neo4j(document_name=filename, chunk_id=body.chunk_id, db_name=db_name)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Delete failed"))
    return {"success": True, "document_name": filename, "chunk_id": body.chunk_id, "message": "Chunk deleted"}


@app.post(
    "/transcription/reload",
    summary="Reload a re-transcribed file in Neo4j",
    description="Deletes all Chunk nodes for the document, then re-creates them from the transcription file.",
)
async def reload_transcription(body: TranscriptionReloadBody):
    filename = os.path.basename(body.filename)
    if not filename.endswith("_combined.txt"):
        raise HTTPException(status_code=400, detail="Filename must end with _combined.txt")
    path = os.path.join(TRANSCRIPTIONS_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Transcription file not found")
    url_mapping = {}
    if os.path.isfile(VODS_CSV):
        with open(VODS_CSV, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                title = (row.get("title") or "").strip()
                if title and (filename.startswith(title) or filename.replace("_combined.txt", "") == title):
                    url_mapping[filename] = (row.get("url") or "").strip()
                    break
    db_name = os.getenv("NEO4J_DB_NAME", "lng_transcriptions")
    graphrag_path = os.path.join(_ROOT, "graphrag")
    if graphrag_path not in sys.path:
        sys.path.insert(0, graphrag_path)
    from own_graph_rag import reload_document_in_neo4j
    result = await reload_document_in_neo4j(
        path=os.path.abspath(path),
        db_name=db_name,
        embedding_backend=body.embedding,
        url_mapping_dict=url_mapping or None,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Reload failed"))
    return {"success": True, "document_name": result.get("document_name"), "deleted_count": result.get("deleted_count", 0), "message": result.get("message")}


# ----- GraphRAG queries -----

@app.post(
    "/graphrag/nl-query",
    summary="Natural language query",
    description="Asks a question in natural language; uses LLM to query the knowledge graph and return an answer. Requires OpenAI or Ollama (NL_QUERY_LLM). For full implementation use the Flask web app at /api/graphrag/nl-query.",
)
async def graphrag_nl_query(body: NLQueryBody):
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")
    raise HTTPException(
        status_code=501,
        detail="Use POST /graphrag/query with a Cypher query, or run the Flask app (launch_web.py) for natural-language queries at /api/graphrag/nl-query.",
    )


@app.post(
    "/graphrag/query",
    summary="Execute Cypher query",
    description="Runs a Cypher query on Neo4j and returns results and summary.",
)
async def graphrag_cypher_query(body: CypherQueryBody):
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")
    import neo4j
    from time import time
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "lng-graphrag-password")
    DB_NAME = os.getenv("NEO4J_DB_NAME", "lng_transcriptions")
    driver = None
    try:
        driver = neo4j.GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD), connection_timeout=30)
        actual_db = "neo4j"  # Community Edition default
        try:
            test_db = f"_t_{int(time())}"
            with driver.session(database="system") as s:
                s.run(f"CREATE DATABASE {test_db}")
                s.run(f"DROP DATABASE {test_db} IF EXISTS")
            actual_db = DB_NAME  # Enterprise: use requested DB
        except Exception:
            pass  # Community: keep "neo4j"
        with driver.session(database=actual_db) as session:
            result = session.run(body.query)
            records = []
            for rec in result:
                record_dict = {}
                for key in rec.keys():
                    val = rec[key]
                    if hasattr(val, "labels") and hasattr(val, "properties"):
                        record_dict[key] = {"identity": val.id, "labels": list(val.labels), "properties": dict(val)}
                    elif hasattr(val, "type") and hasattr(val, "start_node"):
                        record_dict[key] = {
                            "identity": val.id, "type": val.type,
                            "start": {"identity": val.start_node.id, "labels": list(val.start_node.labels), "properties": dict(val.start_node)},
                            "end": {"identity": val.end_node.id, "labels": list(val.end_node.labels), "properties": dict(val.end_node)},
                            "properties": dict(val),
                        }
                    else:
                        record_dict[key] = val
                records.append(record_dict)
            summary = result.consume()
            return {
                "success": True,
                "query": body.query,
                "results": records,
                "summary": {
                    "result_available_after": summary.result_available_after,
                    "result_consumed_after": summary.result_consumed_after,
                    "counters": {
                        "nodes_created": summary.counters.nodes_created,
                        "nodes_deleted": summary.counters.nodes_deleted,
                        "relationships_created": summary.counters.relationships_created,
                        "relationships_deleted": summary.counters.relationships_deleted,
                    },
                },
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    finally:
        if driver:
            driver.close()


# ----- Neo4j document/chunk operations -----

@app.post(
    "/neo4j/load",
    summary="Load a transcription file into Neo4j",
    description="Loads a single _combined.txt file into Neo4j (chunks + concepts + embeddings). Does not delete existing data.",
)
async def neo4j_load_document(body: LoadDocumentBody):
    path = body.path if os.path.isabs(body.path) else os.path.join(_ROOT, body.path)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    url_mapping = {}
    if os.path.isfile(VODS_CSV):
        doc_name = os.path.basename(path)
        base = doc_name.replace("_combined.txt", "")
        with open(VODS_CSV, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                title = (row.get("title") or "").strip()
                if title == base or doc_name.startswith(title):
                    url_mapping[doc_name] = (row.get("url") or "").strip()
                    break
    graphrag_path = os.path.join(_ROOT, "graphrag")
    if graphrag_path not in sys.path:
        sys.path.insert(0, graphrag_path)
    from own_graph_rag import load_files_neo4j_graphrag
    await load_files_neo4j_graphrag(
        path=path,
        db_name=body.db_name,
        node_labels=[],
        rel_labels=[],
        prompt_template="",
        generate_concepts=True,
        background_tasks=None,
        url_mapping_dict=url_mapping or None,
        embedding_backend=body.embedding_backend,
    )
    return {"success": True, "path": path, "message": "Document loaded"}


@app.post(
    "/neo4j/update-chunk",
    summary="Update a chunk in Neo4j",
    description="Updates a chunk's text and regenerates its embeddings in Neo4j.",
)
async def neo4j_update_chunk(body: UpdateChunkBody):
    graphrag_path = os.path.join(_ROOT, "graphrag")
    if graphrag_path not in sys.path:
        sys.path.insert(0, graphrag_path)
    from own_graph_rag import update_chunk_in_neo4j
    result = await update_chunk_in_neo4j(
        document_name=body.document_name,
        chunk_id=body.chunk_id,
        new_text=body.new_text,
        db_name=body.db_name,
        embedding_backend=body.embedding_backend,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Update failed"))
    return {"success": True, "document_name": body.document_name, "chunk_id": body.chunk_id, "message": result.get("message")}


@app.post(
    "/neo4j/delete-chunk",
    summary="Delete a chunk from Neo4j",
    description="Deletes a single Chunk node by document_name and chunk_id.",
)
async def neo4j_delete_chunk(body: DeleteChunkBody):
    graphrag_path = os.path.join(_ROOT, "graphrag")
    if graphrag_path not in sys.path:
        sys.path.insert(0, graphrag_path)
    from own_graph_rag import delete_chunk_in_neo4j
    result = await delete_chunk_in_neo4j(document_name=body.document_name, chunk_id=body.chunk_id, db_name=body.db_name)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Delete failed"))
    return {"success": True, "document_name": body.document_name, "chunk_id": body.chunk_id, "message": result.get("message")}


@app.post(
    "/neo4j/delete-document-chunks",
    summary="Delete all chunks for a document",
    description="Deletes all Chunk nodes for the given document_name. Use before reloading a re-transcribed file.",
)
async def neo4j_delete_document_chunks(body: DeleteDocumentChunksBody):
    graphrag_path = os.path.join(_ROOT, "graphrag")
    if graphrag_path not in sys.path:
        sys.path.insert(0, graphrag_path)
    from own_graph_rag import delete_document_chunks_in_neo4j
    result = await delete_document_chunks_in_neo4j(document_name=body.document_name, db_name=body.db_name)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Delete failed"))
    return {"success": True, "document_name": body.document_name, "deleted_count": result.get("deleted_count", 0), "message": result.get("message")}


@app.post(
    "/neo4j/reload-document",
    summary="Reload a document in Neo4j",
    description="Deletes all Chunk nodes for the document, then re-creates them from the transcription file (chunks + concepts + embeddings).",
)
async def neo4j_reload_document(body: ReloadDocumentBody):
    path = body.path if os.path.isabs(body.path) else os.path.join(_ROOT, body.path)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    url_mapping = {}
    doc_name = os.path.basename(path)
    if os.path.isfile(VODS_CSV):
        base = doc_name.replace("_combined.txt", "")
        with open(VODS_CSV, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                title = (row.get("title") or "").strip()
                if title == base or doc_name.startswith(title):
                    url_mapping[doc_name] = (row.get("url") or "").strip()
                    break
    graphrag_path = os.path.join(_ROOT, "graphrag")
    if graphrag_path not in sys.path:
        sys.path.insert(0, graphrag_path)
    from own_graph_rag import reload_document_in_neo4j
    result = await reload_document_in_neo4j(
        path=path,
        db_name=body.db_name,
        embedding_backend=body.embedding_backend,
        url_mapping_dict=url_mapping or None,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Reload failed"))
    return {"success": True, "document_name": result.get("document_name"), "deleted_count": result.get("deleted_count", 0), "message": result.get("message")}


# ----- Stats -----

@app.get(
    "/stats",
    summary="Overall statistics",
    description="Returns counts for videos, transcriptions, and completed/pending status.",
)
async def get_stats():
    videos = _get_download_status()
    transcriptions = _get_transcription_files()
    completed = sum(1 for v in videos if v.get("transcription_exists") or v.get("status") == "completed")
    return {
        "success": True,
        "stats": {
            "total_videos": len(videos),
            "total_transcriptions": len(transcriptions),
            "videos_with_transcriptions": sum(1 for v in videos if v.get("transcription_exists")),
            "completed": completed,
            "pending": sum(1 for v in videos if v.get("status") == "pending" and not v.get("transcription_exists")),
        },
    }


# ----- Health -----

@app.get("/health", summary="Health check", description="Returns OK if the API is running.")
async def health():
    return {"status": "ok"}
