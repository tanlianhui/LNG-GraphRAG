from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import csv
import os
from pathlib import Path
import json
import asyncio
from typing import List, Dict, Optional
import sys
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

# Load .env before any code that reads MYSQL_* or other env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
# Secret key optional for local dev; set FLASK_SECRET_KEY in .env only for production
app.secret_key = os.getenv("FLASK_SECRET_KEY", "lng-graphrag-dev-secret-change-in-production")

# Flask-Login (optional: only if auth DB is configured)
try:
    from flask_login import LoginManager, login_user, logout_user, login_required, current_user
    from auth_db import (
        is_configured as auth_configured,
        init_tables as auth_init_tables,
        get_connection as auth_get_connection,
        create_user as auth_create_user,
        get_user_by_id as auth_get_user_by_id,
        get_user_by_username,
        get_user_by_email,
        get_user_for_flask,
        create_reset_token as auth_create_reset_token,
        get_user_by_reset_token as auth_get_user_by_reset_token,
        delete_reset_token as auth_delete_reset_token,
        update_user_password as auth_update_user_password,
        record_edit as auth_record_edit,
        record_query as auth_record_query,
        get_edit_history as auth_get_edit_history,
        get_query_history as auth_get_query_history,
        get_admin_2fa as auth_get_admin_2fa,
        set_admin_2fa_secret as auth_set_admin_2fa_secret,
        set_admin_2fa_enabled as auth_set_admin_2fa_enabled,
    )
    login_manager = LoginManager(app)
    login_manager.login_view = "login"
    login_manager.login_message = "Please log in to access this page."

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Login required"}), 401
        return redirect(url_for("login"))

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return get_user_for_flask(int(user_id))
        except (ValueError, TypeError):
            return None

    _auth_tables_inited = False

    def init_auth_tables_once():
        global _auth_tables_inited
        if _auth_tables_inited or not auth_configured():
            return
        try:
            with auth_get_connection() as conn:
                auth_init_tables(conn)
            _auth_tables_inited = True
        except Exception as e:
            print(f"Auth DB init warning: {e}")
except ImportError:
    login_manager = None
    login_required = lambda f: f  # no-op if Flask-Login not installed
    current_user = None
    auth_configured = lambda: False
    init_auth_tables_once = lambda: None
    auth_record_edit = lambda *a, **k: None
    auth_record_query = lambda *a, **k: None
    auth_get_edit_history = lambda uid, limit=100: []
    auth_get_query_history = lambda uid, limit=100: []
    auth_get_admin_2fa = lambda uid: {"user_id": uid, "otp_secret": None, "otp_enabled": False}
    auth_set_admin_2fa_secret = lambda uid, secret: False
    auth_set_admin_2fa_enabled = lambda uid, enabled: False

# Optional: pyotp for app-level admin 2FA fallback
try:
    import pyotp
except ImportError:
    pyotp = None

# Configuration
VODS_CSV = "./VODs/videos.csv"
TRANSCRIPTIONS_DIR = "./transcriptions"
EDIT_DIR = "./transcriptions/edit"  # full edited transcription files
EDIT_HISTORY_DIR = "./transcriptions/edit_history"  # per-user, per-chunk edit history (not full files)
VODS_DIR = "./VODs"


def _parse_csv_env(name: str) -> set:
    raw = os.getenv(name, "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


ADMIN_EMAILS = _parse_csv_env("ADMIN_EMAILS")
ADMIN_USERNAMES = _parse_csv_env("ADMIN_USERNAMES")


def is_admin_user(user_obj) -> bool:
    """Admin identity comes from env allowlist for easy local control."""
    if not user_obj:
        return False
    username = (getattr(user_obj, "username", "") or "").strip().lower()
    email = (getattr(user_obj, "email", "") or "").strip().lower()
    if not ADMIN_EMAILS and not ADMIN_USERNAMES:
        return False
    return (email in ADMIN_EMAILS) or (username in ADMIN_USERNAMES)


def admin_required(fn):
    """Require logged-in admin user."""
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not getattr(current_user, "is_authenticated", False):
            return jsonify({"success": False, "error": "Login required"}), 401
        if not is_admin_user(current_user):
            return jsonify({"success": False, "error": "Admin required. Set ADMIN_EMAILS/ADMIN_USERNAMES in .env."}), 403
        return fn(*args, **kwargs)
    return wrapper

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

def get_title_to_url_map() -> Dict[str, str]:
    """Build title -> YouTube URL from VODs/videos.csv (for YouTube player in Transcriptions tab)."""
    out = {}
    if not os.path.exists(VODS_CSV):
        return out
    try:
        with open(VODS_CSV, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                title, url = row.get('title', '').strip(), row.get('url', '').strip()
                if title and url:
                    out[title] = url
    except Exception as e:
        print(f"Error reading videos.csv for URL map: {e}")
    return out


def get_transcription_files() -> List[Dict]:
    """Get list of all transcription files (includes url when found in VODs/videos.csv)."""
    transcriptions = []
    if not os.path.exists(TRANSCRIPTIONS_DIR):
        return transcriptions
    title_to_url = get_title_to_url_map()
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
                    'size_mb': round(file_size / (1024 * 1024), 2),
                    'url': title_to_url.get(title, ''),
                })
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

