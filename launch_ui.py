#!/usr/bin/env python3
"""
Launch script for LNG GraphRAG UI
"""

import sys
import os
import tkinter as tk
from tkinter import messagebox
from utils import setup_path, safe_execute, log_error

def check_dependencies():
    """Check if required dependencies are installed"""
    required_modules = [
        'torch', 'torchaudio', 'transformers', 'datasets', 
        'yt_dlp', 'sqlite3'
    ]
    
    missing_modules = []
    
    for module in required_modules:
        try:
            if module == 'sqlite3':
                import sqlite3
            else:
                __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        error_msg = f"Missing required modules: {', '.join(missing_modules)}\n\n"
        error_msg += "Please install them using:\n"
        error_msg += "pip install torch torchaudio transformers datasets yt-dlp"
        
        messagebox.showerror("Missing Dependencies", error_msg)
        return False
    
    return True

def main():
    """Main launcher function"""
    setup_path()
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Import and run the UI
    success, result, error = safe_execute(lambda: __import__('lng_ui').main())
    
    if not success:
        messagebox.showerror("Error", f"Failed to start application: {error}")
        sys.exit(1)

if __name__ == "__main__":
    main()
