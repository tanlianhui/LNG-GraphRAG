#!/usr/bin/env python3
"""
Launch script for LNG GraphRAG Web Dashboard
"""
import sys
import os

# Ensure stdout can handle Unicode on Windows (e.g. when piped to a log file)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.web_app import app

if __name__ == '__main__':
    print("=" * 60)
    print("LNG GraphRAG Web Dashboard")
    print("=" * 60)
    print("\nStarting web server...")
    print("Dashboard will be available at: http://localhost:5000")
    print("Press Ctrl+C to stop the server\n")
    print("-" * 60)
    
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped. Goodbye!")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        sys.exit(1)

