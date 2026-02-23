# LNG-GraphRAG

A comprehensive GraphRAG (Graph Retrieval-Augmented Generation) project that combines advanced audio processing with graph-based knowledge retrieval.

## Project Overview

This project integrates multiple components to create a powerful GraphRAG system:

- **Breeze-ASR-25**: Advanced speech recognition capabilities
- **VODs**: Video content processing and download functionality
- **GraphRAG**: Knowledge graph construction and retrieval

## Features

- 🎤 **Audio Processing**: High-quality speech recognition using Breeze-ASR-25
- 📹 **Video Processing**: Enhanced YouTube video download with anti-detection measures
- 🧠 **GraphRAG**: Intelligent knowledge graph construction and retrieval
- 🔄 **Modular Design**: Flexible architecture for easy extension
- 🛡️ **Anti-Detection**: Advanced retry logic, user-agent rotation, and cookie authentication
- 🔧 **Error Handling**: Comprehensive error handling with detailed user feedback

## Getting Started

### Prerequisites

- Python 3.8+
- Git

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd LNG-GraphRAG
```

2. Set up the environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Usage

#### YouTube Video Download

1. **Export Cookies** (Required to avoid 403 errors):
```bash
python VODs/export_cookies_guide.py
```

2. **Download Videos**:
```bash
python VODs/download_from_youtube.py
```

3. **Process with ASR**:
```bash
python run_batch_asr.py
```

#### Testing

Run the UI to test functionality:
```bash
python launch_ui.py
```

## Project Structure

```
LNG-GraphRAG/
├── Breeze-ASR-25/          # Speech recognition module
├── VODs/                   # Video processing module
├── todo.md                 # Project roadmap and tasks
└── README.md              # This file
```

## Contributing

Please see our [todo.md](todo.md) for current development goals and tasks.

## License

[License information to be added]

## Roadmap

See [todo.md](todo.md) for detailed project roadmap and completed tasks.

## Standard Operating Procedure (SOP)

### Complete System Setup and Running Guide

This SOP covers the complete workflow from initial setup to running the full system.

#### Prerequisites Checklist

- [ ] Python 3.8+ installed
- [ ] Docker installed and running
- [ ] OpenAI API key obtained
- [ ] Git repository cloned
- [ ] Virtual environment created

#### Step 1: Initial Setup

```bash
# 1. Navigate to project directory
cd LNG-GraphRAG

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file (optional, for environment variables)
cat > .env << EOF
OPENAI_API_KEY=your-openai-api-key-here
NEO4J_IP=localhost
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=lng-graphrag-password
NEO4J_DB_NAME=lng_transcriptions
EOF
```

#### Step 2: Start Neo4j Database

```bash
# Start Neo4j using the setup script
./setup_neo4j.sh

# Verify Neo4j is running
docker ps | grep lng-neo4j

# Check Neo4j is ready (should return 1)
docker exec lng-neo4j cypher-shell -u neo4j -p lng-graphrag-password "RETURN 1"
```

**Expected Output:**
- Container `lng-neo4j` should be running
- Neo4j Browser available at http://localhost:7474
- Bolt connection available at bolt://localhost:7687

**Note:** The setup uses Neo4j Community Edition by default. The code automatically detects this and uses the default database. If you're using Enterprise Edition, it will create named databases as specified.

#### Step 3: Download YouTube Videos (Optional)

If you need to download new videos:

```bash
# 1. Export YouTube cookies (required for age-restricted videos)
# Follow instructions in VODs/export_cookies_guide.py
# Place cookies file at: VODs/www.youtube.com_cookies.txt

# 2. Download videos
python VODs/download_from_youtube.py

# This will:
# - Fetch video list from YouTube channel
# - Download audio as WAV files to ./VODs/
# - Update VODs/videos.csv with download status
```

#### Step 4: Process Audio to Transcriptions (Optional)

If you have new WAV files to transcribe:

```bash
# Process audio files with ASR
# (Note: This requires the ASR processing script)
python run_batch_asr.py  # If available
```

#### Step 5: Load Transcriptions into Neo4j

```bash
# Set OpenAI API key if not in .env file
export OPENAI_API_KEY='your-openai-api-key-here'

# Option A: Ensure Neo4j is running, then load (uses Ollama nomic embeddings by default)
python run_embeddings_to_neo4j.py

