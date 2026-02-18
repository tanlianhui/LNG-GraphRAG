#!/usr/bin/env python3
"""
Simple ASR processing for a single audio file
"""

import sys
import os
import torchaudio
import torch
import numpy as np
import shutil
import tempfile
import psutil
import asyncio
import concurrent.futures
from pathlib import Path
from transformers import WhisperProcessor, WhisperForConditionalGeneration
from utils import setup_path, safe_execute, log_error, handle_unicode_encoding

def split_audio_at_silence(waveform, sample_rate, min_duration=60, max_duration=300, silence_threshold=0.01, min_silence_duration=1.0):
    """Split audio at silence points with duration constraints."""
    # Convert to mono if stereo
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0)
    waveform = waveform.squeeze().numpy()
    
    # Resample to 16kHz if needed
    if sample_rate != 16_000:
        resampler = torchaudio.transforms.Resample(sample_rate, 16_000)
        waveform = resampler(torch.tensor(waveform)).numpy()
        sample_rate = 16_000
    
    # Find silence regions
    silence_samples = np.abs(waveform) < silence_threshold
    min_silence_samples = int(min_silence_duration * sample_rate)
    
    # Find silence regions longer than min_silence_duration
    silence_regions = []
    in_silence = False
    silence_start = 0
    
    for i, is_silent in enumerate(silence_samples):
        if is_silent and not in_silence:
            silence_start = i
            in_silence = True
        elif not is_silent and in_silence:
            if i - silence_start >= min_silence_samples:
                silence_regions.append((silence_start, i))
            in_silence = False
    
    # Split audio at silence points
    chunks = []
    chunk_times = []  # Store (start_time, end_time) for each chunk
    current_start = 0
    min_samples = int(min_duration * sample_rate)
    max_samples = int(max_duration * sample_rate)
    
    for silence_start, silence_end in silence_regions:
        chunk_duration = (silence_start - current_start) / sample_rate
        
        # If chunk is too short, continue to next silence
        if chunk_duration < min_duration:
            continue
            
        # If chunk is too long, force split at max_duration
        if chunk_duration > max_duration:
            # Split current chunk at max_duration
            end_sample = current_start + max_samples
            start_time = current_start / sample_rate
            end_time = end_sample / sample_rate
            chunks.append(waveform[current_start:end_sample])
            chunk_times.append((start_time, end_time))
            current_start = end_sample
        else:
            start_time = current_start / sample_rate
            end_time = silence_start / sample_rate
            chunks.append(waveform[current_start:silence_start])
            chunk_times.append((start_time, end_time))
            current_start = silence_end
    
    # Add remaining audio if any
    if current_start < len(waveform):
        remaining_duration = (len(waveform) - current_start) / sample_rate
        if remaining_duration >= min_duration:
            start_time = current_start / sample_rate
            end_time = len(waveform) / sample_rate
            chunks.append(waveform[current_start:])
            chunk_times.append((start_time, end_time))
    
    return chunks, sample_rate, chunk_times

def get_emptiest_drive():
    """Find the drive with the most free space"""
    try:
        drives = []
        
        # Get all available drives
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                free_gb = usage.free / (1024**3)  # Convert to GB
                drives.append({
                    'mountpoint': partition.mountpoint,
                    'free_gb': free_gb,
                    'total_gb': usage.total / (1024**3)
                })
            except (PermissionError, OSError):
                continue
        
        if not drives:
            return None
        
        # Sort by free space (descending)
        drives.sort(key=lambda x: x['free_gb'], reverse=True)
        
        print(f"Available drives:")
        for drive in drives:
            print(f"  {drive['mountpoint']}: {drive['free_gb']:.1f} GB free / {drive['total_gb']:.1f} GB total")
        
        best_drive = drives[0]
        print(f"Using drive with most free space: {best_drive['mountpoint']} ({best_drive['free_gb']:.1f} GB free)")
        
        return best_drive['mountpoint']
        
    except Exception as e:
        print(f"Error checking drives: {e}")
        return None

