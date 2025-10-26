#!/usr/bin/env python3
"""
Database manager for LNG GraphRAG project
Handles file status tracking and management
"""

import sqlite3
import os
from datetime import datetime
from pathlib import Path

class DatabaseManager:
    def __init__(self, db_path="lng_graphrag.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create files table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_size INTEGER,
                duration REAL,
                transcription_path TEXT,
                error_message TEXT
            )
        ''')
        
        # Create downloads table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                title TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_id INTEGER,
                error_message TEXT,
                FOREIGN KEY (file_id) REFERENCES files (id)
            )
        ''')
        
        # Create processing_jobs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processing_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (file_id) REFERENCES files (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_file(self, filename, file_path, file_type, file_size=None, duration=None):
        """Add a new file to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO files (filename, file_path, file_type, file_size, duration)
            VALUES (?, ?, ?, ?, ?)
        ''', (filename, file_path, file_type, file_size, duration))
        
        file_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return file_id
    
    def add_download(self, url, title=None):
        """Add a new download to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO downloads (url, title)
            VALUES (?, ?)
        ''', (url, title))
        
        download_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return download_id
    
    def update_file_status(self, file_id, status, error_message=None, transcription_path=None):
        """Update file status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE files 
            SET status = ?, error_message = ?, transcription_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, error_message, transcription_path, file_id))
        
        conn.commit()
        conn.close()
    
    def update_download_status(self, download_id, status, file_id=None, error_message=None):
        """Update download status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE downloads 
            SET status = ?, file_id = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, file_id, error_message, download_id))
        
        conn.commit()
        conn.close()
    
    def add_processing_job(self, file_id, job_type):
        """Add a new processing job"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO processing_jobs (file_id, job_type, started_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (file_id, job_type))
        
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return job_id
    
    def update_processing_job(self, job_id, status, error_message=None):
        """Update processing job status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if status == 'completed':
            cursor.execute('''
                UPDATE processing_jobs 
                SET status = ?, completed_at = CURRENT_TIMESTAMP, error_message = ?
                WHERE id = ?
            ''', (status, error_message, job_id))
        else:
            cursor.execute('''
                UPDATE processing_jobs 
                SET status = ?, error_message = ?
                WHERE id = ?
            ''', (status, error_message, job_id))
        
        conn.commit()
        conn.close()
    
    def delete_file(self, file_id):
        """Delete a file and all related data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Get file info before deletion
            cursor.execute('SELECT filename, file_path, transcription_path FROM files WHERE id = ?', (file_id,))
            file_info = cursor.fetchone()
            
            if not file_info:
                return False, "File not found"
            
            filename, file_path, transcription_path = file_info
            
            # Delete related processing jobs
            cursor.execute('DELETE FROM processing_jobs WHERE file_id = ?', (file_id,))
            
            # Update downloads that reference this file
            cursor.execute('UPDATE downloads SET file_id = NULL WHERE file_id = ?', (file_id,))
            
            # Delete the file record
            cursor.execute('DELETE FROM files WHERE id = ?', (file_id,))
            
            conn.commit()
            conn.close()
            
            return True, {
                'filename': filename,
                'file_path': file_path,
                'transcription_path': transcription_path
            }
            
        except Exception as e:
            conn.rollback()
            conn.close()
            return False, str(e)
    
    def delete_multiple_files(self, file_ids):
        """Delete multiple files and all related data"""
        results = []
        
        for file_id in file_ids:
            success, result = self.delete_file(file_id)
            results.append({
                'file_id': file_id,
                'success': success,
                'result': result
            })
        
        return results
    
    def delete_download(self, download_id):
        """Delete a download from the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Get download info before deletion
            cursor.execute('SELECT url, title FROM downloads WHERE id = ?', (download_id,))
            download_info = cursor.fetchone()
            
            if not download_info:
                return False
            
            # Delete the download record
            cursor.execute('DELETE FROM downloads WHERE id = ?', (download_id,))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            conn.rollback()
            conn.close()
            return False
    
    def get_files_by_status(self, status):
        """Get files by status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM files WHERE status = ? ORDER BY created_at DESC
        ''', (status,))
        
        files = cursor.fetchall()
        conn.close()
        return files
    
    def get_all_files(self):
        """Get all files"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT f.*, d.url, d.title as download_title
            FROM files f
            LEFT JOIN downloads d ON f.id = d.file_id
            ORDER BY f.created_at DESC
        ''')
        
        files = cursor.fetchall()
        conn.close()
        return files
    
    def get_file_by_id(self, file_id):
        """Get a specific file by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM files WHERE id = ?', (file_id,))
        file_data = cursor.fetchone()
        conn.close()
        return file_data
    
    def link_download_to_file(self, download_id, file_id):
        """Link a download to a file"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE downloads 
            SET file_id = ? 
            WHERE id = ?
        ''', (file_id, download_id))
        
        conn.commit()
        conn.close()
    
    def get_downloads_by_status(self, status):
        """Get downloads by status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if status == "all":
            cursor.execute('''
                SELECT * FROM downloads ORDER BY created_at DESC
            ''')
        else:
            cursor.execute('''
                SELECT * FROM downloads WHERE status = ? ORDER BY created_at DESC
            ''', (status,))
        
        downloads = cursor.fetchall()
        conn.close()
        return downloads
    
    def get_processing_jobs_by_status(self, status):
        """Get processing jobs by status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if status == "all":
            cursor.execute('''
                SELECT pj.*, f.filename, f.file_path
                FROM processing_jobs pj
                JOIN files f ON pj.file_id = f.id
                ORDER BY pj.started_at DESC
            ''')
        else:
            cursor.execute('''
                SELECT pj.*, f.filename, f.file_path
                FROM processing_jobs pj
                JOIN files f ON pj.file_id = f.id
                WHERE pj.status = ? ORDER BY pj.started_at DESC
            ''', (status,))
        
        jobs = cursor.fetchall()
        conn.close()
        return jobs
    
    def cleanup_interrupted_processes(self):
        """Clean up processes that were interrupted (e.g., due to system crash)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Reset files that were in processing state
        cursor.execute('''
            UPDATE files 
            SET status = 'pending', error_message = 'Process interrupted - reset to pending'
            WHERE status = 'processing'
        ''')
        
        # Reset downloads that were in downloading state
        cursor.execute('''
            UPDATE downloads 
            SET status = 'pending', error_message = 'Download interrupted - reset to pending'
            WHERE status = 'downloading'
        ''')
        
        # Mark processing jobs as failed if they were running
        cursor.execute('''
            UPDATE processing_jobs 
            SET status = 'failed', error_message = 'Process interrupted - system restart'
            WHERE status = 'processing'
        ''')
        
        # Mark processing jobs as failed if they were started but not completed
        cursor.execute('''
            UPDATE processing_jobs 
            SET status = 'failed', error_message = 'Process interrupted - system restart'
            WHERE status = 'pending' AND started_at IS NOT NULL
        ''')
        
        # Get count of cleaned up items
        cursor.execute('SELECT COUNT(*) FROM files WHERE status = "pending" AND error_message LIKE "%interrupted%"')
        cleaned_files = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM downloads WHERE status = "pending" AND error_message LIKE "%interrupted%"')
        cleaned_downloads = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM processing_jobs WHERE status = "failed" AND error_message LIKE "%interrupted%"')
        cleaned_jobs = cursor.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        return {
            'cleaned_files': cleaned_files,
            'cleaned_downloads': cleaned_downloads,
            'cleaned_jobs': cleaned_jobs
        }
    
    def get_statistics(self):
        """Get project statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # File statistics
        cursor.execute('SELECT COUNT(*) FROM files')
        total_files = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM files WHERE status = "completed"')
        completed_files = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM files WHERE status = "failed"')
        failed_files = cursor.fetchone()[0]
        
        # Download statistics
        cursor.execute('SELECT COUNT(*) FROM downloads')
        total_downloads = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM downloads WHERE status = "completed"')
        completed_downloads = cursor.fetchone()[0]
        
        # Processing statistics
        cursor.execute('SELECT COUNT(*) FROM processing_jobs WHERE job_type = "asr"')
        total_asr_jobs = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM processing_jobs WHERE job_type = "asr" AND status = "completed"')
        completed_asr_jobs = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_files': total_files,
            'completed_files': completed_files,
            'failed_files': failed_files,
            'total_downloads': total_downloads,
            'completed_downloads': completed_downloads,
            'total_asr_jobs': total_asr_jobs,
            'completed_asr_jobs': completed_asr_jobs
        }
