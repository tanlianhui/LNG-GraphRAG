#!/usr/bin/env python3
"""
Common utilities for LNG GraphRAG project
"""

import sys
import os
import traceback
from typing import Any, Callable, Optional

def setup_path():
    """Add current directory to Python path for imports"""
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def safe_execute(func: Callable, *args, **kwargs) -> tuple[bool, Any, Optional[str]]:
    """
    Safely execute a function with error handling
    
    Returns:
        tuple: (success: bool, result: Any, error_message: Optional[str])
    """
    try:
        result = func(*args, **kwargs)
        return True, result, None
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        return False, None, error_msg

def log_error(error: Exception, context: str = "") -> str:
    """
    Log error with context and return formatted error message
    
    Args:
        error: Exception object
        context: Additional context for the error
        
    Returns:
        str: Formatted error message
    """
    error_msg = f"{type(error).__name__}: {str(error)}"
    if context:
        error_msg = f"{context} - {error_msg}"
    return error_msg

def handle_unicode_encoding():
    """Set up UTF-8 encoding for console output"""
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass  # Fallback if encoding setup fails

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    return f"{size:.1f} {size_names[i]}"

def format_duration(seconds: float) -> str:
    """Format duration in human readable format"""
    if seconds is None or seconds < 0:
        return "Unknown"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"
