import torchaudio
import torch
import os
import numpy as np
import asyncio
import aiofiles
from concurrent.futures import ThreadPoolExecutor
from transformers import WhisperProcessor, WhisperForConditionalGeneration, AutomaticSpeechRecognitionPipeline

# 1. Load audio
audio_path = "./VODs/【LNG】2025OCT 10月大家在幹嘛啊.wav"

# Check if audio file exists
if not os.path.exists(audio_path):
    print(f"Error: Audio file not found at {audio_path}")
    exit(1)

try:
    waveform, sample_rate = torchaudio.load(audio_path)
    print(f"Loaded audio: {waveform.shape}, sample rate: {sample_rate}")
except Exception as e:
    print(f"Error loading audio file: {e}")
    exit(1)          

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

# 2. Preprocess and split audio
print("Splitting audio at silence points...")
audio_chunks, sample_rate = split_audio_at_silence(waveform, sample_rate)
print(f"Audio split into {len(audio_chunks)} chunks")
for i, chunk in enumerate(audio_chunks):
    duration = len(chunk) / sample_rate
    print(f"Chunk {i+1}: {duration:.2f} seconds")

# 3. Load Model
try:
    print("Loading processor...")
    processor = WhisperProcessor.from_pretrained("MediaTek-Research/Breeze-ASR-25")
    
    # Check if CUDA is available, otherwise use CPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    
    print("Loading model...")
    model = WhisperForConditionalGeneration.from_pretrained("MediaTek-Research/Breeze-ASR-25").to(device).eval()
    print("Model loaded successfully!")
    
except Exception as e:
    print(f"Error loading model: {e}")
    exit(1)

# 4. Build Pipeline
try:
    print("Building ASR pipeline...")
    asr_pipeline = AutomaticSpeechRecognitionPipeline(
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        chunk_length_s=0
    )
    print("Pipeline built successfully!")
except Exception as e:
    print(f"Error building pipeline: {e}")
    exit(1)

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

# 6. Async Inference - Process all chunks concurrently
async def main_async():
    try:
        print("Starting async transcription...")
        
        # Process all chunks concurrently
        all_transcriptions = await process_all_chunks_async(
            audio_chunks, asr_pipeline, sample_rate, max_concurrent=3
        )
        
        # Save results
        output_path = f"./transcriptions/{audio_path.split('/')[-1].split('.')[0]}.txt"
        os.makedirs("./transcriptions", exist_ok=True)
        await save_transcription_async(all_transcriptions, output_path)
        
        print(f"\n✅ Transcription completed! {len(all_transcriptions)} chunks processed.")
        print(f"📝 Results saved to: {output_path}")
        
    except Exception as e:
        print(f"Error during async transcription: {e}")
        return False
    
    return True

# Run the async main function
if __name__ == "__main__":
    try:
        result = asyncio.run(main_async())
        if not result:
            exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  Transcription interrupted by user")
        exit(1)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        exit(1)
