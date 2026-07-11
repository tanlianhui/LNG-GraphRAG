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
from pathlib import Path
from transformers import WhisperProcessor, WhisperForConditionalGeneration
from utils import setup_path, safe_execute, log_error, handle_unicode_encoding

def split_audio_at_silence(waveform, sample_rate, min_duration=10, max_duration=30, silence_threshold=0.01, min_silence_duration=1.0):
    """Split audio by silence only. Each returned chunk is one continuous segment (no mid-segment cuts).
    Duration constraints: segments shorter than min_duration are skipped; segments longer than max_duration
    are split at max_duration. Each chunk's full timespan is passed to ASR for transcription."""
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

    # Hard cap: guarantee NO chunk exceeds max_duration. Silence detection can
    # leave huge segments (e.g. game streams with constant audio = zero silence →
    # the whole multi-hour file as one chunk), which OOMs the GPU. Sub-split any
    # oversized segment into <=max_duration pieces.
    capped_chunks, capped_times = [], []
    for data, (cs, ce) in zip(chunks, chunk_times):
        if len(data) <= max_samples:
            capped_chunks.append(data)
            capped_times.append((cs, ce))
            continue
        off = 0
        while off < len(data):
            piece = data[off:off + max_samples]
            ps = cs + off / sample_rate
            pe = cs + min(off + max_samples, len(data)) / sample_rate
            capped_chunks.append(piece)
            capped_times.append((ps, pe))
            off += max_samples

    return capped_chunks, sample_rate, capped_times

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

def process_chunk(chunk_data, processor, model, device, chunk_index, base_name, output_dir, start_time, end_time, prompt_ids=None, num_beams=5, self_consistency=False):
    """Process one audio chunk sequentially. Falls back to CPU on CUDA error.

    num_beams: beam-search width for the primary transcription (>1 = beam search,
        markedly fewer acoustic errors than greedy at some speed cost).
    self_consistency: if True, ALSO produce a greedy candidate. The two candidates
        (beam + greedy) are returned so the LLM post-correction step can reconcile
        them; divergence between them flags low-confidence spans.

    Returns (transcription, chunk_index, start_time, end_time, alt_candidate).
    alt_candidate is the greedy text when self_consistency is on, else None.
    """
    chunk, sample_rate = chunk_data
    duration = len(chunk) / sample_rate
    print(f"Processing chunk {chunk_index+1} (duration: {duration:.2f}s, time: {start_time:.2f}s - {end_time:.2f}s)")

    # Validate chunk before sending to GPU
    if len(chunk) == 0 or np.all(chunk == 0) or np.any(np.isnan(chunk)):
        error_msg = f"[Error in chunk {chunk_index+1}: invalid audio (empty/silent/NaN)]"
        print(error_msg)
        return error_msg, chunk_index, start_time, end_time, None

    def _infer(target_device, mdl, beams):
        with torch.no_grad():
            inputs = processor(chunk, sampling_rate=16000, return_tensors="pt")
            inputs = {k: v.to(target_device) for k, v in inputs.items()}
            prompt_len = prompt_ids.shape[-1] if prompt_ids is not None else 0
            # Whisper's decoder is capped at max_target_positions (448) INCLUDING the
            # prompt + special tokens. Requesting more indexes past the positional
            # embedding table → CUDA device-side assert. Budget new tokens under 448.
            max_new = max(1, 448 - prompt_len - 8)  # 8 = margin for special tokens
            generate_kwargs = dict(
                max_new_tokens=max_new,
                num_beams=beams,
                do_sample=False,
                temperature=None,
            )
            if prompt_ids is not None:
                # prompt_ids must be on same device
                generate_kwargs["prompt_ids"] = prompt_ids.to(target_device)
            generated_ids = mdl.generate(inputs["input_features"], **generate_kwargs)
            return processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

    def _infer_safe(beams):
        """Run inference with CUDA→CPU fallback. Raises on unrecoverable error."""
        try:
            return _infer(device, model, beams)
        except RuntimeError as e:
            err_str = str(e)
            if "CUDA" in err_str or "cuda" in err_str:
                print(f"Chunk {chunk_index+1}: CUDA error — clearing cache and retrying on CPU: {err_str[:120]}")
                if device != "cpu":
                    torch.cuda.empty_cache()
                cpu_model = model.to("cpu")
                try:
                    out = _infer("cpu", cpu_model, beams)
                    print(f"Chunk {chunk_index+1}: CPU fallback succeeded")
                    return out
                finally:
                    model.to(device)  # restore device for next chunks
            raise

    try:
        transcription = _infer_safe(num_beams)
    except Exception as e:
        error_msg = f"[Error in chunk {chunk_index+1}: {e}]"
        print(error_msg)
        return error_msg, chunk_index, start_time, end_time, None

    alt_candidate = None
    if self_consistency:
        try:
            alt = _infer_safe(1)  # greedy second opinion
            if alt.strip() and alt.strip() != transcription.strip():
                alt_candidate = alt
        except Exception as e:
            print(f"Chunk {chunk_index+1}: self-consistency greedy pass failed ({e}) — using beam result only")

    print(f"Chunk {chunk_index+1} transcription: {transcription[:100]}...")

    chunk_file = f"{output_dir}/{base_name}_chunk_{chunk_index+1:03d}.txt"
    with open(chunk_file, "w", encoding="utf-8") as f:
        f.write(f"[{start_time:.2f}s - {end_time:.2f}s]\n")
        f.write(transcription)

    return transcription, chunk_index, start_time, end_time, alt_candidate

