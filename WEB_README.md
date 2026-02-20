# LNG GraphRAG Web Dashboard

A modern web interface for monitoring YouTube downloads, viewing transcriptions, and querying the GraphRAG knowledge graph.

## Features

### 📥 Download Status Tab
- Real-time status monitoring of YouTube video downloads
- Filter by status (completed, pending, failed, skipped)
- Search functionality
- Visual indicators for WAV files and transcriptions
- Direct links to YouTube videos

### 📝 Transcriptions Tab
- **Split layout**: left = transcription list and chunk content; right = **fixed YouTube player** for the selected video (so annotators can listen while editing).
- **YouTube player**: When you expand a transcription whose title matches a row in `VODs/videos.csv`, the right half shows the embedded YouTube video for that URL. The right panel stays fixed while the left side scrolls.
- Browse all available transcriptions; collapsible sections per file.
- Chunk-based display (organized by audio chunks) with edit/delete and Neo4j sync.
- File metadata (size, filename). Lazy loading of transcription content.
- The transcriptions API (`GET /api/transcriptions`) includes an optional `url` field per item when the title is found in `videos.csv`.

**Where edits are saved:** Edits from the webpage are **not** written back to the original `transcriptions/<name>_combined.txt` file. They are appended to **edit files** in `transcriptions/edit/<name>_combined_edit.txt`. The app (and Neo4j loader) always prefer the edit file when it exists and merge edits with the original when reading, so your corrections are the effective source of truth. The original file is left unchanged so you keep a clean ASR output and a separate record of human edits.

### 🕸️ GraphRAG Tab
- Neo4j Cypher query interface
- Execute queries against the knowledge graph
- Results display with JSON formatting
- Ready for future GraphRAG implementation

## Optional: User login and history

You can enable a **user login system** with a separate **MySQL** database. When enabled, users can register and log in; the app records **transcription edit history** and **query history** per user. See **[AUTH_SETUP.md](AUTH_SETUP.md)** for MySQL setup and environment variables. If MySQL is not configured, the app runs without login and the dashboard works as before.

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Make sure you have:
   - `VODs/videos.csv` - Download status CSV file
   - `transcriptions/` - Directory with transcription files
   - `VODs/` - Directory with downloaded WAV files

## Usage

### Start the Web Server

```bash
python launch_web.py
```

Or directly:
```bash
python web_app.py
```

### Access the Dashboard

Open your browser and navigate to:
```
http://localhost:5000
```

## API Endpoints

### Download Status
- `GET /api/download-status` - Get all video download statuses
- `GET /api/stats` - Get overall statistics

### Transcriptions
- `GET /api/transcriptions` - List all transcription files (each item includes `url` when the title exists in `VODs/videos.csv`, for the YouTube player).
- `GET /api/transcription/<filename>` - Get transcription content

### GraphRAG
- `POST /api/graphrag/query` - Execute Cypher query
  ```json
  {
    "query": "MATCH (n) RETURN n LIMIT 25"
  }
  ```
- `POST /api/graphrag/nl-query` - Natural language question → Cypher → graph context → answer (uses an LLM; see configuration below).

### Configuration (optional)

Environment variables for the **natural language query** LLM (saves OpenAI token cost when using Ollama):

| Variable | Default | Description |
|----------|---------|-------------|
| `NL_QUERY_LLM` | `openai` | `openai` = GPT-4o-mini (API); `ollama` = local model (no API cost). |
| `OLLAMA_NL_MODEL` | `llama3.2` | Ollama model name when `NL_QUERY_LLM=ollama` (e.g. `llama3.2`, `llama3.1`, `mistral`). |

Example (use local LLM for NL queries):
```bash
export NL_QUERY_LLM=ollama
export OLLAMA_NL_MODEL=llama3.2
python launch_web.py
```
Ensure Ollama is running and the model is pulled (`ollama pull llama3.2`). The API response includes `llm_backend` (`openai` or `ollama`).

## Future Enhancements

### GraphRAG Integration
The GraphRAG tab connects to Neo4j. The graph contains:
- **Document** → **Chunk** (with `text`, `nomic_embeddings`, `openai_embeddings`, optional `start_time`/`end_time`)
- **Chunk** → **Concept** (MENTIONS)
- **Concept** (with `nomic_embeddings`, `openai_embeddings`) and **CONCEPT_RELATION** between concepts

Vector indexes: `chunk_nomic_embeddings`, `chunk_openai_embeddings`, `concept_nomic_embeddings`, `concept_openai_embeddings`. Load data with `run_embeddings_to_neo4j.py` or `load_transcriptions_to_neo4j.py` (see NEO4J_SETUP.md).

### Features to Add
- Real-time updates via WebSocket
- Export transcriptions to various formats
- Advanced search and filtering
- Graph visualization for Neo4j results
- Batch operations for downloads
- Transcription editing capabilities

## Project Structure

```
LNG-GraphRAG/
├── web_app.py              # Flask web server
├── launch_web.py           # Launch script
├── templates/
│   └── index.html          # Main dashboard HTML
├── VODs/
│   └── videos.csv          # Download status CSV
└── transcriptions/         # Transcription files
```

## Troubleshooting

### Port Already in Use
If port 5000 is already in use, modify `web_app.py`:
```python
app.run(debug=True, host='0.0.0.0', port=5001)  # Change port
```

### CSV File Not Found
Make sure `VODs/videos.csv` exists and has the correct format:
```csv
title,url,status
Video Title,https://youtube.com/watch?v=...,completed
```

### Transcriptions Not Loading
- Check that transcription files exist in `transcriptions/` directory
- Verify file naming: `{title}_combined.txt`
- Check file permissions

## License

[Same as main project]

