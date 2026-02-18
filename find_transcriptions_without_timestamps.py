 #!/usr/bin/env python3
"""
Find transcription files that do not contain timestamps (e.g. === Chunk 1 === instead of === Chunk 1 [0.00s - 94.49s] ===).
Outputs their names and, if videos.csv exists, the YouTube URL for redownload + rerun.
"""
import re
import csv
import sys
from pathlib import Path

TRANSCRIPTIONS_DIR = Path("./transcriptions")
VIDEOS_CSV = Path("./VODs/videos.csv")
# Timecode pattern used in combined format: [0.00s - 94.49s]
TIMECODE_PATTERN = re.compile(r"\[\d+\.?\d*s\s*-\s*\d+\.?\d*s\]")


def has_timestamps(content: str) -> bool:
    """Return True if content has at least one chunk header with timecodes."""
    return bool(TIMECODE_PATTERN.search(content))


def get_transcription_base_name(path: Path) -> str:
    """e.g. 'foo_combined.txt' -> 'foo'."""
    stem = path.stem  # foo_combined
    if stem.endswith("_combined"):
        return stem[: -len("_combined")]
    return stem


def main():
    trans_dir = TRANSCRIPTIONS_DIR.resolve()
    if not trans_dir.exists():
        print(f"❌ Transcriptions directory not found: {trans_dir}")
        sys.exit(1)

    combined_files = sorted(trans_dir.glob("*_combined.txt"))
    if not combined_files:
        print(f"No *_combined.txt files in {trans_dir}")
        sys.exit(0)

    no_ts: list[Path] = []
    for path in combined_files:
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"⚠️  Could not read {path.name}: {e}")
            continue
        if not has_timestamps(content):
            no_ts.append(path)

    # Report
    print("=" * 60)
    print("Transcriptions without timestamps")
    print("=" * 60)
    print(f"Scanned: {trans_dir}")
    print(f"Total _combined.txt: {len(combined_files)}")
    print(f"Without timestamps: {len(no_ts)}")
    print()

    if not no_ts:
        print("✅ All transcriptions have timestamps.")
        return 0

    print("Files missing timestamps:")
    for p in no_ts:
        print(f"  - {p.name}")
    print()

    # Map to videos.csv for redownload
    title_to_url: dict[str, str] = {}
    if VIDEOS_CSV.exists():
        try:
            with open(VIDEOS_CSV, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    title = (row.get("title") or "").strip()
                    url = (row.get("url") or "").strip()
                    if title and url:
                        title_to_url[title] = url
        except Exception as e:
            print(f"⚠️  Could not read {VIDEOS_CSV}: {e}")

    if title_to_url:
        print("Suggested redownload (match by transcription base name ↔ CSV title):")
        for p in no_ts:
            base = get_transcription_base_name(p)
            url = title_to_url.get(base)
            if url:
                print(f"  {base}")
                print(f"    URL: {url}")
            else:
                # Try partial match (title can have extra chars in CSV)
                matches = [t for t in title_to_url if base in t or t in base]
                if matches:
                    print(f"  {base} (possible CSV title: {matches[0]})")
                    print(f"    URL: {title_to_url[matches[0]]}")
                else:
                    print(f"  {base} (no matching title in videos.csv)")
        print()
        print("To redownload and rerun ASR for these (same format with timestamps):")
        print("  python redownload_rerun_no_timestamps.py")
        print("Or for one file:")
        print("  python redownload_rerun_no_timestamps.py --title \"Exact title from list above\"")
    else:
        print("No videos.csv found; add URLs manually and run ASR on the WAVs.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
