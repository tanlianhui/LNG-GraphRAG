#!/usr/bin/env python3
"""
Cookie Export Guide for YouTube Downloads
This script helps users export cookies from their browser to avoid 403 errors.
"""

import os
import sys
from pathlib import Path

def print_guide():
    print("YouTube Cookie Export Guide")
    print("=" * 50)
    print()
    print("To avoid 403 Forbidden errors, you need to export cookies from your browser.")
    print("This allows the downloader to authenticate as you.")
    print()
    print("Method 1: Using Browser Extension (Recommended)")
    print("-" * 40)
    print("1. Install 'Get cookies.txt' extension in Chrome/Edge:")
    print("   https://chrome.google.com/webstore/detail/get-cookiestxt/bgaddhkoddajcdgocldbbfleckgcbcid")
    print()
    print("2. Go to YouTube and make sure you're logged in")
    print("3. Click the extension icon and select 'Export'")
    print("4. Save the file as 'www.youtube.com_cookies.txt' in the VODs folder")
    print()
    print("Method 2: Using yt-dlp (Alternative)")
    print("-" * 40)
    print("1. Install yt-dlp: pip install yt-dlp")
    print("2. Run: yt-dlp --cookies-from-browser chrome --print-traffic")
    print("3. This will show you how to extract cookies")
    print()
    print("Method 3: Manual Export (Advanced)")
    print("-" * 40)
    print("1. Open Chrome DevTools (F12)")
    print("2. Go to Application tab > Cookies > https://www.youtube.com")
    print("3. Copy all cookies and save as cookies.txt format")
    print()
    print("Checking for existing cookies...")
    
    cookie_file = Path("./VODs/www.youtube.com_cookies.txt")
    if cookie_file.exists():
        print(f"Found existing cookies file: {cookie_file}")
        print("If you're still getting 403 errors, try exporting fresh cookies")
    else:
        print(f"No cookies file found: {cookie_file}")
        print("Please follow one of the methods above to export cookies")
    
    print()
    print("After exporting cookies, run the download script again:")
    print("   python VODs/download_from_youtube.py")

def check_requirements():
    """Check if required tools are available"""
    print("Checking requirements...")
    
    try:
        import yt_dlp
        print("yt-dlp is installed")
    except ImportError:
        print("yt_dlp not found. Install with: pip install yt-dlp")
        return False
    
    try:
        import requests
        print("requests is installed")
    except ImportError:
        print("requests not found. Install with: pip install requests")
        return False
    
    return True

def main():
    print_guide()
    
    if not check_requirements():
        print("\nMissing requirements. Please install them first.")
        sys.exit(1)
    
    print("\nAll requirements met!")
    print("Follow the cookie export guide above to get started.")

if __name__ == "__main__":
    main()