@app.before_request
def _init_auth_db():
    init_auth_tables_once()


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/login')
def login():
    """Login page"""
    return render_template('login.html')


@app.route('/register')
def register():
    """Register page"""
    return render_template('register.html')


@app.route('/api/auth/register', methods=['POST'])
def api_auth_register():
    """Register a new user. Body: username, email, password."""
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    if not username or not email or not password:
        return jsonify({'success': False, 'error': 'Username, email, and password are required'}), 400
    if len(username) < 2:
        return jsonify({'success': False, 'error': 'Username must be at least 2 characters'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
    if not auth_configured():
        return jsonify({
            'success': False,
            'error': 'Auth not configured. Run: pip install flask-login pymysql. Set MYSQL_* in .env and start MySQL (e.g. docker-compose up -d mysql). See AUTH_SETUP.md.'
        }), 503
    password_hash = generate_password_hash(password, method="pbkdf2:sha256")
    user_id = auth_create_user(username, email, password_hash)
    if user_id is None:
        return jsonify({'success': False, 'error': 'Username or email already taken'}), 409
    from flask_login import login_user
    user = get_user_for_flask(user_id)
    if user:
        login_user(user, remember=True)
    return jsonify({'success': True, 'user_id': user_id, 'username': username})


@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    """Login. Body: username or email, password."""
    data = request.get_json() or {}
    login_id = (data.get('username') or data.get('email') or '').strip()
    password = data.get('password') or ''
    otp = (data.get('otp') or '').strip().replace(" ", "")
    if not login_id or not password:
        return jsonify({'success': False, 'error': 'Username/email and password required'}), 400
    if not auth_configured():
        return jsonify({
            'success': False,
            'error': 'Auth not configured. Run: pip install flask-login pymysql. Set MYSQL_* in .env and start MySQL (e.g. docker-compose up -d mysql). See AUTH_SETUP.md.'
        }), 503
    user_row = get_user_by_username(login_id) if '@' not in login_id else get_user_by_email(login_id)
    if not user_row or not check_password_hash(user_row['password_hash'], password):
        return jsonify({'success': False, 'error': 'Invalid username/email or password'}), 401
    user_email = (user_row.get("email") or "").strip().lower()
    user_name = (user_row.get("username") or "").strip().lower()
    is_admin_identity = (user_email in ADMIN_EMAILS) or (user_name in ADMIN_USERNAMES)
    if is_admin_identity:
        twofa = auth_get_admin_2fa(user_row['id'])
        if twofa.get("otp_enabled"):
            if pyotp is None:
                return jsonify({'success': False, 'error': 'pyotp is required for admin 2FA. Install dependencies and retry.'}), 503
            if not otp:
                return jsonify({'success': False, 'error': 'OTP code required for admin account', 'requires_otp': True}), 401
            secret = twofa.get("otp_secret") or ""
            if not secret or not pyotp.TOTP(secret).verify(otp, valid_window=1):
                return jsonify({'success': False, 'error': 'Invalid OTP code', 'requires_otp': True}), 401
    from flask_login import login_user
    from auth_db import get_user_for_flask
    user = get_user_for_flask(user_row['id'])
    if user:
        login_user(user, remember=True)
    return jsonify({'success': True, 'username': user_row['username']})


@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    """Logout current user."""
    if auth_configured():
        try:
            logout_user()
        except Exception:
            pass
    return jsonify({'success': True})


@app.route('/forgot-password')
def forgot_password_page():
    """Forgot password form page."""
    return render_template('forgot_password.html')


@app.route('/reset-password')
def reset_password_page():
    """Reset password form page (requires ?token=...)."""
    token = request.args.get('token', '')
    return render_template('reset_password.html', token=token)


@app.route('/api/auth/forgot-password', methods=['POST'])
def api_auth_forgot_password():
    """Request password reset. Body: email. Creates token and returns reset link (or sends email if configured)."""
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400
    if not auth_configured():
        return jsonify({
            'success': False,
            'error': 'Auth not configured. See AUTH_SETUP.md.'
        }), 503
    user_row = get_user_by_email(email)
    # Always return same message to avoid leaking whether email exists
    if not user_row:
        return jsonify({
            'success': True,
            'message': 'If an account exists for that email, a reset link has been sent.',
            'reset_link': None
        })
    import secrets
    from datetime import datetime, timedelta
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)
    try:
        auth_create_reset_token(token, user_row['id'], expires_at)
    except Exception as e:
        return jsonify({'success': False, 'error': 'Could not create reset token'}), 500
    reset_link = request.url_root.rstrip('/') + '/reset-password?token=' + token
    # TODO: if SMTP configured, send email with reset_link; else return link for dev
    return jsonify({
        'success': True,
        'message': 'If an account exists for that email, a reset link has been created.',
        'reset_link': reset_link
    })


@app.route('/api/auth/reset-password', methods=['POST'])
def api_auth_reset_password():
    """Reset password with token. Body: token, new_password."""
    data = request.get_json() or {}
    token = (data.get('token') or '').strip()
    new_password = data.get('new_password') or ''
    if not token:
        return jsonify({'success': False, 'error': 'Reset token is required'}), 400
    if len(new_password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
    if not auth_configured():
        return jsonify({'success': False, 'error': 'Auth not configured.'}), 503
    user_row = auth_get_user_by_reset_token(token)
    if not user_row:
        return jsonify({'success': False, 'error': 'Invalid or expired reset link. Request a new one.'}), 400
    password_hash = generate_password_hash(new_password, method="pbkdf2:sha256")
    if not auth_update_user_password(user_row['id'], password_hash):
        return jsonify({'success': False, 'error': 'Failed to update password'}), 500
    auth_delete_reset_token(token)
    return jsonify({'success': True, 'message': 'Password updated. You can log in now.'})


@app.route('/api/auth/me')
def api_auth_me():
    """Return current user if logged in."""
    if not auth_configured():
        return jsonify({'success': True, 'user': None})
    if getattr(current_user, 'is_authenticated', False):
        admin_status = auth_get_admin_2fa(current_user.id) if is_admin_user(current_user) else {"otp_enabled": False}
        return jsonify({
            'success': True,
            'user': {
                'id': current_user.id,
                'username': current_user.username,
                'email': current_user.email,
                'is_admin': is_admin_user(current_user),
                'admin_2fa_enabled': bool(admin_status.get("otp_enabled")),
            }
        })
    return jsonify({'success': True, 'user': None})


@app.route('/admin/2fa')
@login_required
def admin_2fa_page():
    """Simple admin page for OTP setup/enable/disable."""
    if not is_admin_user(current_user):
        return redirect(url_for("index"))
    return render_template("admin_2fa.html")


@app.route('/api/admin/2fa/status')
@admin_required
def api_admin_2fa_status():
    status = auth_get_admin_2fa(current_user.id)
    return jsonify({
        "success": True,
        "is_admin": True,
        "otp_enabled": bool(status.get("otp_enabled")),
        "has_secret": bool(status.get("otp_secret")),
        "pyotp_available": pyotp is not None,
    })


@app.route('/api/admin/2fa/setup', methods=['POST'])
@admin_required
def api_admin_2fa_setup():
    if pyotp is None:
        return jsonify({"success": False, "error": "pyotp is not installed. Install requirements first."}), 503
    secret = pyotp.random_base32()
    if not auth_set_admin_2fa_secret(current_user.id, secret):
        return jsonify({"success": False, "error": "Failed to store OTP secret"}), 500
    issuer = os.getenv("OTP_ISSUER", "LNG GraphRAG")
    account = (getattr(current_user, "email", "") or getattr(current_user, "username", "") or f"user-{current_user.id}")
    otp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=account, issuer_name=issuer)
    return jsonify({
        "success": True,
        "secret": secret,
        "otpauth_uri": otp_uri,
        "message": "Scan the URI in your authenticator app, then call /api/admin/2fa/enable with current otp code."
    })


@app.route('/api/admin/2fa/enable', methods=['POST'])
@admin_required
def api_admin_2fa_enable():
    if pyotp is None:
        return jsonify({"success": False, "error": "pyotp is not installed. Install requirements first."}), 503
    data = request.get_json() or {}
    otp = (data.get("otp") or "").strip().replace(" ", "")
    if not otp:
        return jsonify({"success": False, "error": "OTP code is required"}), 400
    status = auth_get_admin_2fa(current_user.id)
    secret = status.get("otp_secret") or ""
    if not secret:
        return jsonify({"success": False, "error": "2FA setup not initialized. Run setup first."}), 400
    if not pyotp.TOTP(secret).verify(otp, valid_window=1):
        return jsonify({"success": False, "error": "Invalid OTP code"}), 401
    if not auth_set_admin_2fa_enabled(current_user.id, True):
        return jsonify({"success": False, "error": "Failed to enable 2FA"}), 500
    return jsonify({"success": True, "message": "Admin 2FA enabled"})


@app.route('/api/admin/2fa/disable', methods=['POST'])
@admin_required
def api_admin_2fa_disable():
    if pyotp is None:
        return jsonify({"success": False, "error": "pyotp is not installed. Install requirements first."}), 503
    data = request.get_json() or {}
    otp = (data.get("otp") or "").strip().replace(" ", "")
    status = auth_get_admin_2fa(current_user.id)
    secret = status.get("otp_secret") or ""
    if not secret or not status.get("otp_enabled"):
        return jsonify({"success": False, "error": "Admin 2FA is not enabled"}), 400
    if not otp or not pyotp.TOTP(secret).verify(otp, valid_window=1):
        return jsonify({"success": False, "error": "Valid OTP code is required to disable"}), 401
    if not auth_set_admin_2fa_enabled(current_user.id, False):
        return jsonify({"success": False, "error": "Failed to disable 2FA"}), 500
    return jsonify({"success": True, "message": "Admin 2FA disabled"})


@app.route('/api/history/edits')
@login_required
def api_history_edits():
    """Return edit history for current user (requires login)."""
    if not auth_configured():
        return jsonify({'success': False, 'error': 'Auth not configured'}), 503
    if not getattr(current_user, 'is_authenticated', False):
        return jsonify({'success': False, 'error': 'Login required'}), 401
    limit = min(int(request.args.get('limit', 100)), 500)
    rows = auth_get_edit_history(current_user.id, limit=limit)
    return jsonify({'success': True, 'edits': rows})


@app.route('/api/history/queries')
@login_required
def api_history_queries():
    """Return query history for current user (requires login)."""
    if not auth_configured():
        return jsonify({'success': False, 'error': 'Auth not configured'}), 503
    if not getattr(current_user, 'is_authenticated', False):
        return jsonify({'success': False, 'error': 'Login required'}), 401
    limit = min(int(request.args.get('limit', 100)), 500)
    rows = auth_get_query_history(current_user.id, limit=limit)
    return jsonify({'success': True, 'queries': rows})


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

@app.route('/api/graphrag/nl-query', methods=['POST'])
def api_graphrag_nl_query():
    """API endpoint for natural language queries - converts to Cypher using LLM"""
    data = request.get_json()
    nl_query = data.get('query', '')
    
    if not nl_query:
        return jsonify({
            'success': False,
            'error': 'No query provided'
        }), 400
    
    try:
        from dotenv import load_dotenv
        import os as os_module
        
        load_dotenv()
        
        # LLM for NL → Cypher and answer: openai (API, costs tokens) or ollama (local, no API cost)
        nl_llm_backend = os.getenv("NL_QUERY_LLM", "openai").strip().lower()
        ollama_model = os.getenv("OLLAMA_NL_MODEL", "llama3.2").strip()
        openai_model = os.getenv("OPENAI_NL_MODEL", "gpt-4o-mini").strip()
        
        if nl_llm_backend == "ollama":
            from langchain_ollama import ChatOllama
            llm = ChatOllama(model=ollama_model, temperature=0)
        else:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        
        # Get database schema information
        NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        NEO4J_USERNAME = os.getenv('NEO4J_USERNAME', 'neo4j')
        NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'lng-graphrag-password')
        DB_NAME = os.getenv('NEO4J_DB_NAME', 'lng_transcriptions')
        
        import neo4j
        from time import time
        
        # Connect to Neo4j to get schema
        driver = neo4j.GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
            connection_timeout=30
        )
        
        # Detect Community Edition
        actual_db_name = DB_NAME
        is_community_edition = True
        test_db_name = f"_test_db_{int(time())}"
        try:
            with driver.session(database="system") as session:
                session.run(f"CREATE DATABASE {test_db_name}")
                session.run(f"DROP DATABASE {test_db_name} IF EXISTS")
            is_community_edition = False
        except Exception:
            is_community_edition = True
        
        if is_community_edition:
            actual_db_name = "neo4j"
        else:
            actual_db_name = DB_NAME
        
        # Get schema information
        schema_info = ""
        try:
            with driver.session(database=actual_db_name) as session:
                # Get node labels
                result = session.run("CALL db.labels()")
                labels = [record["label"] for record in result]
                
                # Get relationship types
                result = session.run("CALL db.relationshipTypes()")
                rel_types = [record["relationshipType"] for record in result]
                
                # Get sample properties for each label
                label_props = {}
                for label in labels[:10]:  # Limit to first 10 labels
                    try:
                        result = session.run(f"MATCH (n:{label}) RETURN keys(n) as keys LIMIT 1")
                        for record in result:
                            label_props[label] = record["keys"]
                            break
                    except:
                        pass
                
                schema_info = f"""
Neo4j Database Schema:
- Node Labels: {', '.join(labels)}
- Relationship Types: {', '.join(rel_types)}
- Sample Properties:
"""
                for label, props in label_props.items():
                    schema_info += f"  - {label}: {', '.join(props) if props else 'N/A'}\n"
        except Exception as e:
            schema_info = f"Schema info unavailable: {str(e)}"
        
        driver.close()
        
        # Create prompt for LLM to convert natural language to Cypher
        cypher_prompt = f"""You are a Neo4j Cypher query expert. Convert the user's natural language question into a valid Cypher query.

Database Schema:
{schema_info}

CRITICAL GUIDELINES - Prioritize Text Content:
1. Always return ONLY the Cypher query, no explanations or markdown
2. Use proper Cypher syntax with MATCH, WHERE, RETURN clauses
3. **MOST IMPORTANT**: Always RETURN nodes that have a 'text' property - this contains the actual content
   - For Chunk nodes: RETURN n.text, n (to get both text and full node)
   - For Concept nodes: RETURN n.name, n (concepts may not have text, use name)
   - Always prioritize nodes with text content over metadata-only nodes
4. Use LIMIT to restrict results (default: 25-50 nodes for good context)
5. Common patterns for text-rich queries:
   - Finding chunks with text: MATCH (n:Chunk) WHERE n.text CONTAINS 'keyword' RETURN n.text, n LIMIT 25
   - Finding related content: MATCH (c:Chunk)-[r]->(concept:Concept) RETURN c.text, c, r, concept LIMIT 30
   - Finding by document: MATCH (d:Document)<-[:BELONGS_TO]-(c:Chunk) RETURN c.text, c LIMIT 25
6. For text search, use CONTAINS or STARTS WITH on the 'text' property
7. When returning relationships, also return the connected nodes' text properties
8. **Always include n.text in RETURN when querying Chunk nodes** - this is the most valuable content

User Question: {nl_query}

Cypher Query:"""
        
        # Generate Cypher query using LLM
        response = llm.invoke([{"role": "user", "content": cypher_prompt}])
        cypher_query = response.content.strip()
        
        # Clean up the query (remove markdown code blocks if present)
        if cypher_query.startswith("```"):
            lines = cypher_query.split("\n")
            cypher_query = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        cypher_query = cypher_query.strip()
        
        # Execute the generated Cypher query to get context
        query_results = execute_cypher_query_for_context(cypher_query, actual_db_name)
        
        if not query_results.get('success'):
            return jsonify({
                'success': False,
                'error': f'Query execution failed: {query_results.get("error", "Unknown error")}',
                'query': nl_query
            }), 500
        
        # Use LLM to answer the question based on the graph context
        context_data = query_results.get('results', [])
        
        # Format context for LLM
        context_text = format_graph_context(context_data)
        
        # Generate answer using LLM with graph context
        answer_prompt = f"""You are a helpful assistant that answers questions based on a knowledge graph database containing transcription chunks and concepts.

User Question: {nl_query}

Graph Context (from Neo4j query results - text content prioritized):
{context_text}

IMPORTANT INSTRUCTIONS:
1. **Prioritize the text content** from nodes - this is the actual transcribed content and is the most valuable information
2. Use the text fields to answer the question directly - they contain the real content from the transcriptions
3. Supplement with metadata (document names, chunk IDs, timecodes, etc.) when relevant to provide context
4. If multiple text chunks are relevant, synthesize them into a coherent answer
5. Be specific and cite relevant details from the text content when possible
6. If the graph doesn't contain relevant information in the text fields, say so clearly
7. Format your answer in a natural, conversational way

Answer:"""
        
        answer_response = llm.invoke([{"role": "user", "content": answer_prompt}])
        answer = answer_response.content.strip()
        
        if auth_configured() and getattr(current_user, 'is_authenticated', False):
            auth_record_query(current_user.id, 'nl', nl_query, result_count=len(context_data))
        
        return jsonify({
            'success': True,
            'query': nl_query,
            'cypher_query': cypher_query,
            'answer': answer,
            'results_count': len(context_data),
            'llm_backend': nl_llm_backend,
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Natural language query failed: {str(e)}',
            'query': nl_query
        }), 500


