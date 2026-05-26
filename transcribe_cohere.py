"""
transcribe_cohere.py — Transcribe 2024-2026 LNG streams with Cohere ASR,
then use an LLM to merge with existing Breeze-ASR-25 output into the
highest-accuracy Mandarin dialogue sequence.

Chunking: uses the SAME silence-based boundaries from the existing Breeze
_combined.txt timestamps so each chunk pair is perfectly aligned.
For files with no Breeze transcription, falls back to silero-VAD.

Pipeline per file:
  1. Download WAV if missing
  2. Parse Breeze chunk timestamps from _combined.txt
  3. Slice WAV at those boundaries → feed each segment to Cohere
  4. LLM merges (cohere_text, breeze_text) per chunk → best sequence
  5. Save transcriptions/<title>_merged.txt

Usage:
    python transcribe_cohere.py                       # all 2024-2026 streams
    python transcribe_cohere.py --filter "2025"
    python transcribe_cohere.py --skip-existing       # skip already-merged
    python transcribe_cohere.py --skip-download
    python transcribe_cohere.py --merge-only          # re-merge from cached _cohere_raw.txt
    python transcribe_cohere.py --dry-run
"""
import sys
import csv
import re
import argparse
import os
from pathlib import Path

import torch
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

VODS_DIR       = Path('./VODs')
TRANSCRIPTIONS = Path('./transcriptions')
VIDEOS_CSV     = VODS_DIR / 'videos.csv'
MODEL_ID       = 'CohereLabs/cohere-transcribe-03-2026'
PROC_REVISION  = 'refs/pr/6'
MODEL_REVISION = None           # main branch — weights live here
LANGUAGE       = 'zh'
SAMPLE_RATE    = 16000

ERROR_PATTERNS = ('CUDA', 'Error:', 'Traceback', 'RuntimeError', 'assert',
                  'LAUNCH_BLOCKING', 'stderr', 'ImportError', 'Exception')

