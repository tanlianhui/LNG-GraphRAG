import torchaudio
import torch
import os
import numpy as np
import asyncio
import aiofiles
import csv
import sys
from concurrent.futures import ThreadPoolExecutor
from transformers import WhisperProcessor, WhisperForConditionalGeneration, AutomaticSpeechRecognitionPipeline
from VODs.download_from_youtube import download_from_youtube

def split_audio_at_silence(waveform, sample_rate, min_duration=60, max_duration=300, silence_threshold=0.01, min_silence_duration=1.0):
    """
    Split audio at silence points with duration constraints.
    
    Args:
        waveform: Audio waveform
        sample_rate: Sample rate of the audio
        min_duration: Minimum duration in seconds (default: 60s = 1 minute)
        max_duration: Maximum duration in seconds (default: 300s = 5 minutes)
        silence_threshold: Threshold for silence detection
        min_silence_duration: Minimum silence duration to split at (seconds)
    
    Returns:
        List of audio chunks as numpy arrays
    """
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
            chunks.append(waveform[current_start:end_sample])
            current_start = end_sample
        else:
            chunks.append(waveform[current_start:silence_start])
            current_start = silence_end
    
    # Add remaining audio if any
    if current_start < len(waveform):
        remaining_duration = (len(waveform) - current_start) / sample_rate
        if remaining_duration >= min_duration:
            chunks.append(waveform[current_start:])
    
    return chunks, sample_rate

# Load Model (do this once at startup)
def load_asr_model():
    """Load the ASR model and pipeline once at startup"""
    try:
        print("Loading processor...")
        processor = WhisperProcessor.from_pretrained("MediaTek-Research/Breeze-ASR-25")
        
        # Check if CUDA is available, otherwise use CPU
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {device}")
        
        print("Loading model...")
        model = WhisperForConditionalGeneration.from_pretrained("MediaTek-Research/Breeze-ASR-25").to(device).eval()
        print("Model loaded successfully!")
        
        # Build Pipeline
        print("Building ASR pipeline...")
        asr_pipeline = AutomaticSpeechRecognitionPipeline(
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            chunk_length_s=0
        )
        print("Pipeline built successfully!")
        
        return asr_pipeline
        
    except Exception as e:
        print(f"Error loading model: {e}")
        return None

# Async processing functions
async def process_chunk_async(chunk, chunk_index, asr_pipeline, sample_rate, executor):
    """Process a single audio chunk asynchronously"""
    def process_chunk():
        try:
            output = asr_pipeline(chunk, return_timestamps=True)
            return output["text"].strip()
        except Exception as e:
            return f"[Error in chunk {chunk_index+1}: {e}]"
    
    # Run the processing in a thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, process_chunk)
    
    print(f"Chunk {chunk_index+1} completed: {len(result)} characters")
    return result

async def process_all_chunks_async(audio_chunks, asr_pipeline, sample_rate, max_concurrent=3):
    """Process all audio chunks concurrently with limited concurrency"""
    print(f"Starting async transcription with max {max_concurrent} concurrent processes...")
    
    # Create thread pool executor for CPU-bound tasks
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        # Create tasks for all chunks
        tasks = []
        for i, chunk in enumerate(audio_chunks):
            print(f"Queuing chunk {i+1}/{len(audio_chunks)} (duration: {len(chunk) / sample_rate:.2f}s)")
            task = process_chunk_async(chunk, i, asr_pipeline, sample_rate, executor)
            tasks.append(task)
        
        # Process all chunks concurrently
        print(f"Processing {len(tasks)} chunks concurrently...")
        all_transcriptions = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        processed_transcriptions = []
        for i, result in enumerate(all_transcriptions):
            if isinstance(result, Exception):
                processed_transcriptions.append(f"[Error in chunk {i+1}: {result}]")
                print(f"Chunk {i+1} failed: {result}")
            else:
                processed_transcriptions.append(result)
                print(f"Chunk {i+1} completed successfully")
        
        return processed_transcriptions

async def save_transcription_async(transcriptions, output_path):
    """Save transcriptions to file asynchronously"""
    content = "\n".join(transcriptions)
    async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
        await f.write(content)
    print(f"Transcriptions saved to {output_path}")

