#!/usr/bin/env python3
"""
Run ASR on all WAV files in VODs that do not yet have a transcription.
Output: ./transcriptions/{basename}_combined.txt per file.
Skips WAVs that already have a matching transcription file.
"""
import os
import sys
from pathlib import Path

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import setup_path, handle_unicode_encoding, safe_execute
from simple_asr import process_audio_file

VODS_DIR = Path("./VODs")
TRANSCRIPTIONS_DIR = Path("./transcriptions")


def get_wavs_without_transcription(vods_dir: Path, transcriptions_dir: Path):
    """Return list of WAV paths in vods_dir that don't have a _combined.txt yet."""
    vods_dir = vods_dir.resolve()
    transcriptions_dir = transcriptions_dir.resolve()
    wavs = sorted(vods_dir.glob("*.wav"))
    out = []
    for wav in wavs:
        base = wav.stem
        combined = transcriptions_dir / f"{base}_combined.txt"
        if not combined.exists():
            out.append(wav)
    return out


def main():
    setup_path()
    handle_unicode_encoding()

    vods = Path(VODS_DIR)
    trans = Path(TRANSCRIPTIONS_DIR)
    if not vods.exists():
        print(f"❌ VODs directory not found: {vods}")
        sys.exit(1)
    trans.mkdir(parents=True, exist_ok=True)

    to_process = get_wavs_without_transcription(vods, trans)
    all_wavs = list(vods.glob("*.wav"))
    already = len(all_wavs) - len(to_process)

    print("LNG Batch ASR – transcribe WAVs in VODs")
    print("=" * 60)
    print(f"VODs dir: {vods.absolute()}")
    print(f"Transcriptions dir: {trans.absolute()}")
    print(f"WAV files: {len(all_wavs)} total, {already} already transcribed, {len(to_process)} to process")
    print()

    if not to_process:
        print("Nothing to do. All VOD WAVs already have transcriptions.")
        return 0

    ok = 0
    fail = 0
    for i, wav_path in enumerate(to_process, 1):
        print(f"\n[{i}/{len(to_process)}] {wav_path.name}")
        success, _, error = safe_execute(process_audio_file, str(wav_path), True)  # keep_audio=True
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
