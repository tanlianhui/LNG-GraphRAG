# Neo4j Backup and Restore

This document describes how to backup and restore your Neo4j database.

## Never re-run embeddings after Neo4j rebuild

To **never run the embedding process again** after you rebuild the Neo4j Docker container (or recreate the volume):

1. **One-time**: Run the embedding process with **nomic only** (default):
   ```bash
   python run_embeddings_to_neo4j.py --embedding nomic --clean
   ```
2. **Right after load**: Create a dump (includes all nodes and embeddings):
   ```bash
   python dump_neo4j.py
   ```
   Or run load and dump in one go:
   ```bash
   python run_embeddings_to_neo4j.py --embedding nomic --clean --dump-after
   ```
3. **When you rebuild Neo4j** (new container, new volume, or `docker compose up` after `down -v`):
   - **Do not** run `run_embeddings_to_neo4j.py` again.
   - **Do** restore from the dump:
     ```bash
     python restore_neo4j.py
     ```
   Restore brings back the full graph (including `nomic_embeddings`) so you never need to re-embed.

4. **Optional**: To keep data across simple container rebuilds without using dumps, avoid removing the Neo4j volume: use `docker compose down` (no `-v`). The `neo4j_data` volume persists. Only if you delete the volume or start from scratch do you need to run `restore_neo4j.py` instead of re-running embeddings.

## Overview

The Neo4j database can be dumped to a local folder (`./neo4j`) and restored when needed. This is useful for:
- Creating backups before major changes
- Migrating data between environments
- Restoring after a container restart or data loss

Dumps include all node and relationship data (e.g. Chunk/Concept nodes with `nomic_embeddings`, `openai_embeddings`, and vector indexes are stored in the graph data).

## Prerequisites

- Neo4j container must be running (`lng-neo4j`)
- Docker must be installed and running

## Dumping the Database

To create a backup of your Neo4j database:

```bash
python dump_neo4j.py
```

This will:
1. Check that the Neo4j container is running
2. Create a dump file in `./neo4j/` directory
3. Name the dump file with a timestamp: `neo4j_dump_YYYYMMDD_HHMMSS.dump`
4. Create a symlink `latest.dump` pointing to the most recent dump

**Example output:**
```
==================================================
🎙️  LNG GraphRAG - Neo4j Database Dump
==================================================

📁 Dump directory: /Users/riversoft/Documents/LNG-GraphRAG/neo4j

📦 Dumping Neo4j database 'neo4j' to ./neo4j/neo4j_dump_20250101_120000.dump...
✅ Database dumped successfully to: ./neo4j/neo4j_dump_20250101_120000.dump
✅ Created symlink: ./neo4j/latest.dump -> neo4j_dump_20250101_120000.dump

==================================================
✅ Dump completed successfully!
==================================================
```

## Restoring the Database

To restore a database from a dump:

```bash
python restore_neo4j.py
```

Or to restore a specific dump file:

```bash
python restore_neo4j.py --dump-file neo4j_dump_20250101_120000.dump
```

This will:
1. Check that the Neo4j container is running
2. Find the latest dump file (or use the specified one)
3. **WARNING**: Stop Neo4j, restore the database (overwriting existing data), and restart Neo4j
4. Wait for Neo4j to be ready

**⚠️ Important**: Restoring will **overwrite** the current database. Make sure you have a backup if needed!

**Example output:**
```
==================================================
🎙️  LNG GraphRAG - Neo4j Database Restore
==================================================

📦 Found latest dump: ./neo4j/neo4j_dump_20250101_120000.dump

⚠️  WARNING: This will overwrite the current database 'neo4j'!
   Are you sure you want to continue? (yes/no): yes

🛑 Stopping Neo4j service...
📤 Copying dump file to container...
🔄 Restoring database...
🚀 Starting Neo4j service...
✅ Database restored successfully!

==================================================
✅ Restore completed successfully!
==================================================
⏳ Waiting for Neo4j to be ready...
✅ Neo4j is ready!

🌐 Neo4j Browser: http://localhost:7474
```

## Automated Backup on Restart

To automatically restore the database when Neo4j container restarts, you can:

1. **Manual approach**: Run `python restore_neo4j.py` after starting the container
2. **Automated approach**: Modify `setup_neo4j.sh` to automatically restore if a dump exists

## Best Practices

1. **Regular Backups**: Run `dump_neo4j.py` regularly, especially before:
   - Loading new transcriptions
   - Making major changes to the graph structure
   - Updating Neo4j version

2. **Version Control**: Keep multiple dump files with timestamps for recovery options

3. **Storage**: The `./neo4j` folder is in `.gitignore` - dumps are not committed to git

4. **Disk Space**: Monitor the `./neo4j` folder size - old dumps can be deleted manually

## Troubleshooting

### Container not found
```
❌ Container 'lng-neo4j' not found.
   Please start Neo4j first with: ./setup_neo4j.sh
```
**Solution**: Start Neo4j container with `./setup_neo4j.sh`

### Container not running
```
❌ Container 'lng-neo4j' is not running.
   Please start it with: docker start lng-neo4j
```
**Solution**: Start the container with `docker start lng-neo4j`

### No dump files found
```
❌ No dump files found in ./neo4j
```
**Solution**: Run `python dump_neo4j.py` first to create a dump

### Restore fails
If restore fails, check:
- Container logs: `docker logs lng-neo4j`
- Disk space: Ensure you have enough space
- Permissions: Ensure Docker has permission to access the dump file

## File Structure

```
LNG-GraphRAG/
├── neo4j/                          # Dump directory (gitignored)
│   ├── neo4j_dump_20250101_120000.dump
│   ├── neo4j_dump_20250102_150000.dump
│   └── latest.dump -> neo4j_dump_20250102_150000.dump  # Symlink
├── dump_neo4j.py                   # Dump script
└── restore_neo4j.py                # Restore script
```

