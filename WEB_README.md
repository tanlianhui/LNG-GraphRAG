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
- Browse all available transcriptions
- Collapsible sections for each transcription file
- Chunk-based display (organized by audio chunks)
- File metadata (size, filename)
- Lazy loading of transcription content

### 🕸️ GraphRAG Tab
- Neo4j Cypher query interface
- Execute queries against the knowledge graph
- Results display with JSON formatting
- Ready for future GraphRAG implementation

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
- `GET /api/transcriptions` - List all transcription files
- `GET /api/transcription/<filename>` - Get transcription content

### GraphRAG
- `POST /api/graphrag/query` - Execute Cypher query
  ```json
  {
    "query": "MATCH (n) RETURN n LIMIT 25"
  }
  ```

## Future Enhancements

### GraphRAG Integration
The GraphRAG tab is ready for Neo4j integration. To enable it:

1. Install and configure Neo4j
2. Update `web_app.py` to connect to Neo4j:
```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
```

3. Implement query execution in the `/api/graphrag/query` endpoint

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

