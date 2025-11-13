#!/bin/bash

# Setup script for Neo4j Docker container

echo "=========================================="
echo "🎙️  LNG GraphRAG Neo4j Setup"
echo "=========================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "⚠️  docker-compose not found, trying 'docker compose'..."
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# Stop and remove existing container if it exists
echo "🧹 Cleaning up existing containers..."
$DOCKER_COMPOSE down 2>/dev/null || true

# Pull Neo4j image
echo "📥 Pulling Neo4j image..."
docker pull neo4j:5.15-community

# Start Neo4j
echo "🚀 Starting Neo4j container..."
$DOCKER_COMPOSE up -d

# Wait for Neo4j to be ready
echo "⏳ Waiting for Neo4j to be ready..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if docker exec lng-neo4j cypher-shell -u neo4j -p lng-graphrag-password "RETURN 1" > /dev/null 2>&1; then
        echo "✅ Neo4j is ready!"
        break
    fi
    attempt=$((attempt + 1))
    echo "   Attempt $attempt/$max_attempts..."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "❌ Neo4j failed to start. Check logs with: docker logs lng-neo4j"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ Neo4j is running!"
echo "=========================================="
echo "🌐 Neo4j Browser: http://localhost:7474"
echo "🔌 Bolt: bolt://localhost:7687"
echo "👤 Username: neo4j"
echo "🔑 Password: lng-graphrag-password"
echo ""
echo "📝 Next steps:"
echo "   1. Set your OPENAI_API_KEY: export OPENAI_API_KEY='your-key'"
echo "   2. Run: python load_transcriptions_to_neo4j.py"
echo ""

