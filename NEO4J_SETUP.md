# Neo4j Setup and Transcription Loading Guide

This guide will help you set up Neo4j in Docker and load transcriptions into the knowledge graph.

## Prerequisites

1. **Docker** installed and running
2. **OpenAI API Key** for concept generation (LLM) and for `--embedding openai` or `both`
3. **Ollama** with `nomic-embed-text` for local embeddings when using `--embedding nomic` or `both` (run `ollama pull nomic-embed-text`)
4. Python dependencies installed: `pip install -r requirements.txt`

## Neo4j Edition Support

This project supports both **Neo4j Community Edition** and **Enterprise Edition**:

- **Community Edition** (Docker default): Has only one database, the default **`neo4j`**. There is no separate `lng_transcriptions` database — the app uses **`neo4j`** and refers to it as "lng_transcriptions" in messages. In Neo4j Browser, `SHOW DATABASES` will only list `neo4j` and `system`.
- **Enterprise Edition**: Can create and use multiple named databases (e.g. `lng_transcriptions`).

The code automatically detects which edition you're using and uses the correct database. No configuration needed!

## Step 1: Start Neo4j Docker Container

### Option A: Using the setup script (Recommended)

```bash
./setup_neo4j.sh
```

### Option B: Manual Docker setup

```bash
# Pull Neo4j image
docker pull neo4j:5.15-community

# Start Neo4j using docker-compose
docker-compose up -d

# Or manually:
docker run -d \
  --name lng-neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/lng-graphrag-password \
  neo4j:5.15-community
```

### Verify Neo4j is running

```bash
# Check container status
docker ps | grep lng-neo4j

# Check logs
docker logs lng-neo4j

# Test connection
docker exec lng-neo4j cypher-shell -u neo4j -p lng-graphrag-password "RETURN 1"
```

## Step 2: Set Environment Variables

```bash
# Set OpenAI API key (required for embeddings)
export OPENAI_API_KEY='your-openai-api-key-here'

# Optional: Override Neo4j connection settings
export NEO4J_URI='bolt://localhost:7687'
export NEO4J_USERNAME='neo4j'
export NEO4J_PASSWORD='lng-graphrag-password'
export NEO4J_DB_NAME='lng_transcriptions'
```

## Step 3: Load Transcriptions

### Embedding options

Chunk and Concept nodes store embeddings in two optional properties:

- **`nomic_embeddings`** — from Ollama `nomic-embed-text` (local)
- **`openai_embeddings`** — from OpenAI `text-embedding-3-small` (API)

Use `--embedding nomic` (default), `--embedding openai`, or `--embedding both`. Vector indexes are created for each property you use (`chunk_nomic_embeddings`, `chunk_openai_embeddings`, and the same for concepts).

