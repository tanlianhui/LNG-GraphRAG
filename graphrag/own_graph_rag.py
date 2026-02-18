"""
Simplified GraphRAG implementation for loading transcriptions into Neo4j
Removed unnecessary imports and dependencies
"""
import asyncio
import os
import json
import re
import traceback
import ast
from time import sleep, time
from typing import Any, Literal, Optional

# Embedding backend: which model(s) to use; stored as nomic_embeddings and/or openai_embeddings on nodes
EmbeddingBackend = Literal["nomic", "openai", "both"]

# Core imports
import neo4j
import tiktoken
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings
from langchain_core.embeddings import Embeddings
from langchain_neo4j import Neo4jVector, Neo4jGraph
from langchain_community.callbacks import get_openai_callback
from semantic_text_splitter import CharacterTextSplitter
from neo4j_graphrag.experimental.components.text_splitters.base import TextSplitter
from neo4j_graphrag.experimental.components.types import TextChunk, TextChunks
from pydantic import validate_call

# Initialize encoding for token counting
encoding = tiktoken.get_encoding("cl100k_base")

# Neo4j connection settings from environment
NEO4J_URI = f'bolt://{os.environ.get("NEO4J_IP", "localhost")}:7687'
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "lng-graphrag-password")

# Global flag to track if we're using Community Edition
_IS_COMMUNITY_EDITION = None

def get_database_name(requested_db_name: str) -> str:
    """
    Get the actual database name to use.
    In Community Edition, returns "neo4j" (default database).
    In Enterprise Edition, returns the requested database name.
    """
    global _IS_COMMUNITY_EDITION
    
    if _IS_COMMUNITY_EDITION is None:
        # Check on first call - use the same detection logic as prepare_database
        # Test if CREATE DATABASE is supported (Enterprise Edition feature)
        driver = None
        try:
            driver = neo4j.GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD), connection_timeout=5
            )
            
            # Try to create a test database to detect Enterprise Edition
            test_db_name = f"_test_db_{int(time())}"
            try:
                with driver.session(database="system") as session:
                    # Try to create a test database
                    session.run(f"CREATE DATABASE {test_db_name}")
                    # If successful, immediately drop it
                    session.run(f"DROP DATABASE {test_db_name} IF EXISTS")
                # If we get here, it's Enterprise Edition
                _IS_COMMUNITY_EDITION = False
            except Exception:
                # Any error creating database means Community Edition
                _IS_COMMUNITY_EDITION = True
        except Exception:
            # If we can't connect, assume Community Edition to be safe
            _IS_COMMUNITY_EDITION = True
        finally:
            if driver:
                driver.close()
    
    if _IS_COMMUNITY_EDITION:
        # Community Edition: use default database name "neo4j"
        return "neo4j"  # Default database name in Community Edition
    else:
        return requested_db_name

# Simple logger replacement
def log_debug(msg):
    print(f"[DEBUG] {msg}", flush=True)

def log_error(msg):
    print(f"[ERROR] {msg}", flush=True)


def clean_json_response(raw_response: str) -> str:
    """Clean up LLM response to remove markdown formatting and extract valid JSON."""
    content = raw_response.strip()
    
    # Remove markdown code blocks
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    
    if content.endswith("```"):
        content = content[:-3]
    
    content = content.strip()
    
    # Extract JSON between first { and last }
    start_idx = content.find('{')
    end_idx = content.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
        content = content[start_idx:end_idx+1]
    
    return content


def parse_transcription_chunks(path: str) -> list[dict]:
    """
    Parse transcription file into chunks with metadata (chunk ID, timecodes, text).
    Handles both formats:
    - With timecodes: === Chunk 1 [0.00s - 94.49s] ===
    - Without timecodes: === Chunk 1 ===
    
    Also handles edit files by reading original and applying edits.
    
    Returns:
        List of dicts with keys: chunk_id, text, start_time, end_time
    """
    try:
        if not path.endswith(".txt"):
            raise ValueError(f"Unsupported file type: {path}. Only .txt files are supported.")
        
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Check if this is an edit file (contains "=== EDIT" markers)
        if "=== EDIT" in content:
            # For edit files, we need to read the original file and apply edits
            # First, try to find the original file
            original_filename = os.path.basename(path).replace('_combined_edit.txt', '_combined.txt')
            original_dir = os.path.dirname(path).replace('/edit', '')
            original_path = os.path.join(original_dir, original_filename)
            
            # Parse original file first
            if os.path.exists(original_path):
                with open(original_path, "r", encoding="utf-8") as f:
                    original_content = f.read()
                chunks = parse_original_chunks(original_content)
                # Apply edits from edit file
                chunks = apply_edits_to_chunks(chunks, content)
                return chunks
            else:
                # If original doesn't exist, just parse edit file as regular chunks
                log_debug(f"Original file not found: {original_path}, parsing edit file directly")
        
        # Parse regular transcription file
        return parse_original_chunks(content)
        
    except Exception as e:
        raise ValueError(f"Failed to parse transcription file {path}: {e}")


def parse_original_chunks(content: str) -> list[dict]:
    """Parse original transcription file format"""
    import re
    chunks = []
    # Split by chunk markers
    parts = content.split("=== Chunk")
    
    for part in parts[1:]:  # Skip first empty part
        lines = part.strip().split("\n", 1)
        if len(lines) >= 2:
            header = lines[0].strip()
            text = lines[1].strip() if len(lines) > 1 else ""
            
            # Parse chunk ID and timecodes
            chunk_id = None
            start_time = None
            end_time = None
            
            # Extract chunk number
            chunk_match = re.search(r'(\d+)', header)
            if chunk_match:
                chunk_id = int(chunk_match.group(1)) - 1  # 0-indexed
            
            # Extract timecodes if present: [0.00s - 94.49s]
            timecode_match = re.search(r'\[([\d.]+)s\s*-\s*([\d.]+)s\]', header)
            if timecode_match:
                start_time = float(timecode_match.group(1))
                end_time = float(timecode_match.group(2))
            
            if chunk_id is not None and text:
                # Clean up text: remove any leftover timecode fragments like "41s] ==="
                # This can happen when timecode formatting is inconsistent
                text = re.sub(r'\d+\.?\d*s\]\s*===?\s*', '', text)  # Remove patterns like "41s] ===" or "41.5s] ==="
                text = re.sub(r'^===?\s*', '', text)  # Remove leading "==="
                text = text.strip()
                
                chunks.append({
                    "chunk_id": chunk_id,
                    "text": text,
                    "start_time": start_time,
                    "end_time": end_time
                })
    
    return chunks