# Option B: Load directly (you must start Neo4j first)
python load_transcriptions_to_neo4j.py

# With embedding choice: nomic only (default), openai only, or both
python load_transcriptions_to_neo4j.py --embedding both

# Wipe existing graph and reload (e.g. to fix legacy chunk_embeddings → nomic_embeddings/openai_embeddings)
python load_transcriptions_to_neo4j.py --embedding both --clean
```

**What happens:**
1. Script checks Neo4j connection (waits if not ready)
2. Uses default database `neo4j` (Community Edition) or `lng_transcriptions` (Enterprise)
3. Processes each `*_combined.txt` in `./transcriptions/`
4. Generates embeddings (Ollama nomic and/or OpenAI) and stores them as **`nomic_embeddings`** and **`openai_embeddings`** on Chunk/Concept nodes
5. Extracts concepts and relationships
6. Builds the knowledge graph

**Expected Output:**
- Progress for each transcription file
- Cost tracking for OpenAI when using `--embedding openai` or `both`
- Summary of successful/failed loads

#### Step 6: Launch Web Dashboard

```bash
# Start the web application
python launch_web.py

# Or directly:
python web_app.py
```

**Access the dashboard:**
- URL: http://localhost:5000
- Three tabs available:
  1. **Download Status**: Monitor YouTube download progress
  2. **Transcriptions**: Split view—left: scrollable list and chunk text (with edit/Neo4j sync); right: fixed YouTube player for the selected transcription (URL from `VODs/videos.csv`). Use this to listen while annotating.
  3. **GraphRAG**: Query Neo4j knowledge graph

#### Step 7: Query the Knowledge Graph

**In Neo4j Browser (http://localhost:7474):**
```cypher
// Count all documents
MATCH (d:Document) RETURN count(d) as total_documents

// Count all concepts
MATCH (c:Concept) RETURN count(c) as total_concepts

// Find concepts by keyword
MATCH (c:Concept)
WHERE c.name CONTAINS 'keyword'
RETURN c.name, c.type, c.description
LIMIT 10

// Find relationships
MATCH (c1:Concept)-[r]->(c2:Concept)
RETURN c1.name, type(r), c2.name
LIMIT 25
```

**In Web Dashboard GraphRAG Tab:**
- Ask questions in **natural language** (LLM converts to Cypher and answers from graph context). Default LLM is OpenAI (gpt-4o-mini). To save token cost, set `NL_QUERY_LLM=ollama` and run Ollama with e.g. `ollama pull llama3.2` (see WEB_README.md).
- Enter **Cypher queries** directly and view results in JSON format

### Daily Operations

#### Starting the System

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Start Neo4j (and optional MySQL for user login) if not already running
docker-compose up -d
# OR
./setup_neo4j.sh
# (docker-compose also starts MySQL on port 3306 for auth and for desktop UI pipeline state; see AUTH_SETUP.md)

# 3. (Optional) Restore database from dump if available
python auto_restore_neo4j.py

# 4. Verify Neo4j is ready
docker ps | grep lng-neo4j

# 5. Start web dashboard
python launch_web.py
```

#### Stopping the System

```bash
# Stop web dashboard: Press Ctrl+C in the terminal

# Stop Neo4j (optional - can leave running)
docker-compose down
# OR
docker stop lng-neo4j
```

#### Adding New Transcriptions

**Add a single file (no DB wipe):**
```bash
# From an existing _combined.txt
python load_single_to_neo4j.py ./transcriptions/MyVideo_combined.txt

# From a single WAV (runs ASR first, then loads)
python load_single_to_neo4j.py ./VODs/MyVideo.wav

# With both nomic and OpenAI embeddings
python load_single_to_neo4j.py ./transcriptions/MyVideo_combined.txt --embedding both
```

**Add multiple new files:**
```bash
# 1. Place new transcription files in ./transcriptions/
#    Format: {title}_combined.txt

# 2. Load into Neo4j (only new documents are added; use --clean to wipe and reload all)
python load_transcriptions_to_neo4j.py --embedding nomic
```

**Transcriptions missing timestamps:** If some files use `=== Chunk 1 ===` instead of `=== Chunk 1 [0.00s - 94.49s] ===`:
```bash
# Find which transcriptions lack timestamps and get their YouTube URLs
python find_transcriptions_without_timestamps.py

# Redownload those videos and rerun ASR (same format with timestamps)
python redownload_rerun_no_timestamps.py

# Or for one title only
python redownload_rerun_no_timestamps.py --title "Exact title from CSV"
```

