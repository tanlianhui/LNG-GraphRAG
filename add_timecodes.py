#!/usr/bin/env python3
"""
Add cumulative start and end time codes to existing transcription files.
Re-chunks the WAV file and matches chunks to transcriptions.
"""

import sys
import os
import torchaudio
import torch
import numpy as np
from pathlib import Path
from utils import setup_path, safe_execute, log_error, handle_unicode_encoding
# Import the exact same chunking function from simple_asr.py to ensure identical logic
from simple_asr import split_audio_at_silence


def find_wav_file(transcription_file, vods_dir="./VODs"):
    """Find the corresponding WAV file for a transcription file."""
    # Get base name from transcription file (remove _combined.txt)
    base_name = os.path.basename(transcription_file)
    if base_name.endswith("_combined.txt"):
        base_name = base_name[:-13]  # Remove "_combined.txt"
    elif base_name.endswith(".txt"):
        base_name = base_name[:-4]  # Remove ".txt"
    
    print(f"Looking for WAV file matching: {base_name}")
    
    # Search in VODs directory
    vods_path = Path(vods_dir)
    if not vods_path.exists():
        print(f"Warning: VODs directory not found: {vods_dir}")
        return None
    
    # Try exact match first
    wav_file = vods_path / f"{base_name}.wav"
    if wav_file.exists():
        print(f"Found exact match: {wav_file}")
        return str(wav_file)
    
    # Try partial match (base name might be slightly different)
    # Look for WAV files that contain the key parts of the base name
    base_parts = base_name.replace("【LNG】", "").strip()
    
    for wav_path in vods_path.glob("*.wav"):
        wav_name = wav_path.stem
        # Check if key parts match
        if base_parts in wav_name or wav_name in base_parts:
            print(f"Found partial match: {wav_path}")
            return str(wav_path)
    
    # List available WAV files for debugging
    print(f"Available WAV files in {vods_dir}:")
    for wav_path in sorted(vods_path.glob("*.wav"))[:10]:  # Show first 10
        print(f"  - {wav_path.name}")
    
    return None


