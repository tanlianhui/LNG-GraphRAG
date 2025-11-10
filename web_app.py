from flask import Flask, render_template, jsonify, request
import csv
import os
from pathlib import Path
import json
from typing import List, Dict, Optional

app = Flask(__name__)

# Configuration
VODS_CSV = "./VODs/videos.csv"
TRANSCRIPTIONS_DIR = "./transcriptions"
VODS_DIR = "./VODs"

def get_download_status() -> List[Dict]:
    """Read download status from CSV file"""
    videos = []
    if not os.path.exists(VODS_CSV):
        return videos
    
    try:
        with open(VODS_CSV, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = row.get('title', '')
                url = row.get('url', '')
                status = row.get('status', 'pending')
                
                # Check if WAV file exists
                wav_file = os.path.join(VODS_DIR, f"{title}.wav")
                file_exists = os.path.exists(wav_file)
                
                # Check if transcription exists
                transcription_file = os.path.join(TRANSCRIPTIONS_DIR, f"{title}_combined.txt")
                transcription_exists = os.path.exists(transcription_file)
                
                videos.append({
                    'title': title,
                    'url': url,
                    'status': status,
                    'wav_exists': file_exists,
                    'transcription_exists': transcription_exists,
                    'wav_file': wav_file if file_exists else None,
                    'transcription_file': transcription_file if transcription_exists else None
                })
    except Exception as e:
        print(f"Error reading CSV: {e}")
    
    return videos

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

def get_transcription_content(filename: str) -> Optional[str]:
    """Read transcription file content"""
    file_path = os.path.join(TRANSCRIPTIONS_DIR, filename)
    if not os.path.exists(file_path):
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
    return jsonify({
        'success': True,
        'videos': videos,
        'total': len(videos),
        'completed': sum(1 for v in videos if v['status'] == 'completed'),
        'pending': sum(1 for v in videos if v['status'] == 'pending'),
        'failed': sum(1 for v in videos if v['status'] == 'failed'),
        'skipped': sum(1 for v in videos if v['status'] == 'skipped'),
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
    
    # TODO: Implement Neo4j connection and query execution
    # For now, return a placeholder response
    return jsonify({
        'success': True,
        'query': query,
        'message': 'GraphRAG Neo4j integration coming soon',
        'results': [],
        'note': 'This endpoint will connect to Neo4j and execute Cypher queries once GraphRAG is implemented'
    })

@app.route('/api/stats')
def api_stats():
    """API endpoint for overall statistics"""
    videos = get_download_status()
    transcriptions = get_transcription_files()
    
    return jsonify({
        'success': True,
        'stats': {
            'total_videos': len(videos),
            'completed_downloads': sum(1 for v in videos if v['status'] == 'completed'),
            'pending_downloads': sum(1 for v in videos if v['status'] == 'pending'),
            'failed_downloads': sum(1 for v in videos if v['status'] == 'failed'),
            'total_transcriptions': len(transcriptions),
            'videos_with_transcriptions': sum(1 for v in videos if v['transcription_exists']),
            'total_wav_files': sum(1 for v in videos if v['wav_exists'])
        }
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