def execute_cypher_query_for_context(query: str, db_name: str):
    """Helper function to execute a Cypher query and return results as dict (not JSON response)"""
    import neo4j
    
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USERNAME = os.getenv('NEO4J_USERNAME', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'lng-graphrag-password')
    
    driver = None
    try:
        driver = neo4j.GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
            connection_timeout=30
        )
        
        with driver.session(database=db_name) as session:
            result = session.run(query)
            
            # Collect results - extract text and meaningful information
            records = []
            for record in result:
                record_dict = {}
                for key in record.keys():
                    value = record[key]
                    # Handle Neo4j Node objects - extract meaningful properties
                    if hasattr(value, 'labels') and hasattr(value, 'properties'):
                        props = dict(value)
                        record_dict[key] = {
                            'type': list(value.labels)[0] if value.labels else 'Node',
                            'properties': props
                        }
                    # Handle Neo4j Relationship objects
                    elif hasattr(value, 'type') and hasattr(value, 'start_node') and hasattr(value, 'end_node'):
                        record_dict[key] = {
                            'type': value.type,
                            'start': dict(value.start_node),
                            'end': dict(value.end_node),
                            'properties': dict(value)
                        }
                    # Handle lists
                    elif isinstance(value, list):
                        serialized_list = []
                        for item in value:
                            if hasattr(item, 'labels') and hasattr(item, 'properties'):
                                serialized_list.append({
                                    'type': list(item.labels)[0] if item.labels else 'Node',
                                    'properties': dict(item)
                                })
                            elif hasattr(item, 'type'):
                                serialized_list.append({
                                    'type': item.type,
                                    'properties': dict(item)
                                })
                            else:
                                serialized_list.append(item)
                        record_dict[key] = serialized_list
                    # Handle plain objects
                    elif isinstance(value, dict):
                        record_dict[key] = value
                    elif hasattr(value, '__dict__'):
                        try:
                            record_dict[key] = dict(value)
                        except:
                            record_dict[key] = str(value)
                    else:
                        record_dict[key] = value
                records.append(record_dict)
            
            return {
                'success': True,
                'results': records
            }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        if driver:
            driver.close()


