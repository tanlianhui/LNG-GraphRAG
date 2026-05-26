"""
fetch_new_vods.py — Fetch new live stream replays from LNG official channel.

Checks the /streams tab for videos not yet in videos.csv, downloads them,
runs ASR transcription, and loads the results into Neo4j.

Usage:
    python fetch_new_vods.py               # full pipeline
    python fetch_new_vods.py --dry-run     # list new videos only
    python fetch_new_vods.py --no-asr      # skip ASR step
    python fetch_new_vods.py --no-neo4j    # skip Neo4j loading step
"""
import csv
import os
import sys
import subprocess
import argparse
from pathlib import Path

# Make VODs package importable
sys.path.insert(0, str(Path(__file__).parent))
from VODs.download_from_youtube import (
    get_all_videos,
    normalize_youtube_url,
    download_from_youtube,
    update_csv_status,
    OUTPUT_CSV,
)

STREAMS_URL = "https://www.youtube.com/@LNGworkshop/streams"
VIDEOS_URL  = "https://www.youtube.com/@LNGworkshop/videos"


def read_existing_urls() -> set:
    if not os.path.exists(OUTPUT_CSV):
        return set()
    with open(OUTPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return {normalize_youtube_url(row.get('url', '')) for row in reader if row.get('url')}


def append_to_csv(title: str, url: str, upload_date: str = '') -> None:
    file_exists = os.path.exists(OUTPUT_CSV)
    fieldnames = ['title', 'url', 'status', 'upload_date']
    if file_exists:
        with open(OUTPUT_CSV, 'r', encoding='utf-8-sig') as f:
            detected = csv.DictReader(f).fieldnames
            if detected:
                fieldnames = list(detected)
                if 'upload_date' not in fieldnames:
                    fieldnames.append('upload_date')
    with open(OUTPUT_CSV, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        writer.writerow({'title': title, 'url': url, 'status': 'pending', 'upload_date': upload_date})


def main():
    parser = argparse.ArgumentParser(description="Fetch new LNG live stream replays")
    parser.add_argument('--dry-run', action='store_true', help='List new videos without downloading')
    parser.add_argument('--no-asr', action='store_true', help='Skip ASR step')
    parser.add_argument('--no-neo4j', action='store_true', help='Skip Neo4j loading step')
    parser.add_argument('--limit', type=int, default=0, help='Max new videos to process (0 = all)')
    args = parser.parse_args()

    all_videos = {}
    for label, url in [("streams", STREAMS_URL), ("videos", VIDEOS_URL)]:
        print(f"[fetch_new_vods] Checking {url} ...")
        fetched = get_all_videos(url) or []
        for v in fetched:
            vid_id = v.get('id')
            if vid_id and vid_id not in all_videos:
                all_videos[vid_id] = v

    videos = list(all_videos.values())
    if not videos:
        print("[fetch_new_vods] No videos fetched.")
        return

    videos = [v for v in videos if '精華' not in v.get('title', '')]
    print(f"[fetch_new_vods] {len(videos)} videos found (after filtering)")

    existing_urls = read_existing_urls()
    new_videos = [
        v for v in videos
        if normalize_youtube_url(f"https://www.youtube.com/watch?v={v.get('id')}") not in existing_urls
    ]

    if not new_videos:
        print("[fetch_new_vods] No new live stream replays.")
        return

    if args.limit and args.limit > 0:
        new_videos = new_videos[:args.limit]
        print(f"[fetch_new_vods] Limiting to {args.limit} newest video(s)")

    print(f"[fetch_new_vods] {len(new_videos)} new replays:")
    for v in new_videos:
        date_str = v.get('upload_date', '')
        formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}" if len(date_str) == 8 else date_str
        print(f"  [{formatted}] {v.get('title', 'Unknown')}")

    if args.dry_run:
        print("[fetch_new_vods] --dry-run: no downloads.")
        return

    downloaded = []
    for v in new_videos:
        title = v.get('title', 'Unknown')
        url = normalize_youtube_url(f"https://www.youtube.com/watch?v={v.get('id')}")
        upload_date = v.get('upload_date', '')

        append_to_csv(title, url, upload_date)

        wav_path = f"./VODs/{title}.wav"
        if os.path.exists(wav_path):
            print(f"[fetch_new_vods] Already downloaded: {title}")
            update_csv_status(title, 'skipped')
            continue

        ok, _ = download_from_youtube(url)
        if ok:
            update_csv_status(title, 'completed')
            downloaded.append(title)
            print(f"[fetch_new_vods] Downloaded: {title}")
        else:
            update_csv_status(title, 'failed')
            print(f"[fetch_new_vods] Failed: {title}")

    if not downloaded:
        print("[fetch_new_vods] No new downloads completed.")
        return

    root = Path(__file__).parent

    if not args.no_asr:
        print("[fetch_new_vods] Running ASR ...")
        subprocess.run([sys.executable, str(root / 'run_batch_asr.py')], check=False)

    if not args.no_neo4j:
        print("[fetch_new_vods] Loading to Neo4j ...")
        subprocess.run([sys.executable, str(root / 'run_embeddings_to_neo4j.py')], check=False)

    print(f"[fetch_new_vods] Done. {len(downloaded)} new replays processed.")


if __name__ == '__main__':
    main()