MERGE_PROMPT = """\
你是語音辨識後處理專家。以下是同一段中文音訊（直播對話）的兩個不同ASR辨識結果，請合併成最準確、最流暢的版本。

規則：
- 兩個版本都可能有錯字、缺字或多字
- 若某版本出現明顯錯誤訊息（CUDA error、Error: 等），請完全忽略並直接使用另一版本
- 保留兩個版本中最合理的詞彙與句子結構
- 輸出連貫自然的中文對話，保留說話語氣
- 只回覆合併後的文字，不加任何說明或標題

[Cohere Transcribe]
{cohere}

[Breeze-ASR-25]
{breeze}

合併結果："""


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_entries(filter_str: str) -> list[dict]:
    entries = []
    with open(VIDEOS_CSV, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if filter_str in row['title']:
                entries.append({'title': row['title'], 'url': row['url']})
    return entries


def wav_path(title: str) -> Path:
    return VODS_DIR / f'{title}.wav'


def breeze_path(title: str) -> Path:
    return TRANSCRIPTIONS / f'{title}_combined.txt'


def cohere_cache_path(title: str) -> Path:
    return TRANSCRIPTIONS / f'{title}_cohere_raw.txt'


def merged_path(title: str) -> Path:
    return TRANSCRIPTIONS / f'{title}_merged.txt'


def is_error_text(text: str) -> bool:
    return any(p in text for p in ERROR_PATTERNS)


# ---------------------------------------------------------------------------
# Parse Breeze chunks → list of (start_s, end_s, text_or_empty)
# Keeps errored chunks with empty text so their timestamps are preserved.
# ---------------------------------------------------------------------------

def parse_breeze_chunks(title: str) -> list[tuple[float, float, str]]:
    p = breeze_path(title)
    if not p.exists():
        return []
    header = re.compile(r'=== Chunk \d+ \[(\d+\.?\d*)s - (\d+\.?\d*)s\]')
    chunks, cur_s, cur_e, cur_lines = [], None, None, []
    for line in p.read_text(encoding='utf-8').splitlines():
        m = header.match(line)
        if m:
            if cur_s is not None:
                text = ' '.join(cur_lines).strip()
                chunks.append((cur_s, cur_e, '' if is_error_text(text) else text))
            cur_s, cur_e, cur_lines = float(m.group(1)), float(m.group(2)), []
        elif line.strip() and cur_s is not None:
            cur_lines.append(line.strip())
    if cur_s is not None:
        text = ' '.join(cur_lines).strip()
        chunks.append((cur_s, cur_e, '' if is_error_text(text) else text))
    return chunks


# ---------------------------------------------------------------------------
# VAD fallback (when no Breeze timestamps exist)
# ---------------------------------------------------------------------------

def vad_chunks(audio_np: np.ndarray, sr: int) -> list[tuple[float, float]]:
    """Use silero-VAD to find speech segments, returning (start_s, end_s) pairs."""
    try:
        model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad', model='silero_vad', trust_repo=True)
        (get_speech_timestamps, _, read_audio, *_) = utils
        tensor = torch.from_numpy(audio_np).float()
        timestamps = get_speech_timestamps(tensor, model, sampling_rate=sr,
                                           min_silence_duration_ms=500)
        return [(t['start'] / sr, t['end'] / sr) for t in timestamps]
    except Exception as e:
        print(f'  VAD failed ({e}), using 30s fixed chunks')
        total_s = len(audio_np) / sr
        return [(s, min(s + 30, total_s))
                for s in range(0, int(total_s), 30)]


# ---------------------------------------------------------------------------
# Audio loading and slicing
# ---------------------------------------------------------------------------

def load_audio(path: Path) -> tuple[np.ndarray, int]:
    import librosa
    audio, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    return audio.astype(np.float32), SAMPLE_RATE


def slice_audio(audio_np: np.ndarray, start_s: float, end_s: float) -> np.ndarray:
    s = int(start_s * SAMPLE_RATE)
    e = int(end_s   * SAMPLE_RATE)
    return audio_np[s:e]


# ---------------------------------------------------------------------------
# Cohere transcription (one chunk at a time)
# ---------------------------------------------------------------------------

def cohere_transcribe_chunk(segment: np.ndarray, processor, model) -> str:
    if len(segment) == 0:
        return ''
    results = model.transcribe(
        processor,
        language=LANGUAGE,
        audio_arrays=[segment],
        sample_rates=[SAMPLE_RATE],
        punctuation=True,
    )
    return results[0] if results else ''


# ---------------------------------------------------------------------------
# Cache cohere raw output
# ---------------------------------------------------------------------------

def save_cohere_raw(title: str, chunks: list[tuple[float, float, str]]) -> None:
    lines = [f'=== Chunk {i+1} [{s:.2f}s - {e:.2f}s] ===\n{t}\n'
             for i, (s, e, t) in enumerate(chunks)]
    cohere_cache_path(title).write_text('\n'.join(lines), encoding='utf-8')


def load_cohere_raw(title: str) -> list[tuple[float, float, str]]:
    p = cohere_cache_path(title)
    if not p.exists():
        return []
    header = re.compile(r'=== Chunk \d+ \[(\d+\.?\d*)s - (\d+\.?\d*)s\]')
    results, cur_s, cur_e, cur_lines = [], None, None, []
    for line in p.read_text(encoding='utf-8').splitlines():
        m = header.match(line)
        if m:
            if cur_s is not None:
                results.append((cur_s, cur_e, ' '.join(cur_lines).strip()))
            cur_s, cur_e, cur_lines = float(m.group(1)), float(m.group(2)), []
        elif line.strip():
            cur_lines.append(line.strip())
    if cur_s is not None:
        results.append((cur_s, cur_e, ' '.join(cur_lines).strip()))
    return results


# ---------------------------------------------------------------------------
# LLM merge
# ---------------------------------------------------------------------------

def get_llm():
    backend = os.getenv('NL_QUERY_LLM', 'openai').strip().lower()
    if backend == 'ollama':
        from langchain_ollama import ChatOllama
        mdl = os.getenv('OLLAMA_NL_MODEL', 'llama3.2')
        return ChatOllama(model=mdl, temperature=0.1,
                          timeout=int(os.getenv('OLLAMA_TIMEOUT', '120')),
                          num_ctx=int(os.getenv('OLLAMA_NUM_CTX', '8192')))
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=os.getenv('OPENAI_NL_MODEL', 'gpt-4o-mini'), temperature=0.1)


def llm_merge(llm, cohere_text: str, breeze_text: str) -> str:
    if not cohere_text and not breeze_text:
        return ''
    if not cohere_text:
        return breeze_text
    if not breeze_text:
        return cohere_text
    prompt = MERGE_PROMPT.format(cohere=cohere_text[:2000], breeze=breeze_text[:2000])
    try:
        resp = llm.invoke([{'role': 'user', 'content': prompt}])
        result = re.sub(r'<think>.*?</think>', '', resp.content, flags=re.DOTALL).strip()
        return result or cohere_text
    except Exception as e:
        print(f'    LLM error: {e} — using Cohere text')
        return cohere_text


# ---------------------------------------------------------------------------
# Write merged output
# ---------------------------------------------------------------------------

