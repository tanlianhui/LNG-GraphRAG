#!/usr/bin/env python3
"""
Manual database cleanup script for LNG GraphRAG
Use this script to clean up interrupted processes if the UI is not available
"""

import sys
import os
from utils import setup_path, safe_execute, log_error
from database_manager import DatabaseManager

def main():
    setup_path()
    
    print("LNG GraphRAG Database Cleanup")
    print("=" * 40)
    
    # Initialize database manager
    success, db, error = safe_execute(DatabaseManager)
    if not success:
        print(f"Error initializing database: {error}")
        sys.exit(1)
    
    print("Cleaning up interrupted processes...")
    success, cleanup_results, error = safe_execute(db.cleanup_interrupted_processes)
    
    if not success:
        print(f"Error during cleanup: {error}")
        sys.exit(1)
    
    if any(cleanup_results.values()):
        print("\nCleanup completed:")
        if cleanup_results['cleaned_files'] > 0:
            print(f"  - Reset {cleanup_results['cleaned_files']} interrupted file processes")
        if cleanup_results['cleaned_downloads'] > 0:
            print(f"  - Reset {cleanup_results['cleaned_downloads']} interrupted downloads")
        if cleanup_results['cleaned_jobs'] > 0:
            print(f"  - Marked {cleanup_results['cleaned_jobs']} interrupted jobs as failed")
        
        print(f"\nTotal items cleaned: {sum(cleanup_results.values())}")
    else:
        print("No interrupted processes found")
    
    # Show current statistics
    print("\nCurrent database statistics:")
    success, stats, error = safe_execute(db.get_statistics)
    if success:
        for key, value in stats.items():
            print(f"  {key}: {value}")
    else:
        print(f"Error getting statistics: {error}")
    
    print("\nCleanup completed successfully!")

if __name__ == "__main__":
    main()
