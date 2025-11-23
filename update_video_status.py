#!/usr/bin/env python3
"""
Update videos.csv status based on file existence:
- 'pending': WAV file has never been downloaded
- 'downloaded': WAV file has been fully downloaded
- 'completed': ASR has been run (transcription file exists)

Status progression is unidirectional: pending → downloaded → completed
"""

import csv
import os
from pathlib import Path

CSV_FILE = "./VODs/videos.csv"
VODS_DIR = "./VODs"
TRANSCRIPTIONS_DIR = "./transcriptions"

# Status hierarchy (higher number = more complete)
STATUS_HIERARCHY = {
    'pending': 0,
    'downloaded': 1,
    'completed': 2
}

def normalize_for_matching(text):
    """
    Normalize text for flexible matching by handling common variations.
    """
    if not text:
        return ""
    # Replace different slash characters with standard forward slash
    text = text.replace('⧸', '/').replace('\\', '/')
    # Remove extra whitespace
    text = ' '.join(text.split())
    return text

def find_matching_transcription(title, transcription_files):
    """
    Find a matching transcription file for a given title.
    Handles variations in date formats and other characters.
    """
    normalized_title = normalize_for_matching(title)
    
    # First try exact match
    exact_match = f"{title}_combined.txt"
    if exact_match in transcription_files:
        return True
    
    # Try normalized match
    for trans_file in transcription_files:
        trans_name = trans_file.replace('_combined.txt', '')
        normalized_trans = normalize_for_matching(trans_name)
        if normalized_title == normalized_trans:
            return True
    
    # Try partial match (for cases where only part of the title matches)
    # This handles cases where the filename might have slight variations
    title_parts = normalized_title.replace('【LNG】', '').strip()
    for trans_file in transcription_files:
        trans_name = trans_file.replace('_combined.txt', '')
        normalized_trans = normalize_for_matching(trans_name)
        trans_parts = normalized_trans.replace('【LNG】', '').strip()
        
        # Check if significant parts match (at least 80% of shorter string)
        if title_parts and trans_parts:
            shorter = min(len(title_parts), len(trans_parts))
            longer = max(len(title_parts), len(trans_parts))
            if shorter > 0 and (shorter / longer) > 0.8:
                # Check if they share significant common substrings
                if title_parts in trans_parts or trans_parts in title_parts:
                    return True
    
    return False

def get_status_for_video(title, transcription_files):
    """
    Determine the status of a video based on file existence.
    Returns: 'pending', 'downloaded', or 'completed'
    """
    # Check for transcription file (highest priority - ASR completed)
    if find_matching_transcription(title, transcription_files):
        return 'completed'
    
    # Check for WAV file (downloaded but not processed)
    wav_file = os.path.join(VODS_DIR, f"{title}.wav")
    if os.path.exists(wav_file):
        return 'downloaded'
    
    # No files found - pending
    return 'pending'

def should_update_status(current_status, new_status):
    """
    Determine if status should be updated.
    Always update to reflect current file state:
    - If transcription file exists, always set to 'completed'
    - Otherwise, respect unidirectional progression: pending → downloaded → completed
    - If current status is invalid, always update
    - If new status matches current, no update needed
    """
    # If current status is invalid, always update
    if current_status not in STATUS_HIERARCHY:
        return True
    
    # If statuses match, no update needed
    if current_status == new_status:
        return False
    
    # Always update to 'completed' if transcription file exists
    if new_status == 'completed':
        return True
    
    # Only update if new status is higher (unidirectional progression)
    # This ensures we can only move forward, never backward
    return STATUS_HIERARCHY[new_status] > STATUS_HIERARCHY[current_status]

def update_csv_statuses():
    """
    Read videos.csv and update status column based on file existence.
    """
    # First, get all transcription files
    transcription_files = set()
    if os.path.exists(TRANSCRIPTIONS_DIR):
        for file in os.listdir(TRANSCRIPTIONS_DIR):
            if file.endswith('_combined.txt'):
                transcription_files.add(file)
    
    print(f"Found {len(transcription_files)} transcription files")
    
    # Read all rows
    rows = []
    header = None
    
    if not os.path.exists(CSV_FILE):
        print(f"Error: CSV file not found: {CSV_FILE}")
        return
    
    with open(CSV_FILE, 'r', newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader)  # Read header
        
        # Ensure status column exists
        if 'status' not in header:
            header.append('status')
            status_col_idx = len(header) - 1
        else:
            status_col_idx = header.index('status')
        
        # Read all rows
        for row in reader:
            rows.append(row)
    
    # Update statuses
    updated_count = 0
    pending_count = 0
    downloaded_count = 0
    completed_count = 0
    
    for i, row in enumerate(rows):
        if len(row) < 2:
            continue
        
        title = row[0]
        current_status = row[status_col_idx] if len(row) > status_col_idx else 'pending'
        
        # Get new status based on file existence
        new_status = get_status_for_video(title, transcription_files)
        
        # Update if needed
        if should_update_status(current_status, new_status):
            # Ensure row has enough columns
            while len(row) <= status_col_idx:
                row.append('pending')
            
            row[status_col_idx] = new_status
            updated_count += 1
        
        # Count statuses
        final_status = row[status_col_idx] if len(row) > status_col_idx else 'pending'
        if final_status == 'pending':
            pending_count += 1
        elif final_status == 'downloaded':
            downloaded_count += 1
        elif final_status == 'completed':
            completed_count += 1
    
    # Write updated CSV
    with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    
    # Print summary
    print(f"CSV status update complete!")
    print(f"  Updated: {updated_count} rows")
    print(f"  Status breakdown:")
    print(f"    - pending: {pending_count}")
    print(f"    - downloaded: {downloaded_count}")
    print(f"    - completed: {completed_count}")
    print(f"  Total videos: {len(rows)}")

if __name__ == "__main__":
    # Ensure directories exist
    os.makedirs(VODS_DIR, exist_ok=True)
    os.makedirs(TRANSCRIPTIONS_DIR, exist_ok=True)
    
    print("Updating video statuses in videos.csv...")
    print("=" * 60)
    update_csv_statuses()