def format_graph_context(results: list) -> str:
    """Format graph query results into readable text for LLM context, prioritizing text fields"""
    if not results:
        return "No data found in the graph."
    
    context_parts = []
    for i, record in enumerate(results[:50], 1):  # Limit to 50 records
        record_text = []
        text_contents = []  # Collect all text fields first
        metadata_parts = []  # Collect other metadata
        
        for key, value in record.items():
            if isinstance(value, dict):
                if 'properties' in value:
                    props = value['properties']
                    node_type = value.get('type', 'Node')
                    
                    # PRIORITY 1: Extract text field (most important content)
                    text_content = props.get('text', '')
                    if text_content:
                        # Get full text or meaningful chunk
                        text_contents.append(f"[{node_type}] {text_content[:500]}")  # Increased to 500 chars for more context
                    
                    # PRIORITY 2: Extract other meaningful fields as metadata
                    metadata = {}
                    # Important metadata fields to include
                    if props.get('name'):
                        metadata['name'] = props['name']
                    if props.get('document_name'):
                        metadata['document'] = props['document_name']
                    if props.get('chunk_id') is not None:
                        metadata['chunk_id'] = props['chunk_id']
                    if props.get('start_time') is not None:
                        metadata['start_time'] = props['start_time']
                    if props.get('end_time') is not None:
                        metadata['end_time'] = props['end_time']
                    if props.get('url'):
                        metadata['url'] = props['url']
                    
                    # Add metadata if available
                    if metadata:
                        metadata_parts.append(f"{node_type} metadata: {metadata}")
                else:
                    # Handle relationship or other dict structures
                    if 'start' in value and 'end' in value:
                        # It's a relationship
                        rel_type = value.get('type', 'RELATED_TO')
                        start_props = value.get('start', {}).get('properties', {})
                        end_props = value.get('end', {}).get('properties', {})
                        
                        # Get text from start and end nodes
                        if start_props.get('text'):
                            text_contents.append(f"[Start Node] {start_props['text'][:300]}")
                        if end_props.get('text'):
                            text_contents.append(f"[End Node] {end_props['text'][:300]}")
                        
                        metadata_parts.append(f"Relationship: {rel_type}")
                    else:
                        metadata_parts.append(f"{key}: {str(value)[:200]}")
            elif isinstance(value, (str, int, float)):
                # Direct values
                if isinstance(value, str) and len(value) > 50:
                    # Long strings might be text content
                    text_contents.append(f"{key}: {value[:300]}")
                else:
                    metadata_parts.append(f"{key}: {str(value)}")
        
        # Combine: text content first, then metadata
        if text_contents:
            record_text.extend(text_contents)
        if metadata_parts:
            record_text.extend(metadata_parts)
        
        if record_text:
            context_parts.append(f"Result {i}:\n" + "\n".join(record_text))
    
    return "\n\n".join(context_parts) if context_parts else "No meaningful data extracted from results."


