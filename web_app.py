from flask import Flask, render_template, jsonify, request
import csv
import os
from pathlib import Path
import json
import asyncio
from typing import List, Dict, Optional
import sys

app = Flask(__name__)

# Configuration
VODS_CSV = "./VODs/videos.csv"
TRANSCRIPTIONS_DIR = "./transcriptions"
EDIT_DIR = "./transcriptions/edit"
VODS_DIR = "./VODs"

def get_download_status() -> List[Dict]:
    """Read download status from CSV file and update based on transcription existence"""
    videos = []
    if not os.path.exists(VODS_CSV):
        return videos
    
    updated_rows = []
    needs_update = False
    
    try:
        with open(VODS_CSV, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            for row in reader:
                title = row.get('title', '')
                url = row.get('url', '')
                status = row.get('status', 'pending')
                
                # Check if transcription exists
                transcription_file = os.path.join(TRANSCRIPTIONS_DIR, f"{title}_combined.txt")
                transcription_exists = os.path.exists(transcription_file)
                
                # If transcription exists, mark as completed (regardless of WAV file)
                if transcription_exists and status != 'completed':
                    status = 'completed'
                    needs_update = True
                
                # Check if WAV file exists (for display purposes only)
                wav_file = os.path.join(VODS_DIR, f"{title}.wav")
                file_exists = os.path.exists(wav_file)
                
                videos.append({
                    'title': title,
                    'url': url,
                    'status': status,
                    'wav_exists': file_exists,
                    'transcription_exists': transcription_exists,
                    'wav_file': wav_file if file_exists else None,
                    'transcription_file': transcription_file if transcription_exists else None
                })
                
                # Store updated row for CSV update
                updated_row = row.copy()
                updated_row['status'] = status
                updated_rows.append(updated_row)
        
        # Update CSV if any statuses were changed
        if needs_update and updated_rows:
            update_csv_file(updated_rows, fieldnames)
            
    except Exception as e:
        print(f"Error reading CSV: {e}")
    
    return videos

def update_csv_file(rows: List[Dict], fieldnames: List[str]):
    """Update the CSV file with corrected statuses"""
    try:
        with open(VODS_CSV, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"✅ Updated CSV file with {len(rows)} entries")
    except Exception as e:
        print(f"⚠️  Error updating CSV file: {e}")

def get_transcription_files() -> List[Dict]:
    """Get list of all transcription files"""
    transcriptions = []
    if not os.path.exists(TRANSCRIPTIONS_DIR):
        return transcriptions
    
    try:
        for file in os.listdir(TRANSCRIPTIONS_DIR):
            if file.endswith('_combined.txt'):
                file_path = os.path.join(TRANSCRIPTIONS_DIR, file)
                title = file.replace('_combined.txt', '')
                file_size = os.path.getsize(file_path)
                
                transcriptions.append({
                    'filename': file,
                    'title': title,
                    'path': file_path,
                    'size': file_size,
                    'size_mb': round(file_size / (1024 * 1024), 2)
                })
        
        # Sort by filename (which includes date)
        transcriptions.sort(key=lambda x: x['filename'], reverse=True)
    except Exception as e:
        print(f"Error reading transcriptions directory: {e}")
    
    return transcriptions

def get_transcription_file_path(filename: str) -> Optional[str]:
    """Get the path to transcription file, checking edit file first if it exists"""
    # Check for edit file first
    edit_filename = filename.replace('_combined.txt', '_combined_edit.txt')
    edit_path = os.path.join(EDIT_DIR, edit_filename)
    if os.path.exists(edit_path):
        return edit_path
    
    # Fall back to original file
    original_path = os.path.join(TRANSCRIPTIONS_DIR, filename)
    if os.path.exists(original_path):
        return original_path
    
    return None

def get_transcription_content(filename: str) -> Optional[str]:
    """Read transcription file content, preferring edit file if it exists"""
    file_path = get_transcription_file_path(filename)
    if not file_path:
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading transcription file: {e}")
        return None

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/api/download-status')
def api_download_status():
    """API endpoint for download status"""
    videos = get_download_status()
    # Count completed as videos with transcriptions (transcription = completed)
    completed_count = sum(1 for v in videos if v['transcription_exists'] or v['status'] == 'completed')
    return jsonify({
        'success': True,
        'videos': videos,
        'total': len(videos),
        'completed': completed_count,
        'pending': sum(1 for v in videos if v['status'] == 'pending' and not v['transcription_exists']),
        'failed': sum(1 for v in videos if v['status'] == 'failed' and not v['transcription_exists']),
        'skipped': sum(1 for v in videos if v['status'] == 'skipped' and not v['transcription_exists']),
        'with_transcriptions': sum(1 for v in videos if v['transcription_exists'])
    })

@app.route('/api/transcriptions')
def api_transcriptions():
    """API endpoint for list of transcriptions"""
    transcriptions = get_transcription_files()
    return jsonify({
        'success': True,
        'transcriptions': transcriptions,
        'total': len(transcriptions)
    })

@app.route('/api/transcription/<filename>')
def api_transcription_content(filename):
    """API endpoint for transcription content"""
    # Security: ensure filename doesn't contain path traversal
    filename = os.path.basename(filename)
    content = get_transcription_content(filename)
    
    if content is None:
        return jsonify({
            'success': False,
            'error': 'Transcription file not found'
        }), 404
    
    return jsonify({
        'success': True,
        'filename': filename,
        'content': content
    })

@app.route('/api/graphrag/query', methods=['POST'])
def api_graphrag_query():
    """API endpoint for GraphRAG Neo4j queries"""
    data = request.get_json()
    query = data.get('query', '')
    
    if not query:
        return jsonify({
            'success': False,
            'error': 'No query provided'
        }), 400
    
    # Neo4j connection settings
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USERNAME = os.getenv('NEO4J_USERNAME', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'lng-graphrag-password')
    DB_NAME = os.getenv('NEO4J_DB_NAME', 'lng_transcriptions')
    
    try:
        import neo4j
        from time import time
        
        # Connect to Neo4j
        driver = neo4j.GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
            connection_timeout=30
        )
        
        # Detect Community Edition and use appropriate database
        # Use the same detection logic as own_graph_rag.py
        actual_db_name = DB_NAME
        is_community_edition = True  # Assume Community Edition by default
        
        # Test if CREATE DATABASE is supported (Enterprise Edition feature)
        test_db_name = f"_test_db_{int(time())}"
        try:
            with driver.session(database="system") as session:
                # Try to create a test database
                session.run(f"CREATE DATABASE {test_db_name}")
                # If successful, immediately drop it
                session.run(f"DROP DATABASE {test_db_name} IF EXISTS")
            # If we get here, it's Enterprise Edition
            is_community_edition = False
        except Exception:
            # Any error creating database means Community Edition
            is_community_edition = True
        
        # Use appropriate database name
        if is_community_edition:
            actual_db_name = "neo4j"  # Default database in Community Edition
        else:
            actual_db_name = DB_NAME  # Use requested database in Enterprise Edition
        
        # Execute query
        with driver.session(database=actual_db_name) as session:
            result = session.run(query)
            
            # Collect results - properly serialize Neo4j nodes and relationships
            records = []
            for record in result:
                # Convert record to dict
                record_dict = {}
                for key in record.keys():
                    value = record[key]
                    # Handle Neo4j Node objects
                    if hasattr(value, 'labels') and hasattr(value, 'properties'):
                        record_dict[key] = {
                            'identity': value.id,
                            'labels': list(value.labels),
                            'properties': dict(value)
                        }
                    # Handle Neo4j Relationship objects
                    elif hasattr(value, 'type') and hasattr(value, 'start_node') and hasattr(value, 'end_node'):
                        record_dict[key] = {
                            'identity': value.id,
                            'type': value.type,
                            'start': {
                                'identity': value.start_node.id,
                                'labels': list(value.start_node.labels),
                                'properties': dict(value.start_node)
                            },
                            'end': {
                                'identity': value.end_node.id,
                                'labels': list(value.end_node.labels),
                                'properties': dict(value.end_node)
                            },
                            'properties': dict(value)
                        }
                    # Handle lists (paths, arrays)
                    elif isinstance(value, list):
                        serialized_list = []
                        for item in value:
                            if hasattr(item, 'labels') and hasattr(item, 'properties'):
                                # Node in list
                                serialized_list.append({
                                    'identity': item.id,
                                    'labels': list(item.labels),
                                    'properties': dict(item)
                                })
                            elif hasattr(item, 'type') and hasattr(item, 'start_node'):
                                # Relationship in list
                                serialized_list.append({
                                    'identity': item.id,
                                    'type': item.type,
                                    'start': {
                                        'identity': item.start_node.id,
                                        'labels': list(item.start_node.labels),
                                        'properties': dict(item.start_node)
                                    },
                                    'end': {
                                        'identity': item.end_node.id,
                                        'labels': list(item.end_node.labels),
                                        'properties': dict(item.end_node)
                                    },
                                    'properties': dict(item)
                                })
                            else:
                                serialized_list.append(item)
                        record_dict[key] = serialized_list
                    # Handle other Neo4j types
                    elif hasattr(value, '__dict__'):
                        # Try to serialize as dict if possible
                        try:
                            record_dict[key] = dict(value)
                        except:
                            record_dict[key] = str(value)
                    else:
                        record_dict[key] = value
                records.append(record_dict)
            
            # Get summary
            summary = result.consume()
            
            return jsonify({
                'success': True,
                'query': query,
                'results': records,
                'summary': {
                    'result_available_after': summary.result_available_after,
                    'result_consumed_after': summary.result_consumed_after,
                    'counters': {
                        'nodes_created': summary.counters.nodes_created,
                        'nodes_deleted': summary.counters.nodes_deleted,
                        'relationships_created': summary.counters.relationships_created,
                        'relationships_deleted': summary.counters.relationships_deleted,
                    }
                }
            })
        
    except ImportError:
        return jsonify({
            'success': False,
            'error': 'Neo4j driver not installed. Install with: pip install neo4j'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Query execution failed: {str(e)}',
            'query': query
        }), 500
    finally:
        if 'driver' in locals():
            driver.close()