#### Backup and Restore Neo4j Database

**Create a backup:**
```bash
python dump_neo4j.py
```

This creates a timestamped dump file in `./neo4j/` directory.

**Restore from backup:**
```bash
# Restore from latest dump
python restore_neo4j.py

# Restore from specific dump file
python restore_neo4j.py --dump-file neo4j_dump_20250101_120000.dump
```

**Auto-restore on startup:**
```bash
# After starting Neo4j, automatically restore if database is empty
python auto_restore_neo4j.py

# Force restore even if database has data
python auto_restore_neo4j.py --force
```

See `NEO4J_BACKUP.md` for detailed backup/restore documentation.

### Troubleshooting Quick Reference

| Issue | Solution |
|-------|----------|
| Neo4j connection refused | Run `./setup_neo4j.sh` or `docker-compose up -d` |
| OpenAI API errors | Check `OPENAI_API_KEY` is set correctly |
| Import errors | Run `pip install -r requirements.txt` |
| Port already in use | Change port in `docker-compose.yml` or `web_app.py` |
| Database not found | Community Edition has only default DB `neo4j`; app uses it automatically. See NEO4J_SETUP.md. |
| Transcription files not found | Check `./transcriptions/` directory exists |

### System Status Checks

```bash
# Check Neo4j status
docker ps | grep lng-neo4j
docker logs lng-neo4j | tail -20

# Check transcription files
ls -lh transcriptions/*.txt | wc -l

# Check download status
cat VODs/videos.csv | wc -l

# Test Neo4j connection
docker exec lng-neo4j cypher-shell -u neo4j -p lng-graphrag-password "SHOW DATABASES"
```

### Environment Variables Reference

Create a `.env` file in the project root:

```bash
# Required
OPENAI_API_KEY=your-openai-api-key-here

# Neo4j Connection (defaults shown)
NEO4J_IP=localhost
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=lng-graphrag-password
NEO4J_DB_NAME=lng_transcriptions

# Natural language query LLM (optional; saves OpenAI cost when set to ollama)
# NL_QUERY_LLM=openai   # default: uses gpt-4o-mini
# NL_QUERY_LLM=ollama   # local model, no API cost
# OLLAMA_NL_MODEL=llama3.2   # when NL_QUERY_LLM=ollama
```

### File Structure Reference

```
LNG-GraphRAG/
├── transcriptions/          # Transcription files (*_combined.txt)
├── VODs/
│   ├── videos.csv         # Download status tracking
│   ├── *.wav               # Audio files
│   └── www.youtube.com_cookies.txt  # YouTube cookies
├── graphrag/
│   └── own_graph_rag.py   # GraphRAG implementation (nomic/openai embeddings)
├── templates/
│   └── index.html         # Web dashboard UI
├── web_app.py             # Flask web server
├── load_transcriptions_to_neo4j.py  # Batch loader (--embedding, --clean)
├── load_single_to_neo4j.py          # Single transcription or WAV → Neo4j (no wipe)
├── run_embeddings_to_neo4j.py      # Ensure Neo4j + load all (--embedding, --clean)
├── find_transcriptions_without_timestamps.py   # List files missing timecodes
├── redownload_rerun_no_timestamps.py           # Redownload + ASR for those files
├── setup_neo4j.sh         # Neo4j setup script
├── docker-compose.yml     # Neo4j + MySQL (auth) Docker config
├── dump_neo4j.py          # Backup Neo4j database
├── restore_neo4j.py       # Restore Neo4j database
├── auto_restore_neo4j.py  # Auto-restore on startup
├── neo4j/                 # Database dumps (gitignored)
└── .env                   # Environment variables (create this)
```

### Performance Notes

- **Transcription Loading**: ~2-5 minutes per file (depends on file size and API rate limits)
- **Concept Generation**: Adds ~30-60% more time per file
- **Neo4j Startup**: ~10-30 seconds after container starts
- **Web Dashboard**: Starts immediately, no heavy processing

### Next Steps After Setup

1. ✅ Verify all transcriptions are loaded: Check Neo4j Browser
2. ✅ Test GraphRAG queries: Use web dashboard GraphRAG tab
3. ✅ Explore knowledge graph: Run example queries
4. ✅ Monitor system: Check logs and status regularly
