#!/usr/bin/env python3
"""
Find transcription files without timestamps and match them with videos.csv
"""

import os
import re
import csv
from pathlib import Path

def has_timestamps(file_path):
    """Check if a transcription file has timestamps in the format [X.XXs - Y.YYs]"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Look for timestamp pattern: [X.XXs - Y.YYs]
        timestamp_pattern = r'\[\d+\.?\d*s\s*-\s*\d+\.?\d*s\]'
        return bool(re.search(timestamp_pattern, content))
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return False

def normalize_title(title):
    """Normalize title for matching (remove special characters, normalize separators)"""
    # Replace various separator characters with a standard one
    title = title.replace('⧸', '/').replace('／', '/')
    # Remove extra spaces
    title = re.sub(r'\s+', ' ', title)
    return title.strip()

def find_matching_video(title, videos_csv):
    """Find matching video URL from videos.csv"""
    # Try exact match first
    for row in videos_csv:
        if row['title'] == title:
            return row['url']
    
    # Try normalized match
    normalized_title = normalize_title(title)
    for row in videos_csv:
        if normalize_title(row['title']) == normalized_title:
            return row['url']
    
    # Try partial match (remove _combined.txt and compare)
    title_base = title.replace('_combined.txt', '')
    for row in videos_csv:
        if row['title'] == title_base:
            return row['url']
    
    # Try normalized partial match
    normalized_base = normalize_title(title_base)
    for row in videos_csv:
        if normalize_title(row['title']) == normalized_base:
            return row['url']
    
    return None

def main():
    transcriptions_dir = Path("./transcriptions")
    videos_csv_path = Path("./VODs/videos.csv")
    
    # Read videos.csv
    videos = []
    with open(videos_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        videos = list(reader)
    
    print(f"Loaded {len(videos)} videos from videos.csv\n")
    
    # Find all transcription files
    transcription_files = list(transcriptions_dir.glob("*_combined.txt"))
    print(f"Found {len(transcription_files)} transcription files\n")
    
    # Check each file for timestamps
    files_without_timestamps = []
    
    for file_path in transcription_files:
        if not has_timestamps(file_path):
            files_without_timestamps.append(file_path)
    
    print(f"Found {len(files_without_timestamps)} files without timestamps:\n")
    
    # Match with videos.csv
    results = []
    for file_path in files_without_timestamps:
        filename = file_path.name
        title = filename.replace('_combined.txt', '')
        url = find_matching_video(title, videos)
        
        results.append({
            'filename': filename,
            'title': title,
            'url': url
        })
    
    # Print results
    print("=" * 80)
    print("FILES WITHOUT TIMESTAMPS:")
    print("=" * 80)
    print()
    
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['filename']}")
        print(f"   Title: {result['title']}")
        if result['url']:
            print(f"   URL: {result['url']}")
        else:
            print(f"   URL: NOT FOUND in videos.csv")
        print()
    
    # Summary
    found_count = sum(1 for r in results if r['url'])
    not_found_count = len(results) - found_count
    
    print("=" * 80)
    print("SUMMARY:")
    print(f"  Total files without timestamps: {len(results)}")
    print(f"  Matched with URLs: {found_count}")
    print(f"  Not found in videos.csv: {not_found_count}")
    print("=" * 80)
    
    # Save to CSV for easy processing
    output_csv = "files_to_rerun.csv"
    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['filename', 'title', 'url'])
        writer.writeheader()
        for result in results:
            writer.writerow(result)
    
    print(f"\nResults saved to: {output_csv}")

if __name__ == "__main__":
    main()

