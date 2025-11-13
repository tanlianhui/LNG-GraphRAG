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

# Load all transcriptions into Neo4j
python load_transcriptions_to_neo4j.py
```

**What happens:**
1. Script checks Neo4j connection (waits if not ready)
2. Creates `lng_transcriptions` database if needed
3. Processes each transcription file in `./transcriptions/`
4. Generates embeddings for text chunks
5. Extracts concepts and relationships
6. Builds knowledge graph in Neo4j

**Expected Output:**
- Progress for each transcription file
- Cost tracking for OpenAI API calls
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
  2. **Transcriptions**: Browse and view transcriptions
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
- Enter Cypher queries directly
- View results in JSON format
- Execute queries against the knowledge graph

### Daily Operations

#### Starting the System

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Start Neo4j (if not already running)
docker-compose up -d
# OR
./setup_neo4j.sh

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

```bash
# 1. Place new transcription files in ./transcriptions/
#    Format: {title}_combined.txt

# 2. Load into Neo4j
python load_transcriptions_to_neo4j.py

# The script will:
# - Skip already processed files (based on document name)
# - Process only new files
# - Update the knowledge graph
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
| Database not found | Database is created automatically on first load |
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
```

### File Structure Reference

```
LNG-GraphRAG/
├── transcriptions/          # Transcription files (*_combined.txt)
├── VODs/
│   ├── videos.csv          # Download status tracking
│   ├── *.wav               # Audio files
│   └── www.youtube.com_cookies.txt  # YouTube cookies
├── graphrag/
│   └── own_graph_rag.py   # GraphRAG implementation
├── templates/
│   └── index.html         # Web dashboard UI
├── web_app.py             # Flask web server
├── load_transcriptions_to_neo4j.py  # Transcription loader
├── setup_neo4j.sh         # Neo4j setup script
├── docker-compose.yml     # Neo4j Docker config
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
