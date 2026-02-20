"""
User authentication and history storage using MySQL.
Creates tables: users, edit_history, query_history.
"""
import os
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

# Optional: use PyMySQL if available
try:
    import pymysql
    from pymysql.cursors import DictCursor
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False
    pymysql = None
    DictCursor = None


def get_db_config() -> Dict[str, str]:
    """Read MySQL config from environment. Defaults match docker-compose.yml so no .env is needed for local Docker MySQL."""
    # Use "or" so empty MYSQL_PASSWORD in .env doesn't override the Docker default
    password = os.getenv("MYSQL_PASSWORD") or "lng-graphrag-password"
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "lng_user"),
        "password": password,
        "database": os.getenv("MYSQL_DATABASE", "lng_graphrag_auth"),
        "charset": "utf8mb4",
    }


def is_configured() -> bool:
    """Return True if MySQL is available and configured (password can be empty for local)."""
    if not PYMYSQL_AVAILABLE:
        return False
    cfg = get_db_config()
    return bool(cfg.get("database"))


@contextmanager
def get_connection():
    """Context manager for MySQL connection. Creates database if missing."""
    if not PYMYSQL_AVAILABLE:
        raise RuntimeError("PyMySQL is not installed. Run: pip install pymysql")
    cfg = get_db_config().copy()
    db_name = cfg.pop("database")
    # Connect without database first to create it (cfg already has charset)
    conn = pymysql.connect(**cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.select_db(db_name)
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_tables(conn) -> None:
    """Create users, edit_history, query_history if they don't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(80) NOT NULL UNIQUE,
                email VARCHAR(120) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS edit_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                document_name VARCHAR(255) NOT NULL,
                chunk_id INT NOT NULL,
                old_text TEXT,
                new_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_created (user_id, created_at)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS query_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                query_type ENUM('nl', 'cypher') NOT NULL,
                query_text TEXT NOT NULL,
                result_count INT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_created (user_id, created_at)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token VARCHAR(64) PRIMARY KEY,
                user_id INT NOT NULL,
                expires_at DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_expires (expires_at)
            )
        """)


# --- User CRUD (for Flask-Login) ---

def create_user(username: str, email: str, password_hash: str) -> Optional[int]:
    """Insert user; return user id or None on duplicate."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                    (username.strip(), email.strip().lower(), password_hash)
                )
                return cur.lastrowid
    except Exception as e:
        if "Duplicate" in str(e) or "1062" in str(e):
            return None
        raise


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Return user row by id or None."""
    try:
        with get_connection() as conn:
            with conn.cursor(DictCursor) as cur:
                cur.execute("SELECT id, username, email, password_hash, created_at FROM users WHERE id = %s", (user_id,))
                return cur.fetchone()
    except Exception:
        return None


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Return user row by username or None."""
    try:
        with get_connection() as conn:
            with conn.cursor(DictCursor) as cur:
                cur.execute(
                    "SELECT id, username, email, password_hash, created_at FROM users WHERE username = %s",
                    (username.strip(),)
                )
                return cur.fetchone()
    except Exception:
        return None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Return user row by email or None."""
    try:
        with get_connection() as conn:
            with conn.cursor(DictCursor) as cur:
                cur.execute(
                    "SELECT id, username, email, password_hash, created_at FROM users WHERE email = %s",
                    (email.strip().lower(),)
                )
                return cur.fetchone()
    except Exception:
        return None


def create_reset_token(token: str, user_id: int, expires_at) -> None:
    """Store a password reset token."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)",
                    (token, user_id, expires_at)
                )
    except Exception as e:
        raise RuntimeError(f"Failed to create reset token: {e}") from e


def get_user_by_reset_token(token: str):
    """Return user row if token is valid and not expired; else None. Deletes expired tokens."""
    try:
        with get_connection() as conn:
            with conn.cursor(DictCursor) as cur:
                cur.execute(
                    "DELETE FROM password_reset_tokens WHERE expires_at < NOW()"
                )
                cur.execute(
                    """SELECT u.id, u.username, u.email, u.password_hash, u.created_at
                       FROM users u
                       INNER JOIN password_reset_tokens t ON t.user_id = u.id
                       WHERE t.token = %s AND t.expires_at > NOW()""",
                    (token.strip(),)
                )
                return cur.fetchone()
    except Exception:
        return None


def delete_reset_token(token: str) -> None:
    """Remove a reset token (after use or on demand)."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM password_reset_tokens WHERE token = %s", (token.strip(),))
    except Exception:
        pass


def update_user_password(user_id: int, password_hash: str) -> bool:
    """Update user password by id. Returns True on success."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
                return cur.rowcount == 1
    except Exception:
        return False


class User:
    """Minimal user object for Flask-Login (id, is_authenticated, is_active, get_id)."""
    def __init__(self, row: Dict[str, Any]):
        self.id = row["id"]
        self.username = row["username"]
        self.email = row["email"]
        self.password_hash = row["password_hash"]
        self.created_at = row.get("created_at")

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)


def get_user_for_flask(user_id: int) -> Optional[User]:
    """Load user by id for Flask-Login user_loader. Returns User or None."""
    row = get_user_by_id(user_id)
    return User(row) if row else None


# --- History recording ---

def record_edit(user_id: int, document_name: str, chunk_id: int, new_text: str, old_text: Optional[str] = None) -> None:
    """Append one transcription edit to edit_history."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO edit_history (user_id, document_name, chunk_id, old_text, new_text) VALUES (%s, %s, %s, %s, %s)",
                    (user_id, document_name, chunk_id, old_text or None, new_text)
                )
    except Exception as e:
        print(f"auth_db: record_edit failed: {e}")


def record_query(user_id: int, query_type: str, query_text: str, result_count: Optional[int] = None) -> None:
    """Append one query to query_history. query_type must be 'nl' or 'cypher'."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO query_history (user_id, query_type, query_text, result_count) VALUES (%s, %s, %s, %s)",
                    (user_id, query_type, query_text[:65535], result_count)
                )
    except Exception as e:
        print(f"auth_db: record_query failed: {e}")


def get_edit_history(user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    """Return recent edit_history rows for user (newest first)."""
    try:
        with get_connection() as conn:
            with conn.cursor(DictCursor) as cur:
                cur.execute(
                    "SELECT id, document_name, chunk_id, old_text, new_text, created_at FROM edit_history WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                    (user_id, limit)
                )
                rows = cur.fetchall()
                return [dict(r) for r in rows] if rows else []
    except Exception as e:
        print(f"auth_db: get_edit_history failed: {e}")
        return []


def get_query_history(user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    """Return recent query_history rows for user (newest first)."""
    try:
        with get_connection() as conn:
            with conn.cursor(DictCursor) as cur:
                cur.execute(
                    "SELECT id, query_type, query_text, result_count, created_at FROM query_history WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                    (user_id, limit)
                )
                rows = cur.fetchall()
                return [dict(r) for r in rows] if rows else []
    except Exception as e:
        print(f"auth_db: get_query_history failed: {e}")
        return []