@app.route('/api/stats')
def api_stats():
    """API endpoint for overall statistics"""
    videos = get_download_status()
    transcriptions = get_transcription_files()
    
    # Completed = videos with transcriptions (transcription = completed)
    completed_count = sum(1 for v in videos if v['transcription_exists'] or v['status'] == 'completed')
    
    return jsonify({
        'success': True,
        'stats': {
            'total_videos': len(videos),
            'completed_downloads': completed_count,
            'pending_downloads': sum(1 for v in videos if v['status'] == 'pending' and not v['transcription_exists']),
            'failed_downloads': sum(1 for v in videos if v['status'] == 'failed' and not v['transcription_exists']),
            'total_transcriptions': len(transcriptions),
            'videos_with_transcriptions': sum(1 for v in videos if v['transcription_exists']),
            'total_wav_files': sum(1 for v in videos if v['wav_exists'])
        }
    })

@app.route('/api/transcription/update', methods=['POST'])
def api_update_transcription():
    """API endpoint for updating a transcription chunk"""
    data = request.get_json()
    filename = data.get('filename', '')
    chunk_id = data.get('chunk_id')
    new_text = data.get('new_text', '')
    
    if not filename or chunk_id is None or not new_text:
        return jsonify({
            'success': False,
            'error': 'Missing required fields: filename, chunk_id, new_text'
        }), 400
    
    # Security: ensure filename doesn't contain path traversal
    filename = os.path.basename(filename)
    if not filename.endswith('_combined.txt'):
        return jsonify({
            'success': False,
            'error': 'Invalid filename format'
        }), 400
    
    transcription_path = os.path.join(TRANSCRIPTIONS_DIR, filename)
    if not os.path.exists(transcription_path):
        return jsonify({
            'success': False,
            'error': 'Transcription file not found'
        }), 404
    
    try:
        # Import graphrag functions
        graphrag_path = os.path.join(os.path.dirname(__file__), 'graphrag')
        if graphrag_path not in sys.path:
            sys.path.insert(0, graphrag_path)
        
        from own_graph_rag import write_edit_to_file, update_chunk_in_neo4j
        import os as os_module
        from dotenv import load_dotenv
        
        load_dotenv()
        
        # Write edit to "_edit" file in edit directory (do not modify original transcription file)
        # Create edit directory if it doesn't exist
        os.makedirs(EDIT_DIR, exist_ok=True)
        edit_filename = filename.replace('_combined.txt', '_combined_edit.txt')
        edit_file_path = os.path.join(EDIT_DIR, edit_filename)
        file_updated = asyncio.run(write_edit_to_file(
            edit_file_path,
            filename,
            chunk_id,
            new_text
        ))
        
        if not file_updated:
            return jsonify({
                'success': False,
                'error': 'Failed to write edit to file'
            }), 500
        
        # Update Neo4j (document name is the filename)
        document_name = filename
        db_name = os_module.getenv('NEO4J_DB_NAME', 'lng_transcriptions')
        
        neo4j_result = asyncio.run(update_chunk_in_neo4j(
            document_name=document_name,
            chunk_id=chunk_id,
            new_text=new_text,
            db_name=db_name
        ))
        
        if not neo4j_result.get('success'):
            return jsonify({
                'success': False,
                'error': f"Failed to update Neo4j: {neo4j_result.get('error', 'Unknown error')}",
                'file_updated': True  # File was updated even if Neo4j failed
            }), 500
        
        return jsonify({
            'success': True,
            'message': 'Transcription chunk updated successfully in Neo4j and edit file',
            'document_name': document_name,
            'chunk_id': chunk_id,
            'edit_file': os.path.basename(edit_file_path)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Update failed: {str(e)}'
        }), 500