def parse_transcription_file(transcription_file):
    """Parse existing transcription file and extract chunks."""
    chunks = []
    
    with open(transcription_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Split by chunk markers
    parts = content.split("=== Chunk")
    
    for part in parts[1:]:  # Skip first empty part
        lines = part.strip().split("\n", 1)
        if len(lines) >= 2:
            chunk_num = lines[0].strip().split()[0]  # Get chunk number
            transcription = lines[1].strip() if len(lines) > 1 else ""
            chunks.append({
                "number": int(chunk_num),
                "text": transcription
            })
    
    print(f"Parsed {len(chunks)} chunks from transcription file")
    return chunks


def add_timecodes_to_transcription(transcription_file, wav_file=None, vods_dir="./VODs", output_file=None):
    """Add time codes to an existing transcription file."""
    if not os.path.exists(transcription_file):
        print(f"Error: Transcription file not found: {transcription_file}")
        return False
    
    # Find WAV file if not provided
    if wav_file is None:
        wav_file = find_wav_file(transcription_file, vods_dir)
        if wav_file is None:
            print(f"Error: Could not find corresponding WAV file for {transcription_file}")
            return False
    
    if not os.path.exists(wav_file):
        print(f"Error: WAV file not found: {wav_file}")
        return False
    
    print(f"Loading WAV file: {wav_file}")
    try:
        waveform, sample_rate = torchaudio.load(wav_file)
        print(f"Audio shape: {waveform.shape}, sample rate: {sample_rate}")
    except Exception as e:
        print(f"Error loading WAV file: {e}")
        # Try with librosa as fallback
        try:
            import librosa
            audio_data, sr = librosa.load(wav_file, sr=None)
            waveform = torch.tensor(audio_data).unsqueeze(0)
            sample_rate = sr
            print(f"Loaded with librosa - Audio shape: {waveform.shape}, sample rate: {sample_rate}")
        except Exception as e2:
            print(f"Error with librosa fallback: {e2}")
            return False
    
    # Re-chunk the audio
    print("Re-chunking audio...")
    audio_chunks, sample_rate, chunk_times = split_audio_at_silence(waveform, sample_rate)
    print(f"Audio split into {len(audio_chunks)} chunks")
    
    # Parse existing transcription
    print("Parsing existing transcription...")
    transcription_chunks = parse_transcription_file(transcription_file)
    
    # Check if chunk counts match
    if len(audio_chunks) != len(transcription_chunks):
        print(f"Warning: Chunk count mismatch!")
        print(f"  Audio chunks: {len(audio_chunks)}")
        print(f"  Transcription chunks: {len(transcription_chunks)}")
        print(f"  Using minimum count: {min(len(audio_chunks), len(transcription_chunks))}")
        min_count = min(len(audio_chunks), len(transcription_chunks))
    else:
        min_count = len(audio_chunks)
    
    # Create output file name
    if output_file is None:
        output_file = transcription_file  # Overwrite original
    
    # Write updated transcription with time codes
    print(f"Writing updated transcription to: {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        for i in range(min_count):
            start_time, end_time = chunk_times[i]
            chunk_text = transcription_chunks[i]["text"]
            f.write(f"=== Chunk {i+1} [{start_time:.2f}s - {end_time:.2f}s] ===\n")
            f.write(chunk_text)
            f.write("\n\n")
    
    print(f"Successfully added time codes to {output_file}")
    return True


def process_all_transcriptions(transcriptions_dir="./transcriptions", vods_dir="./VODs"):
    """Process all transcription files in the directory."""
    transcriptions_path = Path(transcriptions_dir)
    if not transcriptions_path.exists():
        print(f"Error: Transcriptions directory not found: {transcriptions_dir}")
        return False
    
    transcription_files = list(transcriptions_path.glob("*_combined.txt"))
    
    if not transcription_files:
        print(f"No transcription files found in {transcriptions_dir}")
        return False
    
    print(f"Found {len(transcription_files)} transcription files")
    
    success_count = 0
    for transcription_file in transcription_files:
        print(f"\n{'='*60}")
        print(f"Processing: {transcription_file.name}")
        print(f"{'='*60}")
        
        if add_timecodes_to_transcription(str(transcription_file), vods_dir=vods_dir):
            success_count += 1
        else:
            print(f"Failed to process: {transcription_file.name}")
    
    print(f"\n{'='*60}")
    print(f"Processed {success_count}/{len(transcription_files)} files successfully")
    print(f"{'='*60}")
    
    return success_count == len(transcription_files)


def main():
    # Set up path and encoding
    setup_path()
    handle_unicode_encoding()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python add_timecodes.py <transcription_file> [wav_file]")
        print("  python add_timecodes.py --all [transcriptions_dir] [vods_dir]")
        print("\nExamples:")
        print("  python add_timecodes.py transcriptions/【LNG】2025OCT 10月大家在幹嘛啊_combined.txt")
        print("  python add_timecodes.py --all")
        print("  python add_timecodes.py --all ./transcriptions ./VODs")
        sys.exit(1)
    
    if sys.argv[1] == "--all":
        # Process all transcription files
        transcriptions_dir = sys.argv[2] if len(sys.argv) > 2 else "./transcriptions"
        vods_dir = sys.argv[3] if len(sys.argv) > 3 else "./VODs"
        
        success, result, error = safe_execute(process_all_transcriptions, transcriptions_dir, vods_dir)
        
        if success:
            print("Success!")
        else:
            print(f"Error: {error}")
            sys.exit(1)
    else:
        # Process single file
        transcription_file = sys.argv[1]
        wav_file = sys.argv[2] if len(sys.argv) > 2 else None
        
        success, result, error = safe_execute(add_timecodes_to_transcription, transcription_file, wav_file)
        
        if success:
            print("Success!")
        else:
            print(f"Error: {error}")
            sys.exit(1)


if __name__ == "__main__":
    main()

