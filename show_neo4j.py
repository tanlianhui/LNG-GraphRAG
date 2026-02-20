#!/usr/bin/env python3
"""
Show Neo4j database content (node labels, relationship types, sample Chunk/Document nodes).
Uses .env for NEO4J_IP, NEO4J_USERNAME, NEO4J_PASSWORD. Run from project root.

Example:
  python show_neo4j.py

If the database is empty, load transcriptions first, e.g.:
  python load_single_to_neo4j.py "transcriptions/combined/【LNG】2026JAN 豬神降臨來疊字 魔法馬馬射下來_combined.txt"
  # or
  python load_transcriptions_to_neo4j.py
"""
import os
import subprocess
import sys
from pathlib import Path

# Run the actual Neo4j queries in a subprocess with cwd outside the project
# so that the project's ./neo4j (dump folder) does not shadow the neo4j driver.
ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
CODE = r"""
import os
from pathlib import Path
from dotenv import load_dotenv
env_path = os.environ.get("SHOW_NEO4J_ENV")
if env_path:
    load_dotenv(env_path)
import neo4j

uri = "bolt://" + os.environ.get("NEO4J_IP", "localhost") + ":7687"
user = os.environ.get("NEO4J_USERNAME", "neo4j")
password = os.environ.get("NEO4J_PASSWORD", "lng-graphrag-password")
driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))

def run(q, **kwargs):
    with driver.session(database="neo4j") as s:
        return list(s.run(q, **kwargs))

print("=== Neo4j database: neo4j ===")
print()
labels = run("CALL db.labels() YIELD label RETURN label ORDER BY label")
if not labels:
    print("No labels in database (empty graph).")
else:
    print("Labels and node counts:")
    for rec in labels:
        label = rec["label"]
        cnt = run("MATCH (n:`" + label + "`) RETURN count(n) AS c")[0]["c"]
        print("  %s: %s" % (label, cnt))
rels = run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType")
if rels:
    print()
    print("Relationship types and counts:")
    for rec in rels:
        rt = rec["relationshipType"]
        cnt = run("MATCH ()-[r:`" + rt + "`]->() RETURN count(r) AS c")[0]["c"]
        print("  %s: %s" % (rt, cnt))
chunks = run("MATCH (n:Chunk) RETURN n.document_name AS doc, n.id AS id LIMIT 10")
print()
if chunks:
    print("Sample Chunk nodes (document_name, id):")
    for r in chunks:
        print("  doc=%r, id=%s" % (r["doc"], r["id"]))
else:
    print("No Chunk nodes found.")
docs = run("MATCH (n:Document) RETURN n.name AS name LIMIT 10")
if docs:
    print("Sample Document nodes:")
    for r in docs:
        print("  name=%r" % (r["name"],))
else:
    print("No Document nodes found.")
driver.close()
print()
print("Done.")
"""


def main():
    if not ENV_FILE.exists():
        print("No .env found. Create one with NEO4J_IP, NEO4J_USERNAME, NEO4J_PASSWORD.", file=sys.stderr)
        sys.exit(1)
    python = sys.executable
    env = {**os.environ, "PYTHONPATH": str(ROOT), "SHOW_NEO4J_ENV": str(ENV_FILE)}
    script = CODE
    r = subprocess.run(
        [python, "-c", script],
        cwd="/tmp",
        env=env,
    )
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