**Never re-run embeddings after Neo4j rebuild:** Run load once with nomic (default), then `python dump_neo4j.py` (or use `--dump-after`). After any Neo4j Docker rebuild, run `python restore_neo4j.py` instead of the embedding script. See [NEO4J_BACKUP.md](NEO4J_BACKUP.md#never-re-run-embeddings-after-neo4j-rebuild).

### Load all transcriptions

```bash
# Ensure Neo4j is running, then load (default: nomic embeddings only)
python run_embeddings_to_neo4j.py

# Or load directly (Neo4j must already be running)
python load_transcriptions_to_neo4j.py

# With both nomic and OpenAI embeddings
python load_transcriptions_to_neo4j.py --embedding both

# Wipe existing graph and reload (removes old data; use after schema/embedding changes)
python load_transcriptions_to_neo4j.py --embedding both --clean
```

This will:
- Use the default database `neo4j` (Community Edition) or create/use `lng_transcriptions` (Enterprise)
- Process each `*_combined.txt` in `./transcriptions/`
- Generate embeddings and store them as `nomic_embeddings` and/or `openai_embeddings` on Chunk/Concept nodes
- Extract concepts and relationships
- Build the knowledge graph

### Process specific files

You can modify `load_transcriptions_to_neo4j.py` to filter specific files, or use `load_single_to_neo4j.py` for one file (see below).

### Add a single transcription or WAV to existing Neo4j

To add one new transcription (or one WAV) **without** wiping the database:

```bash
# From a _combined.txt file (same format as in ./transcriptions/)
python load_single_to_neo4j.py ./transcriptions/MyVideo_combined.txt

# From a single WAV: runs ASR first, then loads the produced _combined.txt
python load_single_to_neo4j.py ./VODs/MyVideo.wav

# With OpenAI + Nomic embeddings
python load_single_to_neo4j.py ./transcriptions/MyVideo_combined.txt --embedding both
```

The script uses the same pipeline (chunks, embeddings, concepts) and appends to the existing graph. Ensure Neo4j is running and `OPENAI_API_KEY` is set if you use concept generation or `--embedding openai|both`.

### Transcriptions without timestamps

Transcriptions should use the format `=== Chunk 1 [0.00s - 94.49s] ===`. If some files only have `=== Chunk 1 ===` (no timecodes):

```bash
# Find which transcriptions lack timestamps and get their YouTube URLs
python find_transcriptions_without_timestamps.py

# Redownload those videos and rerun ASR to produce the same format with timestamps
python redownload_rerun_no_timestamps.py

# Single title (exact match with videos.csv)
python redownload_rerun_no_timestamps.py --title "Exact video title"

# Only rerun ASR (WAVs already present)
python redownload_rerun_no_timestamps.py --skip-download
```

Then load (or reload) transcriptions as in Step 3.

### Manual transcription fixes and embeddings

When you correct chunk text (e.g. fix ASR mistakes), embeddings should stay in sync. There are two supported flows:

1. **Edit file + reload**  
   Edits are stored in `transcriptions/edit/<doc>_combined_edit.txt` in the format `=== EDIT ... ===` (Document, Chunk ID, New Text). When you **reload** that document (e.g. via `load_single_to_neo4j.py` or a full `load_transcriptions_to_neo4j.py`), the loader applies those edits to the chunk text and recomputes **both** nomic and OpenAI embeddings for the whole document. Use this when you have many edits or prefer file-based history.

2. **In-place update (e.g. web UI)**  
   Saving a chunk edit from the web app (or any caller of `update_chunk_in_neo4j`) updates the Chunk node in Neo4j and regenerates embeddings for that chunk only. By default **both** `nomic_embeddings` and `openai_embeddings` are updated so vector search stays consistent. The same edit is also written to the `_combined_edit.txt` file for that document. The **original** `transcriptions/<doc>_combined.txt` is never modified; only the edit file is updated.

So in both flows, **nomic and OpenAI embeddings are updated** to match the adjusted chunk text. When the app or loader reads a transcription, it uses the edit file when present and merges edits with the original, so your corrections are the effective source of truth.

## Step 4: Access Neo4j

### Neo4j Browser
Open in your browser: http://localhost:7474
- Username: `neo4j`
- Password: `lng-graphrag-password`

### Query Examples

```cypher
// Count all documents
MATCH (d:Document) RETURN count(d) as total_documents

// Count all chunks
MATCH (c:Chunk) RETURN count(c) as total_chunks

// Count all concepts
MATCH (concept:Concept) RETURN count(concept) as total_concepts

// Find concepts related to a topic
MATCH (c:Concept)
WHERE c.name CONTAINS 'keyword'
RETURN c.name, c.type, c.description
LIMIT 10

// Find relationships between concepts
MATCH (c1:Concept)-[r]->(c2:Concept)
RETURN c1.name, type(r), c2.name
LIMIT 25

// Find chunks mentioning a concept
MATCH (chunk:Chunk)-[:MENTIONS]->(concept:Concept)
WHERE concept.name = 'ConceptName'
RETURN chunk.text, chunk.document_name
LIMIT 10
```

## Step 5: Use GraphRAG in Web Dashboard

The web dashboard (`http://localhost:5000`) now has a GraphRAG tab where you can:

1. Enter Cypher queries
2. Execute them against the Neo4j database
3. View results in JSON format

### Example Queries for Web Dashboard

```cypher
// Get all concepts
MATCH (c:Concept) RETURN c.name, c.type, c.description LIMIT 25

// Get document statistics
MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)
RETURN d.name, count(c) as chunk_count
ORDER BY chunk_count DESC

// Find related concepts
MATCH (c1:Concept)-[r]->(c2:Concept)
RETURN c1.name, type(r), c2.name
LIMIT 25
```

## Troubleshooting

### Neo4j container won't start

```bash
# Check Docker logs
docker logs lng-neo4j

# Check if port is already in use
lsof -i :7474
lsof -i :7687

# Stop and remove existing container
docker stop lng-neo4j
docker rm lng-neo4j
```

### Connection errors

- Verify Neo4j is running: `docker ps | grep neo4j`
- Check connection: `docker exec lng-neo4j cypher-shell -u neo4j -p lng-graphrag-password "RETURN 1"`
- Verify environment variables are set correctly

### Import errors

- Make sure `OPENAI_API_KEY` is set
- Check that transcription files exist in `./transcriptions/`
- Verify the graphrag module can be imported
- Check Python dependencies: `pip install -r requirements.txt`

### Database not found / No "lng_transcriptions" database

- **Community Edition (Docker default):** There is no separate `lng_transcriptions` database. The app uses the default database **`neo4j`**. Run `SHOW DATABASES` — you will only see `neo4j` and `system`. Data is stored in `neo4j`.
- **Enterprise Edition:** The loader can create/use a named database `lng_transcriptions` if supported.
- If you see "Database not found", ensure the Neo4j container is running and the app has detected the correct edition (check startup messages for "Community Edition" or "Enterprise Edition").

## Stopping Neo4j

```bash
# Stop container
docker-compose down

# Or manually
docker stop lng-neo4j
docker rm lng-neo4j
```

## Data Persistence

Data is stored in Docker volumes:
- `neo4j_data`: Database data
- `neo4j_logs`: Log files

To remove all data:
```bash
docker-compose down -v
```

## Next Steps

1. Explore the graph in Neo4j Browser
2. Use the GraphRAG tab in the web dashboard
3. Query concepts and relationships
4. Build custom queries for your use case

