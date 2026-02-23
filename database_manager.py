#!/usr/bin/env python3
"""
Database manager for LNG GraphRAG project.
Uses MySQL (same DB as auth) for file status, downloads, and processing jobs.
Requires PyMySQL and MySQL (e.g. docker-compose up -d mysql). See AUTH_SETUP.md.
"""

from auth_db import get_connection, init_tables, is_configured

# Optional: use PyMySQL for direct checks
try:
    import pymysql
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False


class DatabaseManager:
    """Manages files, downloads, and processing_jobs in MySQL (shared with auth DB)."""

    def __init__(self, db_path=None):
        # db_path ignored; kept for backward compatibility with callers that pass it
        if not PYMYSQL_AVAILABLE:
            raise RuntimeError("PyMySQL is required. Run: pip install pymysql")
        if not is_configured():
            raise RuntimeError(
                "MySQL is not configured. Set MYSQL_* env (or use defaults) and start MySQL, e.g. docker-compose up -d mysql. See AUTH_SETUP.md."
            )
        with get_connection() as conn:
            init_tables(conn)

    def add_file(self, filename, file_path, file_type, file_size=None, duration=None):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO files (filename, file_path, file_type, file_size, duration)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (filename, file_path, file_type, file_size, duration),
                )
                return cur.lastrowid

    def add_download(self, url, title=None):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO downloads (url, title) VALUES (%s, %s)",
                    (url, title),
                )
                return cur.lastrowid

    def update_file_status(self, file_id, status, error_message=None, transcription_path=None):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE files
                    SET status = %s, error_message = %s, transcription_path = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (status, error_message, transcription_path, file_id),
                )

    def update_download_status(self, download_id, status, file_id=None, error_message=None):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE downloads
                    SET status = %s, file_id = %s, error_message = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (status, file_id, error_message, download_id),
                )

    def add_processing_job(self, file_id, job_type):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO processing_jobs (file_id, job_type, started_at) VALUES (%s, %s, CURRENT_TIMESTAMP)",
                    (file_id, job_type),
                )
                return cur.lastrowid

    def update_processing_job(self, job_id, status, error_message=None):
        with get_connection() as conn:
            with conn.cursor() as cur:
                if status == "completed":
                    cur.execute(
                        """
                        UPDATE processing_jobs
                        SET status = %s, completed_at = CURRENT_TIMESTAMP, error_message = %s
                        WHERE id = %s
                        """,
                        (status, error_message, job_id),
                    )
                else:
                    cur.execute(
                        "UPDATE processing_jobs SET status = %s, error_message = %s WHERE id = %s",
                        (status, error_message, job_id),
                    )

    def delete_file(self, file_id):
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT filename, file_path, transcription_path FROM files WHERE id = %s",
                        (file_id,),
                    )
                    file_info = cur.fetchone()
                    if not file_info:
                        return False, "File not found"
                    filename, file_path, transcription_path = file_info
                    cur.execute("DELETE FROM processing_jobs WHERE file_id = %s", (file_id,))
                    cur.execute("UPDATE downloads SET file_id = NULL WHERE file_id = %s", (file_id,))
                    cur.execute("DELETE FROM files WHERE id = %s", (file_id,))
                conn.commit()
            return True, {"filename": filename, "file_path": file_path, "transcription_path": transcription_path}
        except Exception as e:
            return False, str(e)

    def delete_multiple_files(self, file_ids):
        results = []
        for file_id in file_ids:
            success, result = self.delete_file(file_id)
            results.append({"file_id": file_id, "success": success, "result": result})
        return results

    def delete_download(self, download_id):
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT url, title FROM downloads WHERE id = %s", (download_id,))
                    if not cur.fetchone():
                        return False
                    cur.execute("DELETE FROM downloads WHERE id = %s", (download_id,))
                conn.commit()
            return True
        except Exception:
            return False

    def get_files_by_status(self, status):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM files WHERE status = %s ORDER BY created_at DESC",
                    (status,),
                )
                return cur.fetchall()

    def get_all_files(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT f.id, f.filename, f.file_path, f.file_type, f.status, f.created_at, f.updated_at,
                           f.file_size, f.duration, f.transcription_path, f.error_message, d.url, d.title
                    FROM files f
                    LEFT JOIN downloads d ON f.id = d.file_id
                    ORDER BY f.created_at DESC
                    """
                )
                return cur.fetchall()

    def get_file_by_id(self, file_id):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM files WHERE id = %s", (file_id,))
                return cur.fetchone()

    def link_download_to_file(self, download_id, file_id):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE downloads SET file_id = %s WHERE id = %s", (file_id, download_id))

    def get_downloads_by_status(self, status):
        with get_connection() as conn:
            with conn.cursor() as cur:
                if status == "all":
                    cur.execute("SELECT * FROM downloads ORDER BY created_at DESC")
                else:
                    cur.execute(
                        "SELECT * FROM downloads WHERE status = %s ORDER BY created_at DESC",
                        (status,),
                    )
                return cur.fetchall()

    def get_processing_jobs_by_status(self, status):
        with get_connection() as conn:
            with conn.cursor() as cur:
                if status == "all":
                    cur.execute(
                        """
                        SELECT pj.id, pj.file_id, pj.job_type, pj.status, pj.started_at, pj.completed_at,
                               pj.error_message, f.filename, f.file_path
                        FROM processing_jobs pj
                        JOIN files f ON pj.file_id = f.id
                        ORDER BY pj.started_at DESC
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT pj.id, pj.file_id, pj.job_type, pj.status, pj.started_at, pj.completed_at,
                               pj.error_message, f.filename, f.file_path
                        FROM processing_jobs pj
                        JOIN files f ON pj.file_id = f.id
                        WHERE pj.status = %s
                        ORDER BY pj.started_at DESC
                        """,
                        (status,),
                    )
                return cur.fetchall()

    def cleanup_interrupted_processes(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE files SET status = 'pending', error_message = 'Process interrupted - reset to pending' WHERE status = 'processing'"
                )
                cur.execute(
                    "UPDATE downloads SET status = 'pending', error_message = 'Download interrupted - reset to pending' WHERE status = 'downloading'"
                )
                cur.execute(
                    "UPDATE processing_jobs SET status = 'failed', error_message = 'Process interrupted - system restart' WHERE status = 'processing'"
                )
                cur.execute(
                    "UPDATE processing_jobs SET status = 'failed', error_message = 'Process interrupted - system restart' WHERE status = 'pending' AND started_at IS NOT NULL"
                )
                cur.execute(
                    'SELECT COUNT(*) FROM files WHERE status = "pending" AND error_message LIKE %s',
                    ("%interrupted%",),
                )
                cleaned_files = cur.fetchone()[0]
                cur.execute(
                    'SELECT COUNT(*) FROM downloads WHERE status = "pending" AND error_message LIKE %s',
                    ("%interrupted%",),
                )
                cleaned_downloads = cur.fetchone()[0]
                cur.execute(
                    'SELECT COUNT(*) FROM processing_jobs WHERE status = "failed" AND error_message LIKE %s',
                    ("%interrupted%",),
                )
                cleaned_jobs = cur.fetchone()[0]
        return {
            "cleaned_files": cleaned_files,
            "cleaned_downloads": cleaned_downloads,
            "cleaned_jobs": cleaned_jobs,
        }

    def get_statistics(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM files")
                total_files = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM files WHERE status = 'completed'")
                completed_files = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM files WHERE status = 'failed'")
                failed_files = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM downloads")
                total_downloads = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM downloads WHERE status = 'completed'")
                completed_downloads = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM processing_jobs WHERE job_type = 'asr'")
                total_asr_jobs = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM processing_jobs WHERE job_type = 'asr' AND status = 'completed'")
                completed_asr_jobs = cur.fetchone()[0]
        return {
            "total_files": total_files,
            "completed_files": completed_files,
            "failed_files": failed_files,
            "total_downloads": total_downloads,
            "completed_downloads": completed_downloads,
            "total_asr_jobs": total_asr_jobs,
            "completed_asr_jobs": completed_asr_jobs,
        }
