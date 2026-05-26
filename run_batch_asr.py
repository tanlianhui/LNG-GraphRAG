#!/usr/bin/env python3
"""
Run ASR on all WAV files in VODs that do not yet have a transcription.
Output: ./transcriptions/{basename}<suffix>.txt per file.
Skips WAVs that already have a matching transcription file for the chosen suffix.

Usage:
    python run_batch_asr.py                        # normal run → _combined.txt
    python run_batch_asr.py --suffix _kw_combined  # re-run with keyword biasing
    python run_batch_asr.py --filter 2026          # only filenames containing "2026"
"""
import os
import sys
import argparse
from pathlib import Path

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import setup_path, handle_unicode_encoding, safe_execute
from simple_asr import process_audio_file

VODS_DIR = Path("./VODs")
TRANSCRIPTIONS_DIR = Path("./transcriptions")


def get_wavs_to_process(vods_dir: Path, transcriptions_dir: Path,
                         suffix: str, filter_str: str):
    """Return WAV paths that don't yet have a <suffix>.txt transcription."""
    vods_dir = vods_dir.resolve()
    transcriptions_dir = transcriptions_dir.resolve()
    wavs = sorted(vods_dir.glob("*.wav"))
    if filter_str:
        wavs = [w for w in wavs if filter_str in w.name]
    out = []
    for wav in wavs:
        base = wav.stem
        if not (transcriptions_dir / f"{base}{suffix}.txt").exists():
            out.append(wav)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suffix',  default='_combined',
                        help='Output filename suffix (default: _combined)')
    parser.add_argument('--filter',  default='',
                        help='Only process WAV files whose name contains this string')
    args = parser.parse_args()

    setup_path()
    handle_unicode_encoding()

    vods = Path(VODS_DIR)
    trans = Path(TRANSCRIPTIONS_DIR)
    if not vods.exists():
        print(f"❌ VODs directory not found: {vods}")
        sys.exit(1)
    trans.mkdir(parents=True, exist_ok=True)

    to_process = get_wavs_to_process(vods, trans, args.suffix, args.filter)
    all_wavs = list(vods.glob("*.wav"))
    already = len(all_wavs) - len(to_process)

    print("LNG Batch ASR – transcribe WAVs in VODs")
    print("=" * 60)
    print(f"VODs dir: {vods.absolute()}")
    print(f"Transcriptions dir: {trans.absolute()}")
    print(f"Output suffix: {args.suffix}")
    print(f"WAV files: {len(all_wavs)} total, {already} already have {args.suffix}.txt, {len(to_process)} to process")
    print()

    if not to_process:
        print(f"Nothing to do. All WAVs already have {args.suffix}.txt.")
        return 0

    ok = 0
    fail = 0
    for i, wav_path in enumerate(to_process, 1):
        print(f"\n[{i}/{len(to_process)}] {wav_path.name}")
        success, _, error = safe_execute(
            process_audio_file, str(wav_path),
            True,        # keep_audio
            args.suffix, # output_suffix
        )
        if success:
            ok += 1
        else:
            fail += 1
            print(f"   Error: {error}")

    print()
    print("=" * 60)
    print(f"Done. OK: {ok}, Failed: {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