def create_safe_copy(audio_file_path):
    """Create a safe copy of the audio file with ASCII filename to avoid Unicode issues"""
    # Find the emptiest drive
    best_drive = get_emptiest_drive()
    
    # Try drives in order of preference
    drives_to_try = []
    if best_drive:
        drives_to_try.append(best_drive)
    
    # Add fallback drives
    drives_to_try.extend(["E:\\", "D:\\", "C:\\"])
    
    for drive in drives_to_try:
        try:
            print(f"Trying to create safe copy on {drive}")
            temp_dir = tempfile.mkdtemp(dir=drive)
            safe_filename = "temp_audio.wav"
            safe_path = os.path.join(temp_dir, safe_filename)
            
            # Copy the file
            shutil.copy2(audio_file_path, safe_path)
            
            print(f"Created safe copy: {safe_path}")
            return safe_path, temp_dir
            
        except Exception as e:
            print(f"Error creating safe copy on {drive}: {e}")
            continue
    
    # Final fallback to current directory
    try:
        print("Trying fallback to current directory")
        temp_dir = tempfile.mkdtemp()
        safe_filename = "temp_audio.wav"
        safe_path = os.path.join(temp_dir, safe_filename)
        
        # Copy the file
        shutil.copy2(audio_file_path, safe_path)
        
        print(f"Created safe copy (final fallback): {safe_path}")
        return safe_path, temp_dir
        
    except Exception as e:
        print(f"Error creating safe copy (final fallback): {e}")
        return None, None

def cleanup_temp_file(temp_path, temp_dir):
    """Clean up temporary file and directory"""
    try:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
        print(f"Cleaned up temporary files")
    except Exception as e:
        print(f"Warning: Could not clean up temporary files: {e}")

