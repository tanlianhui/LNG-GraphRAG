# Neo4j Setup and Transcription Loading Guide

This guide will help you set up Neo4j in Docker and load transcriptions into the knowledge graph.

## Prerequisites

1. **Docker** installed and running
2. **OpenAI API Key** for embeddings
3. Python dependencies installed: `pip install -r requirements.txt`

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

### Load all transcriptions

```bash
python load_transcriptions_to_neo4j.py
```

This will:
- Create the `lng_transcriptions` database
- Process each transcription file in `./transcriptions/`
- Generate embeddings for chunks
- Extract concepts and relationships
- Build the knowledge graph

### Process specific files

You can modify `load_transcriptions_to_neo4j.py` to filter specific files.

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

### Database not found

If you get "Database not found" errors:
- The database is created automatically on first load
- Check database exists: `docker exec lng-neo4j cypher-shell -u neo4j -p lng-graphrag-password "SHOW DATABASES"`

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

