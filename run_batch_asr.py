#!/usr/bin/env python3
"""
Simple script to run batch ASR processing on videos from CSV.
This script processes videos one at a time: download -> transcribe -> save -> cleanup.
"""

import sys
import os
from batch_asr_processor import process_videos_from_csv

def main():
    print("🎬 LNG GraphRAG Batch ASR Processor")
    print("=" * 50)
    
    # Check if CSV file exists
    csv_file = "./VODs/videos.csv"
    if not os.path.exists(csv_file):
        print(f"❌ CSV file not found: {csv_file}")
        print("💡 Please run the download script first to generate the CSV file.")
        return
    
    # Get user preferences
    print(f"📋 Found CSV file: {csv_file}")
    
    try:
        # Ask user for processing options
        print("\n🔧 Processing Options:")
        print("1. Process all pending videos")
        print("2. Process first N videos")
        print("3. Process from specific index")
        
        choice = input("\nEnter your choice (1-3): ").strip()
        
        start_index = 0
        max_videos = None
        
        if choice == "2":
            try:
                max_videos = int(input("How many videos to process? "))
            except ValueError:
                print("❌ Invalid number. Processing all videos.")
                max_videos = None
        elif choice == "3":
            try:
                start_index = int(input("Start from which index? "))
                max_videos_input = input("How many videos to process? (press Enter for all): ").strip()
                if max_videos_input:
                    max_videos = int(max_videos_input)
            except ValueError:
                print("❌ Invalid number. Using default values.")
                start_index = 0
                max_videos = None
        
        print(f"\n🚀 Starting batch processing...")
        print(f"📊 Start index: {start_index}")
        print(f"📊 Max videos: {max_videos if max_videos else 'All'}")
        
        # Start processing
        process_videos_from_csv(csv_file, start_index, max_videos)
        
    except KeyboardInterrupt:
        print("\n⚠️  Processing interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