def apply_edits_to_chunks(chunks: list[dict], edit_content: str) -> list[dict]:
    """
    Apply edits from edit file to chunks.
    Edit file format:
    === EDIT timestamp ===
    Document: filename
    Chunk ID: chunk_id
    New Text:
    [new text]
    ===
    """
    import re
    from datetime import datetime
    
    # Parse all edits, keeping only the latest edit for each chunk
    edit_pattern = r'=== EDIT ([^=]+) ===\nDocument: ([^\n]+)\nChunk ID: (\d+)\nNew Text:\n(.*?)\n==='
    edits = re.findall(edit_pattern, edit_content, re.DOTALL)
    
    # Group edits by chunk_id and keep only the latest (by timestamp)
    chunk_edits = {}
    for timestamp_str, doc_name, chunk_id_str, new_text in edits:
        chunk_id = int(chunk_id_str)
        try:
            timestamp = datetime.fromisoformat(timestamp_str.strip())
            if chunk_id not in chunk_edits or timestamp > chunk_edits[chunk_id][0]:
                chunk_edits[chunk_id] = (timestamp, new_text.strip())
        except Exception:
            # If timestamp parsing fails, just use the latest one we've seen
            if chunk_id not in chunk_edits:
                chunk_edits[chunk_id] = (datetime.now(), new_text.strip())
    
    # Apply edits to chunks
    for chunk_id, (timestamp, new_text) in chunk_edits.items():
        if 0 <= chunk_id < len(chunks):
            chunks[chunk_id]["text"] = new_text
            log_debug(f"Applied edit to chunk {chunk_id} (timestamp: {timestamp})")
    
    return chunks


def extract_text_from_file(path: str) -> str:
    """
    Extracts text content from a file. Supports TXT files (simplified version).
    For transcriptions, use parse_transcription_chunks() instead to get chunk metadata.
    """
    try:
        if path.endswith(".txt"):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        else:
            raise ValueError(f"Unsupported file type: {path}. Only .txt files are supported.")
    except Exception as e:
        raise ValueError(f"Failed to extract text from {path}: {e}")


def prepare_database(db_name: str, clean_old_data: bool) -> str:
    """
    Prepare Neo4j database - create if doesn't exist or clean if requested.
    Handles both Community Edition (single database) and Enterprise Edition (multiple databases).
    """
    global _IS_COMMUNITY_EDITION
    db_name = db_name.lower()
    driver = None
    is_community_edition = False
    
    try:
        log_debug("--- Preparing database ---")
        driver = neo4j.GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD), connection_timeout=30
        )

        # Test if we can CREATE DATABASE (Enterprise Edition feature)
        # Community Edition doesn't support CREATE DATABASE even if SHOW DATABASES works
        # Default to Community Edition and only switch if we can successfully create a database
        is_community_edition = True  # Assume Community Edition by default
        db_exists = True  # Default database always exists
        
        # Test if CREATE DATABASE is supported by trying to create a test database
        test_db_name = f"_test_db_{int(time())}"
        try:
            with driver.session(database="system") as session:
                # Try to create a test database
                session.run(f"CREATE DATABASE {test_db_name}")
                # If successful, immediately drop it
                session.run(f"DROP DATABASE {test_db_name} IF EXISTS")
            # If we get here, it's Enterprise Edition
            is_community_edition = False
            # Now check if our target database exists
            with driver.session(database="system") as session:
                result = session.run("SHOW DATABASES")
                databases = [record["name"] for record in result]
                db_exists = db_name in databases
                print(f"ℹ️  Detected Neo4j Enterprise Edition", flush=True)
        except Exception as e:
            # Any error creating database means Community Edition
            error_str = str(e)
            error_lower = error_str.lower()
            
            # Log the detection
            if "unsupported" in error_lower or "administration" in error_lower:
                print(f"ℹ️  Detected Neo4j Community Edition - using default database", flush=True)
            else:
                # Even if it's a different error, assume Community Edition for safety
                print(f"ℹ️  Using default database (Community Edition - CREATE DATABASE not supported)", flush=True)
            
            is_community_edition = True
            db_exists = True

        operation_performed = False
        msg = ""
        
        if is_community_edition:
            # Community Edition: Use default database and clean data if requested
            # Set global flag so other functions know we're using Community Edition
            _IS_COMMUNITY_EDITION = True
            
            if clean_old_data:
                print(f"Cleaning data in default database 'neo4j'...", flush=True)
                # Delete all nodes and relationships
                with driver.session() as session:
                    # Delete all nodes and relationships
                    session.run("MATCH (n) DETACH DELETE n")
                msg = f"Default database 'neo4j' cleaned (Community Edition)."
                operation_performed = True
            else:
                msg = f"Using default database 'neo4j' (Community Edition — no separate '{db_name}' DB; data lives in 'neo4j')."
                return msg
        else:
            # Enterprise Edition: Create or manage databases
            _IS_COMMUNITY_EDITION = False
            
        if not db_exists:
            print(f"Database '{db_name}' does not exist. Creating now...", flush=True)
            with driver.session(database="system") as session:
                session.run(f"CREATE DATABASE {db_name}")
            msg = f"Database '{db_name}' created."
            operation_performed = True
        elif clean_old_data:
            print(f"Cleaning contents of database '{db_name}'...", flush=True)
            with driver.session(database="system") as session:
                session.run(f"CREATE OR REPLACE DATABASE {db_name}")
            msg = f"Database '{db_name}' was reset."
            operation_performed = True
        else:
            msg = f"Database '{db_name}' exists and was left intact."
            return msg

        if operation_performed:
                # Wait until the database is actually online
            print(f"Waiting for database '{db_name}' to come online...", flush=True)
            start_time = time()
            while time() - start_time < 60:  # 60 second timeout
                try:
                    with driver.session(database="system") as session:
                        result = session.run(f"SHOW DATABASE `{db_name}`")
                        record = result.single()
                        status = record["currentStatus"]
                        status_msg = record.get("statusMessage", "")
                        print(f"Status: {status}, Message: {status_msg}", flush=True)
                        if status == "online":
                            break
                        elif status == "failed" or "quarantine" in status_msg.lower():
                            raise Exception(f"Database failed to start: {status_msg}")
                        sleep(2)
                except Exception as e:
                    print(f"Error checking database status: {e}, retrying...", flush=True)
                    sleep(2)
            else:  # while loop timeout
                raise RuntimeError(f"Timeout waiting for database '{db_name}' to come online.")

        return msg

    except Exception as e:
        error_message = f"Failed to prepare database '{db_name}': {e}\n{traceback.format_exc()}"
        log_error(error_message)
        raise RuntimeError(f"Database preparation failed: {str(e)}") from e
    finally:
        if 'driver' in locals() and driver:
            driver.close()