def write_merged(title: str,
                 chunks: list[tuple[float, float, str, str, str]]) -> None:
    """chunks: (start_s, end_s, cohere_text, breeze_text, merged_text)"""
    TRANSCRIPTIONS.mkdir(exist_ok=True)
    lines = []
    for i, (s, e, _c, _b, merged) in enumerate(chunks, 1):
        lines.append(f'=== Chunk {i} [{s:.2f}s - {e:.2f}s] ===')
        lines.append(merged)
        lines.append('')
    merged_path(title).write_text('\n'.join(lines), encoding='utf-8')
    print(f'  Saved → {merged_path(title).name}')


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_wav(url: str) -> bool:
    sys.path.insert(0, str(VODS_DIR))
    from download_from_youtube import download_from_youtube
    ok, _ = download_from_youtube(url)
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--filter', default='【LNG】202')
    parser.add_argument('--skip-existing', action='store_true')
    parser.add_argument('--skip-download', action='store_true')
    parser.add_argument('--merge-only', action='store_true',
                        help='Skip Cohere step; re-merge from cached _cohere_raw.txt')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    entries = load_entries(args.filter)
    print(f'Found {len(entries)} entries matching "{args.filter}"')

    if args.dry_run:
        for e in entries:
            w = 'WAV✓' if wav_path(e['title']).exists() else 'WAV✗'
            b = 'BRZ✓' if breeze_path(e['title']).exists() else 'BRZ✗'
            c = 'CHR✓' if cohere_cache_path(e['title']).exists() else 'CHR✗'
            m = 'MRG✓' if merged_path(e['title']).exists() else 'MRG✗'
            print(f'  {w} {b} {c} {m}  {e["title"][:65]}')
        return

    # Load Cohere model
    processor = model = None
    if not args.merge_only:
        print(f'Loading Cohere model {MODEL_ID}...')
        from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq
        processor = AutoProcessor.from_pretrained(
            MODEL_ID, revision=PROC_REVISION, trust_remote_code=True)
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            MODEL_ID, revision=MODEL_REVISION, trust_remote_code=True, device_map='auto')
        model.eval()
        print(f'  → loaded on {next(model.parameters()).device}')

    print('Loading LLM for merging...')
    llm = get_llm()
    print(f'  → {type(llm).__name__}\n')

    for i, entry in enumerate(entries, 1):
        title, url = entry['title'], entry['url']
        print(f'\n[{i}/{len(entries)}] {title[:75]}')

        if args.skip_existing and merged_path(title).exists():
            print('  Skipping — merged file already exists')
            continue

        # --- Step 1: get Cohere chunks aligned to Breeze timestamps ---
        if args.merge_only:
            cohere_chunks = load_cohere_raw(title)
            if not cohere_chunks:
                print('  No cached Cohere output, skipping')
                continue
        else:
            wav = wav_path(title)
            if not wav.exists():
                if args.skip_download:
                    print('  WAV not found, skipping')
                    continue
                print('  Downloading...')
                if not download_wav(url) or not wav.exists():
                    print('  Download failed, skipping')
                    continue

            print(f'  Loading audio ({wav.stat().st_size / 1e6:.0f} MB)...')
            audio_np, sr = load_audio(wav)

            # Use Breeze silence-split boundaries; fall back to VAD
            breeze_raw = parse_breeze_chunks(title)
            if breeze_raw:
                boundaries = [(s, e) for s, e, _ in breeze_raw]
                print(f'  Using {len(boundaries)} Breeze silence-split boundaries')
            else:
                print('  No Breeze transcription — running VAD...')
                boundaries = vad_chunks(audio_np, sr)
                print(f'  VAD found {len(boundaries)} speech segments')

            print('  Transcribing chunks with Cohere...')
            cohere_chunks = []
            for ci, (cs, ce) in enumerate(boundaries, 1):
                seg = slice_audio(audio_np, cs, ce)
                text = cohere_transcribe_chunk(seg, processor, model)
                cohere_chunks.append((cs, ce, text))
                print(f'    [{cs:.1f}s-{ce:.1f}s] {text[:70]}')

            save_cohere_raw(title, cohere_chunks)

        # --- Step 2: load Breeze texts (may be empty for errored chunks) ---
        breeze_map = {(s, e): t for s, e, t in parse_breeze_chunks(title)}

        # --- Step 3: LLM merge per chunk ---
        print(f'  Merging {len(cohere_chunks)} chunks with LLM...')
        merged_chunks = []
        for ci, (cs, ce, cohere_text) in enumerate(cohere_chunks, 1):
            breeze_text = breeze_map.get((cs, ce), '')
            merged = llm_merge(llm, cohere_text, breeze_text)
            merged_chunks.append((cs, ce, cohere_text, breeze_text, merged))
            print(f'    Chunk {ci}: {merged[:70]}')

        write_merged(title, merged_chunks)

    print('\nAll done.')


if __name__ == '__main__':
    main()
