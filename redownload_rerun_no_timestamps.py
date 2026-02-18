#!/usr/bin/env python3
"""
Redownload videos whose transcriptions have no timestamps, then rerun ASR to produce
the same combined format with timestamps (=== Chunk N [start_time - end_time] ===).
Uses find_transcriptions_without_timestamps logic and VODs/videos.csv for URLs.
"""
import re
import csv
import sys
import subprocess
from pathlib import Path

TRANSCRIPTIONS_DIR = Path("./transcriptions")
VODS_DIR = Path("./VODs")
VIDEOS_CSV = Path("./VODs/videos.csv")
TIMECODE_PATTERN = re.compile(r"\[\d+\.?\d*s\s*-\s*\d+\.?\d*s\]")


def has_timestamps(content: str) -> bool:
    return bool(TIMECODE_PATTERN.search(content))


def get_transcription_base_name(path: Path) -> str:
    stem = path.stem
    if stem.endswith("_combined"):
        return stem[: -len("_combined")]
    return stem


def get_titles_without_timestamps():
    """Return list of (transcription_path, base_name) for files without timestamps."""
    if not TRANSCRIPTIONS_DIR.exists():
        return []
    result = []
    for path in sorted(TRANSCRIPTIONS_DIR.glob("*_combined.txt")):
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if not has_timestamps(content):
            result.append((path, get_transcription_base_name(path)))
    return result


def load_title_to_url():
    """Return dict title -> url from videos.csv."""
    out = {}
    if not VIDEOS_CSV.exists():
        return out
    with open(VIDEOS_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("title") or "").strip()
            url = (row.get("url") or "").strip()
            if title and url:
                out[title] = url
    return out


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Redownload videos for transcriptions without timestamps and rerun ASR (same format with timestamps)."
    )
    parser.add_argument(
        "--title",
        type=str,
        help="Process only this exact title (must match CSV title). If omitted, process all transcriptions without timestamps.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download; only rerun ASR on existing WAVs (e.g. after manual download).",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    no_ts = get_titles_without_timestamps()
    title_to_url = load_title_to_url()

    if args.title:
        # Single title: must match a no-timestamp file and CSV
        base = args.title.strip()
        matching = [(p, b) for p, b in no_ts if b == base]
        if not matching:
            print(f"❌ No transcription without timestamps with base name: {base}")
            print("  Run: python find_transcriptions_without_timestamps.py")
            sys.exit(1)
        path, base_name = matching[0]
        url = title_to_url.get(base_name) or title_to_url.get(base)
        if not url and not args.skip_download:
            print(f"❌ Title not found in {VIDEOS_CSV}: {base_name}")
            sys.exit(1)
        to_process = [(path, base_name, url)]
    else:
        if not no_ts:
            print("✅ No transcriptions without timestamps. Nothing to do.")
            return 0
        to_process = []
        for path, base_name in no_ts:
            url = title_to_url.get(base_name)
            to_process.append((path, base_name, url))

    print("Redownload + rerun ASR for transcriptions without timestamps")
    print("=" * 60)
    for path, base_name, url in to_process:
        print(f"  {base_name}  url={url or '(not in CSV)'}")
    print()

    ok = 0
    fail = 0
    for path, base_name, url in to_process:
        wav_path = VODS_DIR / f"{base_name}.wav"

        if not args.skip_download and url:
            print(f"Downloading: {base_name}")
            r = subprocess.run(
                [sys.executable, str(root / "VODs" / "download_from_youtube.py"), "--url", url],
                cwd=root,
                timeout=600,
            )
            if r.returncode != 0:
                print(f"  ❌ Download failed for {base_name}")
                fail += 1
                continue
            if not wav_path.exists():
                print(f"  ⚠️  WAV not found after download: {wav_path}")
                fail += 1
                continue
        elif args.skip_download or not url:
            if not wav_path.exists():
                print(f"  ⚠️  Skip (no WAV): {wav_path}")
                fail += 1
                continue

        print(f"Running ASR: {wav_path.name}")
        r = subprocess.run(
            [sys.executable, str(root / "simple_asr.py"), str(wav_path)],
            cwd=root,
            timeout=3600,
        )
        if r.returncode == 0:
            ok += 1
            print(f"  ✅ {base_name}_combined.txt updated with timestamps")
        else:
            fail += 1
            print(f"  ❌ ASR failed for {base_name}")

    print()
    print("=" * 60)
    print(f"Done. OK: {ok}, Failed: {fail}")
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    main()