class RowSplitter(TextSplitter):
    """Text splitter which splits the input CSV/XLSX into rows of content."""

    @validate_call
    async def run(self, text: list[Any]) -> TextChunks:
        chunks = []
        for index, row in enumerate(text):
            chunks.append(TextChunk(text=str(row), index=index))
        return TextChunks(chunks=chunks)


class SemanticSplitter(TextSplitter):
    """Text splitter which splits the input text semantically."""

    @validate_call
    def __init__(self, chunk_size: int = 4000, chunk_overlap: int = 200) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be strictly less than chunk_size")
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    @validate_call
    def select_last_n_elements_with_ignore(self, lst: list, length: int) -> str:
        reversed_list = lst[::-1]
        count = 0
        result = []
        for item in reversed_list:
            result.append(item)
            if item.strip(" ") != "\n":
                count += 1
            if count == length:
                break
        return "".join(result[::-1])

    @validate_call
    async def run(self, text: str) -> TextChunks:
        """Splits a piece of text into chunks."""
        # Use tiktoken for token counting instead of ChatOpenAI
        total_tokens = len(encoding.encode(text))
        total_docs = (total_tokens // self._chunk_size) + 1
        doc_length = round(len(text) / total_docs)
        splitter = CharacterTextSplitter(trim_chunks=False)
        chunks = splitter.chunks(text, doc_length)

        overlapped_text_ls = []
        warning = 0
        for doc_index in range(len(chunks)):
            current_doc = chunks[doc_index]
            if len(current_doc) < 10 and warning == 0:
                log_debug(f"Warning: Very short document chunk detected. This may affect quality.")
                warning = 1
            if doc_index != 0:
                prev_doc = re.findall(
                    r".*?[\.!\?。！？\n]", chunks[doc_index - 1], re.DOTALL
                )
                prev_doc_last_sent = self.select_last_n_elements_with_ignore(prev_doc, 2)
                if len(prev_doc_last_sent) > self._chunk_overlap:
                    prev_doc_last_sent = self.select_last_n_elements_with_ignore(prev_doc, 1)
                overlapped_text_ls.append(
                    TextChunk(text=str(prev_doc_last_sent + current_doc), index=doc_index)
                )
            else:
                overlapped_text_ls.append(TextChunk(text=str(current_doc), index=doc_index))

        return TextChunks(chunks=overlapped_text_ls)


def join_small_chunks(text_chunks: list[str], max_tokens: int = 10000) -> list[str]:
    """Join small chunks together to optimize storage while not exceeding token limit."""
    if not text_chunks:
        return text_chunks
        
    joined_chunks = []
    current_chunk = ""
    current_tokens = 0
    
    for i, chunk in enumerate(text_chunks):
        chunk_tokens = len(encoding.encode(chunk))
        
        if current_tokens + chunk_tokens > max_tokens and current_chunk:
            joined_chunks.append(current_chunk.strip())
            current_chunk = chunk
            current_tokens = chunk_tokens
        else:
            if current_chunk:
                current_chunk += "\n\n" + f"id {i}: " + chunk
            else:
                current_chunk = chunk
            current_tokens += chunk_tokens
    
    if current_chunk:
        joined_chunks.append(current_chunk.strip())
    
    return joined_chunks


async def generate_concepts_sync(
    text_chunks: list[str],
    document_name: str,
    nomic_model: Optional[Embeddings],
    openai_model: Optional[Embeddings],
    embedding_backend: EmbeddingBackend,
    db_name: str,
    node_labels: list[str] = [],
    rel_labels: list[str] = [],
    prompt_template: str = "",
    url_mapping_dict: dict = None
) -> None:
    """Generate concepts synchronously and upload to Neo4j. Concept embeddings stored as nomic_embeddings and/or openai_embeddings."""
    try:
        function_start = time()
        step_start = time()
        print(f"🔍 Starting concept generation for {document_name}...", flush=True)
        
        # Join small chunks for concept generation
        original_chunk_count = len(text_chunks)
        concept_chunks = join_small_chunks(text_chunks, max_tokens=10000)
        joined_chunk_count = len(concept_chunks)
        
        print(f"📊 Concept generation: Using {joined_chunk_count} joined chunks (from {original_chunk_count} original chunks)", flush=True)
        
        concept_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        
        # Group chunks for efficient processing
        def group_chunks_by_token_limit(chunks, max_tokens=40000):
            grouped_chunks = []
            current_group = []
            current_indices = []
            current_tokens = 0
            
            for i, chunk in enumerate(chunks):
                chunk_tokens = len(encoding.encode(chunk))
                
                if current_tokens + chunk_tokens > max_tokens and current_group:
                    grouped_chunks.append({
                        'text': '\n\n---CHUNK_SEPARATOR---\n\n'.join(current_group),
                        'chunk_indices': current_indices.copy()
                    })
                    current_group = [chunk]
                    current_indices = [i]
                    current_tokens = chunk_tokens
                else:
                    current_group.append(chunk)
                    current_indices.append(i)
                    current_tokens += chunk_tokens
            
            if current_group:
                grouped_chunks.append({
                    'text': '\n\n---CHUNK_SEPARATOR---\n\n'.join(current_group),
                    'chunk_indices': current_indices.copy()
                })
            
            return grouped_chunks
        
        grouped_chunks = group_chunks_by_token_limit(concept_chunks, max_tokens=40000)
        
        print(f"🔍 Extracting key concepts from {len(concept_chunks)} concept chunks grouped into {len(grouped_chunks)} batches...", flush=True)
        
        all_concepts = []
        all_relationships = []
        
        for group_idx, group in enumerate(grouped_chunks):
            if not group['chunk_indices']:
                continue
                
            chunk_range = f"{group['chunk_indices'][0]}-{group['chunk_indices'][-1]}" if len(group['chunk_indices']) > 1 else str(group['chunk_indices'][0])
            print(f"📦 Processing group {group_idx + 1}/{len(grouped_chunks)} (chunks {chunk_range})...", flush=True)
            
            concept_prompt = f"""Extract key concepts and relationships from the following text passages. 
            The text is divided by ---CHUNK_SEPARATOR--- markers. Each section represents a separate chunk.
            
            IMPORTANT CONTEXT: This text was created by joining {len(group['chunk_indices'])} original chunks (indices: {group['chunk_indices']}) into one larger chunk for processing. 
            When you identify a concept, you must specify which of the ORIGINAL chunks (not the joined chunk) actually contain that concept.
            The document has {len(text_chunks)} total original chunks (indices 0 to {len(text_chunks)-1}), so you can reference any chunk in that range.
            
            Text: {group['text']}
            
            CONCEPT EXTRACTION GUIDELINES:
            Focus on extracting the following types of concepts:
            1. **Person**: Names of people, characters, speakers, or individuals mentioned
            2. **Event**: Specific events, activities, happenings, or occurrences
            3. **Time**: Temporal references (dates, times, periods, durations, "yesterday", "next week", etc.)
            4. **Place**: Locations, places, venues, geographical references
            5. **Recurrent Keywords**: Important terms, phrases, or topics that appear multiple times or are central to the discussion
            6. **Organization**: Companies, groups, institutions, teams
            7. **Topic/Theme**: Main subjects, themes, or topics of discussion
            8. **Object/Thing**: Important objects, items, or things mentioned
            
            {"Focus on these entity types: " + ", ".join(node_labels) if node_labels else ""}
            {"Focus on these relationship types: " + ", ".join(rel_labels) if rel_labels else ""}
            {prompt_template if prompt_template else ""}
            
            Return a JSON object with:
            {{
                "concepts": [
                    {{
                        "name": "concept name",
                        "type": "concept type (must be one of: Person, Event, Time, Place, Recurrent Keyword, Organization, Topic, Theme, Object, or other relevant type)",
                        "description": "brief description of the concept and its significance",
                        "origin_chunks": [15, 16, 17]  // List of ACTUAL original chunk indices (0 to {len(text_chunks)-1}) that mention this concept
                    }}
                ],
                "relationships": [
                    {{
                        "from": "source concept name",
                        "to": "target concept name",
                        "type": "specific relationship type (e.g., 'participated_in', 'occurred_at', 'mentioned_with', 'related_to', etc.)",
                        "description": "brief description of the relationship"
                    }}
                ]
            }}
            
            IMPORTANT: 
            - Prioritize Person, Event, Time, Place, and Recurrent Keywords
            - For Recurrent Keywords, identify terms that appear multiple times or are central themes
            - Be specific with concept names (use full names for people, exact dates/times, precise locations)
            - Only return valid JSON. Be concise but comprehensive.
            """
            
            try:
                with get_openai_callback() as cb:
                    response = concept_llm.invoke([{"role": "user", "content": concept_prompt}])
                    cleaned_content = clean_json_response(response.content)
                    extraction_result = json.loads(cleaned_content)
                    print(f"💰 Group {group_idx + 1} concept extraction cost: ${cb.total_cost:.6f} | Tokens: {cb.total_tokens:,}", flush=True)
                
                # Process concepts
                for concept in extraction_result.get("concepts", []):
                    origin_chunks = concept.get("origin_chunks", [])
                    if not origin_chunks:
                        # Detect which chunks mention the concept
                        concept_name_lower = concept["name"].lower()
                        detected_chunks = []
                        for chunk_idx in group['chunk_indices']:
                            if chunk_idx < len(text_chunks):
                                chunk_text = text_chunks[chunk_idx].lower()
                                if concept_name_lower in chunk_text:
                                    detected_chunks.append(chunk_idx)
                        origin_chunks = detected_chunks if detected_chunks else group['chunk_indices'][:1]
                    
                    concept["origin_chunks"] = origin_chunks
                    concept["concept_chunk_idx"] = origin_chunks[0] if origin_chunks else 0
                    all_concepts.append(concept)
                        
                # Process relationships
                for relationship in extraction_result.get("relationships", []):
                    relationship["concept_chunk_idx"] = group['chunk_indices'][0]
                    all_relationships.append(relationship)
                
                print(f"✓ Group {group_idx + 1}: Extracted {len(extraction_result.get('concepts', []))} concepts, {len(extraction_result.get('relationships', []))} relationships", flush=True)
                
            except json.JSONDecodeError as e:
                log_error(f"⚠️ Failed to parse JSON for group {group_idx}: {e}")
            except Exception as e:
                log_error(f"⚠️ Error processing group {group_idx}: {e}")
        
        print(f"✓ Extracted {len(all_concepts)} concepts and {len(all_relationships)} relationships", flush=True)
        
        # Create embeddings for concepts (nomic and/or openai)
        step_start = time()
        concept_texts = [f"{concept['name']}: {concept['description']}" for concept in all_concepts]
        concept_embeddings_nomic: list[list[float]] = []
        concept_embeddings_openai: list[list[float]] = []
        if concept_texts:
            if nomic_model:
                if hasattr(nomic_model, "aembed_documents"):
                    concept_embeddings_nomic = await nomic_model.aembed_documents(concept_texts)
                else:
                    concept_embeddings_nomic = nomic_model.embed_documents(concept_texts)
            if openai_model:
                if hasattr(openai_model, "aembed_documents"):
                    concept_embeddings_openai = await openai_model.aembed_documents(concept_texts)
                else:
                    concept_embeddings_openai = openai_model.embed_documents(concept_texts)
        log_debug(f"✓ Concept embeddings creation: {time() - step_start:.2f}s")
        
        # Upload to Neo4j
        step_start = time()
        actual_db_name = get_database_name(db_name)
        graph = Neo4jGraph(
            url=NEO4J_URI,
            username=NEO4J_USERNAME,
            password=NEO4J_PASSWORD,
            database=actual_db_name
        )
        
        document_url = url_mapping_dict.get(document_name, "") if url_mapping_dict else ""
        
        # Upload concepts with nomic_embeddings and/or openai_embeddings
        if all_concepts:
            concept_upload_query = """
            UNWIND $concepts AS concept
            MERGE (c:Concept {name: concept.name})
            SET c.type = concept.type,
                c.description = concept.description,
                c.nomic_embeddings = concept.nomic_embeddings,
                c.openai_embeddings = concept.openai_embeddings,
                c.document_name = CASE 
                WHEN c.document_name IS NULL THEN concept.document_name
                WHEN c.document_name = concept.document_name THEN c.document_name
                WHEN NOT concept.document_name IN split(c.document_name, ',') THEN c.document_name + ',' + concept.document_name
                ELSE c.document_name
                END,
                c.url = CASE 
                WHEN c.url IS NULL THEN concept.url
                WHEN c.url = concept.url THEN c.url
                WHEN NOT concept.url IN split(c.url, ',') THEN c.url + ',' + concept.url
                ELSE c.url
            END
            """
            
            concept_data = []
            for i, concept in enumerate(all_concepts):
                concept_data.append({
                    "name": concept["name"],
                    "type": concept["type"],
                    "description": concept["description"],
                    "nomic_embeddings": concept_embeddings_nomic[i] if i < len(concept_embeddings_nomic) else None,
                    "openai_embeddings": concept_embeddings_openai[i] if i < len(concept_embeddings_openai) else None,
                    "document_name": document_name,
                    "url": document_url
                })
            
            graph.query(concept_upload_query, params={"concepts": concept_data})
            print(f"✓ Uploaded {len(concept_data)} concept nodes", flush=True)
        
        # Upload relationships
        if all_relationships:
            relationship_data = []
            for rel in all_relationships:
                relationship_data.append({
                    "from": rel["from"],
                    "to": rel["to"],
                    "type": rel["type"].upper().replace(" ", "_"),
                    "description": rel["description"],
                    "document_name": document_name,
                    "url": document_url
                })
            
            try:
                relationship_upload_query = """
                UNWIND $relationships AS rel
                MATCH (from:Concept {name: rel.from})
                MATCH (to:Concept {name: rel.to})
                MERGE (from)-[:CONCEPT_RELATION {
                    relationship_type: rel.type, 
                    description: rel.description,
                    document_name: rel.document_name,
                    url: rel.url
                }]->(to)
                """
                graph.query(relationship_upload_query, params={"relationships": relationship_data})
                print(f"✓ Uploaded {len(relationship_data)} concept relationships", flush=True)
            except Exception as e:
                log_error(f"⚠️ Error uploading relationships: {e}")
        
        # Connect chunks to concepts
        chunk_concept_connections = []
        for concept in all_concepts:
            concept_name = concept["name"]
            origin_chunks = concept.get("origin_chunks", [])
            
            for chunk_idx in origin_chunks:
                if chunk_idx < len(text_chunks):
                    chunk_text = text_chunks[chunk_idx].lower()
                    concept_name_lower = concept_name.lower()
                    
                    if concept_name_lower in chunk_text:
                        chunk_concept_connections.append({
                            "chunk_id": chunk_idx,
                            "concept_name": concept_name,
                            "document_name": document_name,
                            "url": document_url
                        })
        
        if chunk_concept_connections:
            connection_query = """
            UNWIND $connections AS conn
            MATCH (c:Chunk {id: conn.chunk_id, document_name: conn.document_name})
            MATCH (concept:Concept {name: conn.concept_name})
            MERGE (c)-[:MENTIONS {
                document_name: conn.document_name,
                url: conn.url
            }]->(concept)
            """
            graph.query(connection_query, params={"connections": chunk_concept_connections})
            print(f"✓ Connected {len(chunk_concept_connections)} chunk-concept relationships", flush=True)
        
        # Create vector index(es) for concept nomic_embeddings and/or openai_embeddings
        step_start = time()
        actual_db_name = get_database_name(db_name)
        for emb_list, prop_name, index_name in [
            (concept_embeddings_nomic, "nomic_embeddings", "concept_nomic_embeddings"),
            (concept_embeddings_openai, "openai_embeddings", "concept_openai_embeddings"),
        ]:
            if not emb_list:
                continue
            try:
                embedding_dim = len(emb_list[0])
                create_index_query = f"""
                CREATE VECTOR INDEX {index_name} IF NOT EXISTS
                FOR (n:Concept) ON n.{prop_name}
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {embedding_dim},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
                """
                graph.query(create_index_query)
                print(f"✓ Concept vector index {index_name} created", flush=True)
            except Exception as e:
                print(f"⚠️ Concept index {index_name} creation failed (may already exist): {e}", flush=True)
        
        print(f"✓ Concept generation: {time() - function_start:.2f}s", flush=True)

    except Exception as e:
        log_error(f"Error in concept generation: {e}")
        log_error(f"{traceback.format_exc()}")


def _get_embedding_models(backend: EmbeddingBackend) -> tuple[Optional[Embeddings], Optional[Embeddings]]:
    """Return (nomic_model, openai_model); one or both may be None."""
    nomic_model: Optional[Embeddings] = None
    openai_model: Optional[Embeddings] = None
    if backend in ("nomic", "both"):
        nomic_model = OllamaEmbeddings(model="nomic-embed-text")
    if backend in ("openai", "both"):
        openai_model = OpenAIEmbeddings(model="text-embedding-3-small")
    return nomic_model, openai_model


async def load_files_neo4j_graphrag(
    path: str,
    db_name: str,
    node_labels: list[str] = [],
    rel_labels: list[str] = [],
    prompt_template: str = "",
    generate_concepts: bool = True,
    background_tasks = None,
    url_mapping_dict: dict = None,
    embedding_backend: EmbeddingBackend = "nomic",
) -> None:
    """Load files into Neo4j using GraphRAG.
    embedding_backend: 'nomic' | 'openai' | 'both' — which embeddings to compute and store on Chunk/Concept nodes
    as nomic_embeddings and/or openai_embeddings."""
    try:
        total_start = time()
        log_debug(f"=== Starting load_files_neo4j_graphrag for: {path} ===")
        
        # Initialize embedding model(s)
        step_start = time()
        nomic_model, openai_model = _get_embedding_models(embedding_backend)
        primary_model = nomic_model or openai_model  # for vector index when only one
        print(f"✓ Embedding backend: {embedding_backend} (nomic_embeddings, openai_embeddings)", flush=True)
        print(f"✓ Embedding model initialization: {time() - step_start:.2f}s", flush=True)

        # Parse transcription chunks with metadata (chunk ID, timecodes)
        step_start = time()
        transcription_chunks = parse_transcription_chunks(path)
        
        if not transcription_chunks:
            raise ValueError("No chunks parsed from transcription file")
        
        # Extract text chunks and metadata
        text_chunks = [chunk["text"] for chunk in transcription_chunks]
        chunk_metadata = {
            i: {
                "chunk_id": chunk["chunk_id"],
                "start_time": chunk.get("start_time"),
                "end_time": chunk.get("end_time")
            }
            for i, chunk in enumerate(transcription_chunks)
        }
        
        text_length = sum(len(chunk["text"]) for chunk in transcription_chunks)
        print(f"✓ File processing: {time() - step_start:.2f}s - Parsed {len(transcription_chunks)} chunks, Text length: {text_length}", flush=True)
        
        # If chunks don't have timecodes, we still use them but without time metadata
        chunks_with_timecodes = sum(1 for c in transcription_chunks if c.get("start_time") is not None)
        if chunks_with_timecodes > 0:
            print(f"✓ Found timecodes for {chunks_with_timecodes}/{len(transcription_chunks)} chunks", flush=True)

        # Create embeddings (nomic and/or openai based on embedding_backend)
        step_start = time()
        MAX_TOKENS_PER_BATCH = 200000
        BATCH_SIZE = 100
        
        chunk_embeddings_nomic: list[list[float]] = []
        chunk_embeddings_openai: list[list[float]] = []
        total_cost = 0
        total_tokens = 0
        total_requests = 0
        
        i = 0
        batch_num = 1
        total_batches = (len(text_chunks) + BATCH_SIZE - 1) // BATCH_SIZE
        
        while i < len(text_chunks):
            batch = []
            batch_tokens = 0
            
            for j in range(i, min(i + BATCH_SIZE, len(text_chunks))):
                chunk = text_chunks[j]
                chunk_tokens = len(encoding.encode(chunk))
                
                if batch_tokens + chunk_tokens > MAX_TOKENS_PER_BATCH and batch:
                    break
                
                if chunk_tokens > MAX_TOKENS_PER_BATCH:
                    print(f"⚠️  Skipping chunk {j+1} with {chunk_tokens:,} tokens (exceeds limit)", flush=True)
                    i += 1
                    continue
                
                batch.append(chunk)
                batch_tokens += chunk_tokens
            
            if not batch:
                i += 1
                continue
            
            try:
                if nomic_model:
                    batch_nomic = await nomic_model.aembed_documents(batch)
                    chunk_embeddings_nomic.extend(batch_nomic)
                if openai_model:
                    with get_openai_callback() as cb:
                        batch_openai = await openai_model.aembed_documents(batch)
                        chunk_embeddings_openai.extend(batch_openai)
                        total_cost += cb.total_cost
                        total_tokens += cb.total_tokens
                        total_requests += cb.successful_requests
                
                print(f"📊 Processed batch {batch_num}/{total_batches} - {len(batch)} chunks, {batch_tokens:,} tokens", flush=True)
                batch_num += 1
                i += len(batch)

            except Exception as e:
                log_error(f"❌ Error processing batch {batch_num}: {e}")
                i += len(batch)
        
        print(f"✓ Embedding creation: {time() - step_start:.2f}s", flush=True)
        if openai_model:
            print(f"📊 OpenAI chunk embeddings cost: ${total_cost:.6f} | Tokens: {total_tokens:,} | Requests: {total_requests}", flush=True)

        # Neo4j connection
        step_start = time()
        actual_db_name = get_database_name(db_name)
        graph = Neo4jGraph(
            url=NEO4J_URI,
            username=NEO4J_USERNAME,
            password=NEO4J_PASSWORD,
            database=actual_db_name
        )
        print(f"✓ Neo4j connection setup: {time() - step_start:.2f}s", flush=True)

        # Prepare document data with timecode metadata and nomic_embeddings / openai_embeddings
        step_start = time()
        document_name = os.path.basename(path)
        document_data = []
        document_url = url_mapping_dict.get(document_name, "") if url_mapping_dict else ""
        
        for i, chunk in enumerate(text_chunks):
            metadata = chunk_metadata.get(i, {})
            chunk_data = {
                "chunk_id": metadata.get("chunk_id", i),
                "text": chunk,
                "document_name": document_name,
                "url": document_url,
                "nomic_embeddings": chunk_embeddings_nomic[i] if i < len(chunk_embeddings_nomic) else None,
                "openai_embeddings": chunk_embeddings_openai[i] if i < len(chunk_embeddings_openai) else None,
            }
            if metadata.get("start_time") is not None:
                chunk_data["start_time"] = metadata["start_time"]
            if metadata.get("end_time") is not None:
                chunk_data["end_time"] = metadata["end_time"]
            document_data.append(chunk_data)
        
        print(f"✓ Document data preparation: {time() - step_start:.2f}s", flush=True)
        if document_data:
            first_keys = sorted(document_data[0].keys())
            print(f"   Chunk node properties: {first_keys}", flush=True)

        # Upload to Neo4j with timecode metadata and nomic_embeddings / openai_embeddings (no chunk_embeddings)
        step_start = time()
        upload_query = """
        UNWIND $chunks AS chunk
        MERGE (doc:Document {name: chunk.document_name})
        CREATE (c:Chunk {
            id: chunk.chunk_id,
            text: chunk.text,
            document_name: chunk.document_name,
            url: chunk.url,
            start_time: chunk.start_time,
            end_time: chunk.end_time,
            last_updated: datetime(),
            nomic_embeddings: chunk.nomic_embeddings,
            openai_embeddings: chunk.openai_embeddings
        })
        MERGE (doc)-[:HAS_CHUNK]->(c)
        """
        
        # Remove legacy embedding properties from any existing nodes (from older loader runs)
        try:
            graph.query("MATCH (n:Chunk) WHERE n.chunk_embeddings IS NOT NULL REMOVE n.chunk_embeddings")
            graph.query("MATCH (n:Concept) WHERE n.concept_embeddings IS NOT NULL REMOVE n.concept_embeddings")
        except Exception:
            pass  # Ignore if no such properties

        graph.query(upload_query, params={"chunks": document_data})
        print(f"✓ Data upload to Neo4j: {time() - step_start:.2f}s", flush=True)

        # Create vector index(es) for chunk nomic_embeddings and/or openai_embeddings
        step_start = time()
        actual_db_name = get_database_name(db_name)
        for prop_name, model, index_name in [
            ("nomic_embeddings", nomic_model, "chunk_nomic_embeddings"),
            ("openai_embeddings", openai_model, "chunk_openai_embeddings"),
        ]:
            if model is None:
                continue
            try:
                test_embedding = await model.aembed_query("test")
                embedding_dim = len(test_embedding)
                create_index_query = f"""
                CREATE VECTOR INDEX {index_name} IF NOT EXISTS
                FOR (n:Chunk) ON n.{prop_name}
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {embedding_dim},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
                """
                graph.query(create_index_query)
                print(f"✓ Vector index {index_name}: {time() - step_start:.2f}s", flush=True)
            except Exception as e:
                print(f"⚠️ Index {index_name} creation failed (may already exist): {e}", flush=True)

        # Generate concepts if enabled
        if generate_concepts:
            await generate_concepts_sync(
                text_chunks=text_chunks,
                document_name=document_name,
                nomic_model=nomic_model,
                openai_model=openai_model,
                embedding_backend=embedding_backend,
                db_name=db_name,
                node_labels=node_labels,
                rel_labels=rel_labels,
                prompt_template=prompt_template,
                url_mapping_dict=url_mapping_dict
            )
        
        total_time = time() - total_start
        print(f"📄 Total processing time: {total_time:.2f}s", flush=True)
        print(f"📄 Document uploaded successfully with {len(text_chunks)} chunks", flush=True)

    except Exception as e:
        error_msg = f"Error in load_files_neo4j_graphrag: {e}\n{traceback.format_exc()}"
        log_error(error_msg)
        raise RuntimeError(f"GraphRAG processing failed: {str(e)}") from e


async def update_chunk_in_neo4j(
    document_name: str,
    chunk_id: int,
    new_text: str,
    db_name: str = "lng_transcriptions"
) -> dict:
    """
    Update a specific chunk's text and regenerate its embedding in Neo4j.
    This allows manual corrections to transcriptions to be reflected in the graph.
    
    Args:
        document_name: Name of the document (transcription file)
        chunk_id: The chunk ID to update (0-indexed)
        new_text: The new text content for the chunk
        db_name: Database name (will be adjusted for Community Edition)
    
    Returns:
        dict with success status and updated chunk info
    """
    try:
        actual_db_name = get_database_name(db_name)
        
        # Initialize embedding model
        embeddings_model = OllamaEmbeddings(model="nomic-embed-text")
        
        # Generate new embedding for the updated text
        print(f"🔄 Regenerating embedding for chunk {chunk_id} in {document_name}...", flush=True)
        new_embedding = await embeddings_model.aembed_query(new_text)
        
        # Connect to Neo4j
        graph = Neo4jGraph(
            url=NEO4J_URI,
            username=NEO4J_USERNAME,
            password=NEO4J_PASSWORD,
            database=actual_db_name
        )
        
        # Update the chunk node (nomic_embeddings used for vector index chunk_nomic_embeddings)
        update_query = """
        MATCH (c:Chunk {document_name: $document_name, id: $chunk_id})
        SET c.text = $new_text,
            c.nomic_embeddings = $new_embedding,
            c.last_updated = datetime()
        RETURN c
        """
        
        result = graph.query(
            update_query,
            params={
                "document_name": document_name,
                "chunk_id": chunk_id,
                "new_text": new_text,
                "new_embedding": new_embedding
            }
        )
        
        if not result:
            raise ValueError(f"Chunk {chunk_id} not found in document {document_name}")
        
        # Vector index chunk_nomic_embeddings is updated when node property is set
        vector_store = Neo4jVector(
            embedding=embeddings_model,
            url=NEO4J_URI,
            username=NEO4J_USERNAME,
            password=NEO4J_PASSWORD,
            database=actual_db_name,
            index_name="chunk_nomic_embeddings",
            embedding_node_property="nomic_embeddings",
        )
        
        # Delete old vector and add new one
        delete_query = """
        MATCH (c:Chunk {document_name: $document_name, id: $chunk_id})
        DETACH DELETE c
        """
        graph.query(delete_query, params={"document_name": document_name, "chunk_id": chunk_id})
        
        # Re-add chunk with new embedding (nomic_embeddings)
        create_query = """
        MATCH (doc:Document {name: $document_name})
        CREATE (c:Chunk {
            id: $chunk_id,
            text: $new_text,
            nomic_embeddings: $new_embedding,
            document_name: $document_name,
            last_updated: datetime()
        })
        MERGE (doc)-[:HAS_CHUNK]->(c)
        RETURN c
        """
        graph.query(create_query, params={
            "document_name": document_name,
            "chunk_id": chunk_id,
            "new_text": new_text,
            "new_embedding": new_embedding
        })
        
        # Update vector store
        vector_store.add_texts([new_text], metadatas=[{
            "document_name": document_name,
            "chunk_id": chunk_id
        }])
        
        print(f"✓ Successfully updated chunk {chunk_id} in {document_name}", flush=True)
        
        return {
            "success": True,
            "document_name": document_name,
            "chunk_id": chunk_id,
            "message": "Chunk updated successfully"
        }
        
    except Exception as e:
        error_msg = f"Error updating chunk: {e}\n{traceback.format_exc()}"
        log_error(error_msg)
        return {
            "success": False,
            "error": str(e)
        }


async def write_edit_to_file(
    edit_file_path: str,
    document_name: str,
    chunk_id: int,
    new_text: str
) -> bool:
    """
    Write an edit record to the "_edit" file. Appends edits to the file.
    Does not modify the original transcription file.
    
    Args:
        edit_file_path: Path to the edit file (e.g., "transcriptions/edit/filename_combined_edit.txt")
        document_name: Name of the document (for reference)
        chunk_id: The chunk ID that was edited (0-indexed)
        new_text: The new text content
    
    Returns:
        True if successful, False otherwise
    """
    try:
        from datetime import datetime
        
        # Create directory if it doesn't exist
        edit_dir = os.path.dirname(edit_file_path)
        if edit_dir and not os.path.exists(edit_dir):
            os.makedirs(edit_dir, exist_ok=True)
        
        # Format: timestamp | document_name | chunk_id | new_text
        timestamp = datetime.now().isoformat()
        edit_record = f"=== EDIT {timestamp} ===\n"
        edit_record += f"Document: {document_name}\n"
        edit_record += f"Chunk ID: {chunk_id}\n"
        edit_record += f"New Text:\n{new_text}\n"
        edit_record += "===\n\n"
        
        # Append to edit file (create if doesn't exist)
        with open(edit_file_path, "a", encoding="utf-8") as f:
            f.write(edit_record)
        
        print(f"✓ Wrote edit to file: {edit_file_path} (chunk {chunk_id})", flush=True)
        return True

    except Exception as e:
        log_error(f"Error writing edit to file: {e}")
        return False


def get_transcription_file_path(filename: str, transcriptions_dir: str = "./transcriptions", edit_dir: str = "./transcriptions/edit") -> Optional[str]:
    """
    Get the path to transcription file, checking edit file first if it exists.
    
    Args:
        filename: Name of the transcription file (e.g., "filename_combined.txt")
        transcriptions_dir: Directory containing original transcription files
        edit_dir: Directory containing edit files
    
    Returns:
        Path to the file to use (edit file if exists, otherwise original), or None if neither exists
    """
    # Check for edit file first
    edit_filename = filename.replace('_combined.txt', '_combined_edit.txt')
    edit_path = os.path.join(edit_dir, edit_filename)
    if os.path.exists(edit_path):
        return edit_path
    
    # Fall back to original file
    original_path = os.path.join(transcriptions_dir, filename)
    if os.path.exists(original_path):
        return original_path
    
    return None


async def delete_chunk_in_neo4j(
    document_name: str,
    chunk_id: int,
    db_name: str = "lng_transcriptions"
) -> dict:
    """
    Delete a specific chunk node from Neo4j by id and document_name.
    This removes the chunk node and all its relationships.
    
    Args:
        document_name: Name of the document (transcription file)
        chunk_id: The chunk ID to delete (0-indexed)
        db_name: Database name (will be adjusted for Community Edition)
    
    Returns:
        dict with success status
    """
    try:
        actual_db_name = get_database_name(db_name)
        
        # Connect to Neo4j
        graph = Neo4jGraph(
            url=NEO4J_URI,
            username=NEO4J_USERNAME,
            password=NEO4J_PASSWORD,
            database=actual_db_name
        )
        
        # Delete the chunk node and all its relationships
        delete_query = """
        MATCH (c:Chunk {document_name: $document_name, id: $chunk_id})
        DETACH DELETE c
        RETURN count(c) as deleted_count
        """
        
        result = graph.query(
            delete_query,
            params={
                "document_name": document_name,
                "chunk_id": chunk_id
            }
        )
        
        # Check if chunk was found and deleted
        # Result format from Neo4jGraph.query is a list of records
        deleted_count = 0
        if result and len(result) > 0:
            # The result is a list of dictionaries/records
            first_record = result[0]
            if isinstance(first_record, dict):
                deleted_count = first_record.get("deleted_count", 0)
            else:
                # If it's a record object, try to access the value
                deleted_count = getattr(first_record, "deleted_count", 0) if hasattr(first_record, "deleted_count") else 0
        
        if deleted_count == 0:
            raise ValueError(f"Chunk {chunk_id} not found in document {document_name}")
        
        # Also remove from vector index if it exists
        # The vector index should automatically handle deletion when the node is deleted
        # But we can explicitly delete it if needed
        try:
            vector_store = Neo4jVector(
                embedding=OllamaEmbeddings(model="nomic-embed-text"),  # Dummy embedding, just for deletion
                url=NEO4J_URI,
                username=NEO4J_USERNAME,
                password=NEO4J_PASSWORD,
                database=actual_db_name,
                index_name="chunk_nomic_embeddings",
            )
            # The vector index deletion is handled automatically by Neo4j when the node is deleted
        except Exception as e:
            # Vector index deletion is optional, don't fail if it doesn't exist
            log_debug(f"Note: Could not access vector index for deletion (this is OK): {e}")
        
        print(f"✓ Successfully deleted chunk {chunk_id} from {document_name}", flush=True)
        
        return {
            "success": True,
            "document_name": document_name,
            "chunk_id": chunk_id,
            "message": "Chunk deleted successfully"
        }
        
    except Exception as e:
        error_msg = f"Error deleting chunk: {e}\n{traceback.format_exc()}"
        log_error(error_msg)
        return {
            "success": False,
            "error": str(e)
        }


async def delete_chunk_from_transcription_file(
    transcription_path: str,
    chunk_id: int
) -> bool:
    """
    Delete a specific chunk from a transcription file.
    
    Args:
        transcription_path: Path to the transcription file
        chunk_id: The chunk ID to delete (0-indexed, but file uses 1-indexed)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        with open(transcription_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Find and remove the chunk
        # Pattern: === Chunk N [timecodes] ===\n<text>
        file_chunk_id = chunk_id + 1  # File uses 1-indexed
        
        # Match chunk header and content, remove entire chunk
        pattern = rf'=== Chunk {file_chunk_id}(?: \[[^\]]+\])? ===\n.*?(?=\n=== Chunk|\Z)'
        
        new_content = re.sub(pattern, '', content, flags=re.DOTALL)
        
        # Clean up any double newlines that might result
        new_content = re.sub(r'\n{3,}', '\n\n', new_content)
        
        # Write back to file
        with open(transcription_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        print(f"✓ Deleted chunk {file_chunk_id} from transcription file: {transcription_path}", flush=True)
        return True

    except Exception as e:
        log_error(f"Error deleting chunk from transcription file: {e}")
        return False