def process_single_video(video_url, video_title, asr_pipeline, output_dir="./transcriptions"):
    """Process a single video: download, transcribe, save, and cleanup"""
    print(f"\n🎬 Processing: {video_title}")
    print(f"📥 Downloading from: {video_url}")
    
    # Step 1: Download video
    try:
        success = download_from_youtube(video_url)
        if not success:
            print(f"❌ Failed to download: {video_title}")
            return False
        print(f"✅ Successfully downloaded: {video_title}")
    except Exception as e:
        print(f"❌ Download error for {video_title}: {e}")
        return False
    
    # Step 2: Find the downloaded audio file
    expected_filename = f"./VODs/{video_title}.wav"
    if not os.path.exists(expected_filename):
        print(f"❌ Downloaded file not found: {expected_filename}")
        return False
    
    # Step 3: Load and process audio
    try:
        print(f"🎵 Loading audio: {expected_filename}")
        waveform, sample_rate = torchaudio.load(expected_filename)
        print(f"Loaded audio: {waveform.shape}, sample rate: {sample_rate}")
        
        # Split audio at silence points
        print("Splitting audio at silence points...")
        audio_chunks, sample_rate = split_audio_at_silence(waveform, sample_rate)
        print(f"Audio split into {len(audio_chunks)} chunks")
        for i, chunk in enumerate(audio_chunks):
            duration = len(chunk) / sample_rate
            print(f"Chunk {i+1}: {duration:.2f} seconds")
        
    except Exception as e:
        print(f"❌ Error loading audio file: {e}")
        # Clean up the downloaded file
        if os.path.exists(expected_filename):
            os.remove(expected_filename)
        return False
    
    # Step 4: Transcribe audio
    try:
        print("🎤 Starting transcription...")
        
        # Process all chunks concurrently
        all_transcriptions = asyncio.run(process_all_chunks_async(
            audio_chunks, asr_pipeline, sample_rate, max_concurrent=3
        ))
        
        # Save results
        os.makedirs(output_dir, exist_ok=True)
        output_path = f"{output_dir}/{video_title}.txt"
        asyncio.run(save_transcription_async(all_transcriptions, output_path))
        
        print(f"✅ Transcription completed! {len(all_transcriptions)} chunks processed.")
        print(f"📝 Results saved to: {output_path}")
        
    except Exception as e:
        print(f"❌ Error during transcription: {e}")
        # Clean up the downloaded file
        if os.path.exists(expected_filename):
            os.remove(expected_filename)
        return False
    
    # Step 5: Clean up downloaded file
    try:
        if os.path.exists(expected_filename):
            os.remove(expected_filename)
            print(f"🗑️  Cleaned up: {expected_filename}")
    except Exception as e:
        print(f"⚠️  Warning: Could not delete {expected_filename}: {e}")
    
    return True

def update_csv_status(video_title, status, csv_file="./VODs/videos.csv"):
    """Update the CSV file with the completion status of a video"""
    try:
        # Read existing CSV
        rows = []
        with open(csv_file, 'r', newline='', encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2 and row[0] == video_title:
                    # Update the status column
                    if len(row) >= 3:
                        row[2] = status
                    else:
                        row.append(status)
                rows.append(row)
        
        # Write updated CSV
        with open(csv_file, 'w', newline='', encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        print(f"📝 Updated CSV status for {video_title}: {status}")
    except Exception as e:
        print(f"⚠️  Could not update CSV for {video_title}: {e}")

def process_videos_from_csv(csv_file="./VODs/videos.csv", start_index=0, max_videos=None):
    """Process videos from CSV file one at a time"""
    
    # Load ASR model once at startup
    print("🚀 Initializing ASR model...")
    asr_pipeline = load_asr_model()
    if asr_pipeline is None:
        print("❌ Failed to load ASR model. Exiting.")
        return
    
    # Read CSV file
    try:
        with open(csv_file, 'r', newline='', encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            videos = list(reader)
    except Exception as e:
        print(f"❌ Error reading CSV file: {e}")
        return
    
    # Skip header row
    if videos and videos[0][0] == "title":
        videos = videos[1:]
    
    # Filter pending videos
    pending_videos = [v for v in videos if len(v) >= 3 and v[2] == "pending"]
    
    if not pending_videos:
        print("✅ No pending videos found in CSV.")
        return
    
    print(f"📋 Found {len(pending_videos)} pending videos")
    
    # Process videos
    processed_count = 0
    failed_count = 0
    
    for i, video in enumerate(pending_videos[start_index:], start_index):
        if max_videos and processed_count >= max_videos:
            print(f"🛑 Reached maximum video limit: {max_videos}")
            break
            
        video_title = video[0]
        video_url = video[1]
        
        print(f"\n{'='*60}")
        print(f"📹 Video {i+1}/{len(pending_videos)}: {video_title}")
        print(f"{'='*60}")
        
        try:
            success = process_single_video(video_url, video_title, asr_pipeline)
            
            if success:
                processed_count += 1
                update_csv_status(video_title, "completed")
                print(f"✅ Successfully processed: {video_title}")
            else:
                failed_count += 1
                update_csv_status(video_title, "failed")
                print(f"❌ Failed to process: {video_title}")
                
        except KeyboardInterrupt:
            print(f"\n⚠️  Processing interrupted by user")
            print(f"📊 Progress: {processed_count} completed, {failed_count} failed")
            break
        except Exception as e:
            failed_count += 1
            update_csv_status(video_title, "failed")
            print(f"❌ Unexpected error processing {video_title}: {e}")
    
    print(f"\n🎉 Batch processing completed!")
    print(f"📊 Final results: {processed_count} completed, {failed_count} failed")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Process videos from CSV with ASR")
    parser.add_argument("--csv", default="./VODs/videos.csv", help="CSV file path")
    parser.add_argument("--start", type=int, default=0, help="Start index")
    parser.add_argument("--max", type=int, help="Maximum number of videos to process")
    
    args = parser.parse_args()
    
    try:
        process_videos_from_csv(args.csv, args.start, args.max)
    except KeyboardInterrupt:
        print("\n⚠️  Processing interrupted by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