def execute_cypher_query(query: str, db_name: str):
    """Helper function to execute a Cypher query and return results as JSON response"""
    import neo4j
    
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USERNAME = os.getenv('NEO4J_USERNAME', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'lng-graphrag-password')
    
    driver = None
    try:
        driver = neo4j.GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
            connection_timeout=30
        )
        
        with driver.session(database=db_name) as session:
            result = session.run(query)
            
            # Collect results - properly serialize Neo4j nodes and relationships
            records = []
            for record in result:
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
                                serialized_list.append({
                                    'identity': item.id,
                                    'labels': list(item.labels),
                                    'properties': dict(item)
                                })
                            elif hasattr(item, 'type') and hasattr(item, 'start_node'):
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
                    elif hasattr(value, '__dict__'):
                        try:
                            record_dict[key] = dict(value)
                        except:
                            record_dict[key] = str(value)
                    else:
                        record_dict[key] = value
                records.append(record_dict)
            
            summary = result.consume()
            
            if auth_configured() and getattr(current_user, 'is_authenticated', False):
                auth_record_query(current_user.id, 'cypher', query, result_count=len(records))
            
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
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Query execution failed: {str(e)}',
            'query': query
        }), 500
    finally:
        if driver:
            driver.close()


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
    try:
        chunk_id = int(data.get('chunk_id')) if data.get('chunk_id') is not None else None
    except (TypeError, ValueError):
        chunk_id = None
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
        
        from own_graph_rag import (
            get_transcription_file_path,
            parse_transcription_chunks,
            write_full_transcription_to_edit_file,
            write_edit_record_to_history,
            update_chunk_in_neo4j,
        )
        import os as os_module
        from dotenv import load_dotenv
        
        load_dotenv()
        
        # Get current chunks to read old_text for edit_history
        current_path = get_transcription_file_path(filename, TRANSCRIPTIONS_DIR, EDIT_DIR)
        chunks = parse_transcription_chunks(current_path) if current_path else []
        old_text = chunks[chunk_id]["text"] if chunk_id < len(chunks) else ""
        username = "anonymous"
        if auth_configured() and getattr(current_user, "is_authenticated", False):
            username = getattr(current_user, "username", "") or "anonymous"
        
        # Save entire edited transcription to edit/ and append record (with username) to edit_history/
        file_updated = write_full_transcription_to_edit_file(
            TRANSCRIPTIONS_DIR,
            EDIT_DIR,
            EDIT_HISTORY_DIR,
            filename,
            chunk_id,
            new_text,
        )
        if not file_updated:
            return jsonify({
                'success': False,
                'error': 'Failed to write edit to file'
            }), 500
        
        write_edit_record_to_history(
            EDIT_HISTORY_DIR,
            filename,
            chunk_id,
            old_text,
            new_text,
            username,
        )
        
        edit_filename = filename.replace('_combined.txt', '_combined_edit.txt')
        edit_file_path = os.path.join(EDIT_DIR, edit_filename)
        
        # Update Neo4j (document name is the filename)
        document_name = filename
        db_name = os_module.getenv('NEO4J_DB_NAME', 'lng_transcriptions')
        
        neo4j_result = asyncio.run(update_chunk_in_neo4j(
            document_name=document_name,
            chunk_id=chunk_id,
            new_text=new_text,
            db_name=db_name
        ))
        
        neo4j_updated = neo4j_result.get('success', False)
        neo4j_error = neo4j_result.get('error', '')
        chunk_not_found = neo4j_error and 'not found in document' in neo4j_error
        
        if not neo4j_updated and not chunk_not_found:
            return jsonify({
                'success': False,
                'error': f"Failed to update Neo4j: {neo4j_error or 'Unknown error'}",
                'file_updated': True
            }), 500
        
        if auth_configured() and getattr(current_user, 'is_authenticated', False):
            auth_record_edit(current_user.id, document_name, chunk_id, new_text, old_text=old_text)
        
        if neo4j_updated:
            message = 'Transcription chunk updated successfully in Neo4j and edit file'
        else:
            message = (
                'Edit saved to file. Chunk not found in Neo4j for this document '
                '(load or reload this transcription into Neo4j to sync embeddings).'
            )
        return jsonify({
            'success': True,
            'message': message,
            'document_name': document_name,
            'chunk_id': chunk_id,
            'edit_file': os.path.basename(edit_file_path),
            'neo4j_updated': neo4j_updated
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

@app.route('/api/transcription/reload', methods=['POST'])
def api_reload_transcription():
    """
    Re-load a re-transcribed file into Neo4j: delete all Chunk nodes for that document_name,
    then create new chunks (and concepts) from the transcription file.
    """
    data = request.get_json() or {}
    filename = data.get('filename', '')
    embedding_backend = data.get('embedding', 'nomic')
    if embedding_backend not in ('nomic', 'openai', 'both'):
        embedding_backend = 'nomic'

    filename = os.path.basename(filename)
    if not filename.endswith('_combined.txt'):
        return jsonify({
            'success': False,
            'error': 'Invalid filename: must end with _combined.txt'
        }), 400

    transcription_path = os.path.join(TRANSCRIPTIONS_DIR, filename)
    if not os.path.exists(transcription_path):
        return jsonify({
            'success': False,
            'error': 'Transcription file not found'
        }), 404

    try:
        graphrag_path = os.path.join(os.path.dirname(__file__), 'graphrag')
        if graphrag_path not in sys.path:
            sys.path.insert(0, graphrag_path)
        from own_graph_rag import reload_document_in_neo4j
        import os as os_module
        from dotenv import load_dotenv
        load_dotenv()

        url_mapping = {}
        csv_path = os.path.join(os.path.dirname(__file__), 'VODs', 'videos.csv')
        if os.path.isfile(csv_path):
            import csv
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    title = (row.get('title') or '').strip()
                    if title and (filename.startswith(title) or filename.replace('_combined.txt', '') == title):
                        url_mapping[filename] = (row.get('url') or '').strip()
                        break

        db_name = os_module.getenv('NEO4J_DB_NAME', 'lng_transcriptions')
        result = asyncio.run(reload_document_in_neo4j(
            path=os.path.abspath(transcription_path),
            db_name=db_name,
            embedding_backend=embedding_backend,
            url_mapping_dict=url_mapping or None,
        ))
        if not result.get('success'):
            return jsonify({
                'success': False,
                'error': result.get('error', 'Reload failed')
            }), 500
        return jsonify({
            'success': True,
            'document_name': result.get('document_name'),
            'deleted_count': result.get('deleted_count', 0),
            'message': result.get('message', 'Reload complete'),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
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