def process_chunk_async(chunk_data, processor, model, device, chunk_index, base_name, output_dir, start_time, end_time):
    """Process a single audio chunk asynchronously"""
    chunk, sample_rate = chunk_data
    duration = len(chunk) / sample_rate
    print(f"Processing chunk {chunk_index+1} (duration: {duration:.2f}s, time: {start_time:.2f}s - {end_time:.2f}s)")
    
    try:
        # Process with model
        with torch.no_grad():
            # Get features
            inputs = processor(chunk, sampling_rate=16000, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            # Generate
            generated_ids = model.generate(
                inputs["input_features"],
                max_length=448,
                num_beams=1,
                do_sample=False,
                temperature=None,
            )
            
            # Decode
            transcription = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        
        print(f"Chunk {chunk_index+1} transcription: {transcription[:100]}...")
        
        # Save individual chunk transcription with time info
        chunk_file = f"{output_dir}/{base_name}_chunk_{chunk_index+1:03d}.txt"
        with open(chunk_file, "w", encoding="utf-8") as f:
            f.write(f"[{start_time:.2f}s - {end_time:.2f}s]\n")
            f.write(transcription)
        print(f"Saved chunk {chunk_index+1} to: {chunk_file}")
        
        return transcription, chunk_index, start_time, end_time
        
    except Exception as e:
        error_msg = f"[Error in chunk {chunk_index+1}: {e}]"
        print(f"Error processing chunk {chunk_index+1}: {e}")
        return error_msg, chunk_index, start_time, end_time

def process_audio_file(audio_file_path, keep_audio=False):
    """Process a single audio file with ASR, saving after each chunk.
    If keep_audio=True, do not delete the source WAV after success (e.g. for batch from VODs).
    """
    print("Loading ASR model...")
    
    # Load model and processor
    processor = WhisperProcessor.from_pretrained("MediaTek-Research/Breeze-ASR-25")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    
    model = WhisperForConditionalGeneration.from_pretrained("MediaTek-Research/Breeze-ASR-25").to(device).eval()
    
    print(f"Loading audio file: {audio_file_path}")
    
    # Check if file exists and is accessible
    if not os.path.exists(audio_file_path):
        print(f"Error: File not found: {audio_file_path}")
        return False
    
    # Create safe copy to avoid Unicode issues
    safe_path, temp_dir = create_safe_copy(audio_file_path)
    if not safe_path:
        print("Error: Could not create safe copy of file")
        return False
    
    try:
        # Try to load the safe copy
        waveform, sample_rate = torchaudio.load(safe_path)
        print(f"Audio shape: {waveform.shape}, sample rate: {sample_rate}")
    except Exception as e:
        print(f"Error loading safe copy: {e}")
        print("Trying alternative loading method...")
        
        # Try with librosa as fallback
        try:
            import librosa
            audio_data, sr = librosa.load(safe_path, sr=None)
            # Convert to torch tensor
            waveform = torch.tensor(audio_data).unsqueeze(0)
            sample_rate = sr
            print(f"Loaded with librosa - Audio shape: {waveform.shape}, sample rate: {sample_rate}")
        except Exception as e2:
            print(f"Error with librosa fallback: {e2}")
            cleanup_temp_file(safe_path, temp_dir)
            return False
    
    # Split audio into chunks
    print("Splitting audio into chunks...")
    audio_chunks, sample_rate, chunk_times = split_audio_at_silence(waveform, sample_rate)
    print(f"Audio split into {len(audio_chunks)} chunks")
    
    # Create output directory
    output_dir = "./transcriptions"
    os.makedirs(output_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(audio_file_path))[0]
    all_transcriptions = []
    chunk_time_info = chunk_times.copy()  # Initialize with chunk times
    
    try:
        # Process chunks asynchronously using ThreadPoolExecutor
        print(f"Processing {len(audio_chunks)} chunks asynchronously...")
        
        # Prepare chunk data for async processing
        chunk_data_list = [(chunk, sample_rate) for chunk in audio_chunks]
        
        # Use ThreadPoolExecutor for async processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all chunk processing tasks
            future_to_index = {
                executor.submit(
                    process_chunk_async, 
                    chunk_data, 
                    processor, 
                    model, 
                    device, 
                    i, 
                    base_name, 
                    output_dir,
                    chunk_times[i][0],  # start_time
                    chunk_times[i][1]   # end_time
                ): i 
                for i, chunk_data in enumerate(chunk_data_list)
            }
            
            # Collect results as they complete
            results = [None] * len(audio_chunks)
            chunk_time_info = [None] * len(audio_chunks)
            completed_chunks = 0
            
            for future in concurrent.futures.as_completed(future_to_index):
                try:
                    transcription, chunk_index, start_time, end_time = future.result()
                    results[chunk_index] = transcription
                    chunk_time_info[chunk_index] = (start_time, end_time)
                    completed_chunks += 1
                    print(f"Completed chunk {chunk_index+1}/{len(audio_chunks)} ({completed_chunks}/{len(audio_chunks)} total completed)")
                except Exception as e:
                    chunk_index = future_to_index[future]
                    error_msg = f"[Error in chunk {chunk_index+1}: {e}]"
                    results[chunk_index] = error_msg
                    chunk_time_info[chunk_index] = chunk_times[chunk_index]
                    completed_chunks += 1
                    print(f"Error in chunk {chunk_index+1}: {e} ({completed_chunks}/{len(audio_chunks)} total completed)")
        
        # Collect all transcriptions in order
        all_transcriptions = results
        
    except Exception as e:
        print(f"Error during processing: {e}")
        all_transcriptions = [f"[Processing error: {e}]"] * len(audio_chunks)
        # chunk_time_info already initialized before try block
    finally:
        # Always clean up temporary file
        cleanup_temp_file(safe_path, temp_dir)
    
    # Save combined transcription
    combined_file = f"{output_dir}/{base_name}_combined.txt"
    with open(combined_file, "w", encoding="utf-8") as f:
        for i, transcription in enumerate(all_transcriptions):
            start_time, end_time = chunk_time_info[i]
            f.write(f"=== Chunk {i+1} [{start_time:.2f}s - {end_time:.2f}s] ===\n")
            f.write(transcription)
            f.write("\n\n")
    
    print(f"All transcriptions saved to: {combined_file}")
    
    # Clean up individual chunk files after combined transcription is saved
    chunk_files_cleaned = 0
    for i in range(len(audio_chunks)):
        chunk_file = f"{output_dir}/{base_name}_chunk_{i+1:03d}.txt"
        if os.path.exists(chunk_file):
            try:
                os.remove(chunk_file)
                chunk_files_cleaned += 1
                print(f"Cleaned up chunk file: {chunk_file}")
            except Exception as e:
                print(f"Warning: Could not delete chunk file {chunk_file}: {e}")
    
    if chunk_files_cleaned > 0:
        print(f"Cleaned up {chunk_files_cleaned} temporary chunk files")
    
    # Delete original audio file after successful transcription (unless keep_audio=True)
    if not keep_audio and os.path.exists(combined_file):
        try:
            if os.path.exists(audio_file_path):
                os.remove(audio_file_path)
                print(f"Deleted original audio file: {audio_file_path}")
            else:
                print(f"Original audio file not found: {audio_file_path}")
        except Exception as e:
            print(f"Warning: Could not delete original audio file {audio_file_path}: {e}")
    elif keep_audio and os.path.exists(combined_file):
        print(f"Kept original audio file (--keep-audio): {audio_file_path}")
    elif not os.path.exists(combined_file):
        print(f"Warning: Combined transcription file not found, keeping original audio file: {audio_file_path}")
    
    print("Processing completed!")
    
    return True

def main():
    # Set up path and encoding
    setup_path()
    handle_unicode_encoding()
    
    if len(sys.argv) != 2:
        print("Usage: python simple_asr.py <audio_file_path>")
        sys.exit(1)
    
    audio_file_path = sys.argv[1]
    
    if not os.path.exists(audio_file_path):
        print(f"File not found: {audio_file_path}")
        sys.exit(1)
    
    success, result, error = safe_execute(process_audio_file, audio_file_path)
    
    if success:
        print("Success!")
    else:
        print(f"Error: {error}")
        sys.exit(1)

if __name__ == "__main__":
    main()