def process_audio_file(audio_file_path, keep_audio=True, output_suffix='_combined'):
    """Process a single audio file with ASR, saving after each chunk.
    WAV is kept by default; pass keep_audio=False only if you explicitly want deletion.
    output_suffix controls the output filename (default: _combined → <title>_combined.txt).

    Decoding is controlled by env vars (so batch runs stay uniform):
      ASR_NUM_BEAMS        beam width for primary transcription (default 5)
      ASR_SELF_CONSISTENCY 1 = also emit a greedy candidate per chunk into a
                           <title>_candidates.txt sidecar for LLM reconciliation
    """
    num_beams = max(1, int(os.getenv("ASR_NUM_BEAMS", "5")))
    self_consistency = os.getenv("ASR_SELF_CONSISTENCY", "0").strip().lower() in ("1", "true", "yes")
    print(f"Decoding: num_beams={num_beams}, self_consistency={self_consistency}")

    print("Loading ASR model...")

    # Load model and processor
    processor = WhisperProcessor.from_pretrained("MediaTek-Research/Breeze-ASR-25")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    model = WhisperForConditionalGeneration.from_pretrained("MediaTek-Research/Breeze-ASR-25").to(device).eval()

    # Build keyword initial_prompt for vocabulary biasing
    try:
        from asr_keywords import INITIAL_PROMPT
        prompt_ids = processor.get_prompt_ids(INITIAL_PROMPT, return_tensors="pt").to(device)
        print(f"Keyword prompt loaded ({prompt_ids.shape[-1]} tokens)")
    except Exception as e:
        print(f"Warning: could not load keyword prompt ({e}), proceeding without it")
        prompt_ids = None
    
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
    
    # Split audio by silence only; each chunk is the full segment for that timespan
    print("Splitting audio by silence...")
    audio_chunks, sample_rate, chunk_times = split_audio_at_silence(waveform, sample_rate)
    print(f"Audio split into {len(audio_chunks)} chunks (each chunk = full segment, no partial cuts)")
    
    # Create output directory
    output_dir = "./transcriptions"
    os.makedirs(output_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(audio_file_path))[0]
    all_transcriptions = []
    chunk_time_info = chunk_times.copy()  # Initialize with chunk times
    
    try:
        # Process chunks sequentially — CUDA is single-device serial; threads sharing
        # one model cause race conditions and poison the CUDA context on error.
        print(f"Processing {len(audio_chunks)} chunks sequentially...")

        results = [None] * len(audio_chunks)
        alt_results = [None] * len(audio_chunks)
        chunk_time_info = [None] * len(audio_chunks)

        for i, chunk in enumerate(audio_chunks):
            transcription, chunk_index, start_time, end_time, alt_candidate = process_chunk(
                (chunk, sample_rate),
                processor, model, device,
                i, base_name, output_dir,
                chunk_times[i][0], chunk_times[i][1],
                prompt_ids, num_beams, self_consistency,
            )
            results[chunk_index] = transcription
            alt_results[chunk_index] = alt_candidate
            chunk_time_info[chunk_index] = (start_time, end_time)
            print(f"Completed chunk {i+1}/{len(audio_chunks)}")

        all_transcriptions = results

    except Exception as e:
        print(f"Error during processing: {e}")
        all_transcriptions = [f"[Processing error: {e}]"] * len(audio_chunks)
        alt_results = [None] * len(audio_chunks)
        # chunk_time_info already initialized before try block
    finally:
        # Always clean up temporary file
        cleanup_temp_file(safe_path, temp_dir)
    
    # Save combined transcription
    combined_file = f"{output_dir}/{base_name}{output_suffix}.txt"
    with open(combined_file, "w", encoding="utf-8") as f:
        for i, transcription in enumerate(all_transcriptions):
            start_time, end_time = chunk_time_info[i]
            f.write(f"=== Chunk {i+1} [{start_time:.2f}s - {end_time:.2f}s] ===\n")
            f.write(transcription)
            f.write("\n\n")
    
    print(f"All transcriptions saved to: {combined_file}")

    # Self-consistency sidecar: for chunks where beam and greedy disagreed, store
    # both candidates so the LLM correction pass can reconcile them. Same suffix
    # base as combined so postprocess can locate it. Only written if any chunk
    # produced a differing greedy candidate.
    if any(alt_results):
        candidates_file = f"{output_dir}/{base_name}_candidates.txt"
        with open(candidates_file, "w", encoding="utf-8") as f:
            for i, alt in enumerate(alt_results):
                if not alt:
                    continue
                start_time, end_time = chunk_time_info[i]
                f.write(f"=== Chunk {i+1} [{start_time:.2f}s - {end_time:.2f}s] ===\n")
                f.write("<<BEAM>>\n")
                f.write((all_transcriptions[i] or "").strip() + "\n")
                f.write("<<GREEDY>>\n")
                f.write(alt.strip() + "\n\n")
        print(f"Self-consistency candidates saved to: {candidates_file}")

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
    
    import argparse as _ap
    p = _ap.ArgumentParser()
    p.add_argument("audio_file_path")
    p.add_argument("--suffix", default="_combined",
                   help="Output filename suffix (default: _combined)")
    a = p.parse_args()

    if not os.path.exists(a.audio_file_path):
        print(f"File not found: {a.audio_file_path}")
        sys.exit(1)

    success, result, error = safe_execute(process_audio_file, a.audio_file_path,
                                          True, a.suffix)

    if success:
        print("Success!")
    else:
        print(f"Error: {error}")
        sys.exit(1)

if __name__ == "__main__":
    main()