@app.route('/api/transcription/chunks/<filename>')
def api_transcription_chunks(filename):
    """API endpoint to get parsed chunks with metadata"""
    # Security: ensure filename doesn't contain path traversal
    filename = os.path.basename(filename)
    if not filename.endswith('_combined.txt'):
        return jsonify({
            'success': False,
            'error': 'Invalid filename format'
        }), 400
    
    transcription_path = os.path.join(TRANSCRIPTIONS_DIR, filename)
    if not os.path.exists(transcription_path):
        return jsonify({
            'success': False,
            'error': 'Transcription file not found'
        }), 404
    
    try:
        # Import graphrag function
        graphrag_path = os.path.join(os.path.dirname(__file__), 'graphrag')
        if graphrag_path not in sys.path:
            sys.path.insert(0, graphrag_path)
        
        from own_graph_rag import parse_transcription_chunks, get_transcription_file_path as get_file_path
        
        # Check for edit file first, then fall back to original
        actual_path = get_file_path(filename) or transcription_path
        chunks = parse_transcription_chunks(actual_path)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'chunks': chunks,
            'total_chunks': len(chunks)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to parse chunks: {str(e)}'
        }), 500

@app.route('/api/transcription/delete', methods=['POST'])
def api_delete_transcription():
    """API endpoint for deleting a transcription chunk"""
    data = request.get_json()
    filename = data.get('filename', '')
    chunk_id = data.get('chunk_id')
    
    if not filename or chunk_id is None:
        return jsonify({
            'success': False,
            'error': 'Missing required fields: filename, chunk_id'
        }), 400
    
    # Security: ensure filename doesn't contain path traversal
    filename = os.path.basename(filename)
    if not filename.endswith('_combined.txt'):
        return jsonify({
            'success': False,
            'error': 'Invalid filename format'
        }), 400
    
    transcription_path = os.path.join(TRANSCRIPTIONS_DIR, filename)
    if not os.path.exists(transcription_path):
        return jsonify({
            'success': False,
            'error': 'Transcription file not found'
        }), 404
    
    try:
        # Import graphrag functions
        graphrag_path = os.path.join(os.path.dirname(__file__), 'graphrag')
        if graphrag_path not in sys.path:
            sys.path.insert(0, graphrag_path)
        
        from own_graph_rag import delete_chunk_in_neo4j
        import os as os_module
        from dotenv import load_dotenv
        
        load_dotenv()
        
        # Delete from Neo4j only (do not modify transcription files)
        # Document name is the filename
        document_name = filename
        db_name = os_module.getenv('NEO4J_DB_NAME', 'lng_transcriptions')
        
        neo4j_result = asyncio.run(delete_chunk_in_neo4j(
            document_name=document_name,
            chunk_id=chunk_id,
            db_name=db_name
        ))
        
        if not neo4j_result.get('success'):
            return jsonify({
                'success': False,
                'error': f"Failed to delete from Neo4j: {neo4j_result.get('error', 'Unknown error')}",
                'file_deleted': True  # File was deleted even if Neo4j failed
            }), 500
        
        return jsonify({
            'success': True,
            'message': 'Chunk deleted successfully from Neo4j (transcription file unchanged)',
            'document_name': document_name,
            'chunk_id': chunk_id
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Delete failed: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

