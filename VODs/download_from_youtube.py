import yt_dlp
import csv
import os
import sys
import time
import random
from pathlib import Path

# Change this to your target channel URL
CHANNEL_URL = "https://www.youtube.com/@LNGworkshop/videos"
OUTPUT_CSV = "./VODs/videos.csv"

def get_user_agents():
    """Get a list of realistic user agents to rotate through"""
    return [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
    ]

def get_cookie_options():
    """
    Get cookie options for yt-dlp. Uses cookies.txt file in VODs directory.
    """
    cookie_options = []
    
    # Use cookies file in VODs directory
    cookie_file = Path("./VODs/www.youtube.com_cookies.txt")
    if cookie_file.exists():
        cookie_options.append(str(cookie_file))
        print(f"Using cookies file: {cookie_file}")
    else:
        print(f"Cookies file not found: {cookie_file}")
        print("Please export YouTube cookies to VODs/cookies.txt")
        print("You can export cookies using browser extensions or yt-dlp")
    
    return cookie_options

def get_all_videos(channel_url, max_retries: int = 3):
    cookie_options = get_cookie_options()
    user_agents = get_user_agents()
    
    for attempt in range(max_retries):
        print(f"Attempt {attempt + 1}/{max_retries} to fetch video list")
        
        # Add random delay between attempts
        if attempt > 0:
            delay = random.uniform(3, 8) * (attempt + 1)  # Exponential backoff
            print(f"Waiting {delay:.1f} seconds before retry...")
            time.sleep(delay)
        
        for cookie_option in cookie_options:
            # Rotate user agents
            user_agent = random.choice(user_agents)
            
            ydl_opts = {
                "extract_flat": True,      # only fetch metadata, not download
                "dump_single_json": True,  # get all items as one JSON
                "quiet": True,
                "ignoreerrors": True,  # Continue even if some videos fail
                "user_agent": user_agent,  # Rotate user agents
                "referer": "https://www.youtube.com/",  # Add referer
                "sleep_interval": random.uniform(1, 3),  # Random sleep between requests
                "max_sleep_interval": 5,  # Maximum sleep time
                "sleep_interval_requests": 1,  # Sleep after each request
            }
            
            # Add cookie support - use cookiefile for simple cookies.txt
            if cookie_option:
                ydl_opts["cookiefile"] = cookie_option
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(channel_url, download=False)
                    videos = info.get("entries", [])
                    if videos:
                        print(f"Successfully fetched {len(videos)} videos using {cookie_option}")
                        return videos
            except Exception as e:
                error_msg = str(e)
                print(f"Attempt {attempt + 1} failed: {error_msg}")
                
                # Check for specific error types
                if "403" in error_msg or "Forbidden" in error_msg:
                    print("403 Forbidden - YouTube is blocking the request")
                    if attempt < max_retries - 1:
                        print("Trying different user agent and longer delay...")
                        continue
                elif "429" in error_msg or "Too Many Requests" in error_msg:
                    print("Rate limited - waiting longer before retry...")
                    time.sleep(random.uniform(15, 30))
                    continue
                else:
                    print(f"Unknown error: {error_msg}")
                    continue
    
    print("All attempts failed to fetch video list")
    return []


def update_csv_status(video_title, status):
    """Update the CSV file with the completion status of a video"""
    try:
        # Read existing CSV
        rows = []
        with open(OUTPUT_CSV, 'r', newline='', encoding="utf-8-sig") as f:
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
        with open(OUTPUT_CSV, 'w', newline='', encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
    except Exception as e:
        print(f"⚠️  Could not update CSV for {video_title}: {e}")


def normalize_youtube_url(url: str) -> str:
    """Normalize YouTube URL to https://www.youtube.com/watch?v=ID"""
    if "youtu.be/" in url:
        vid = url.split("youtu.be/")[1].split("?")[0].strip()
        return f"https://www.youtube.com/watch?v={vid}"
    if "watch?v=" in url:
        vid = url.split("watch?v=")[1].split("&")[0].split("?")[0].strip()
        return f"https://www.youtube.com/watch?v={vid}"
    return url


def ensure_video_in_csv(url: str, title: str) -> None:
    """Ensure a video row exists in CSV; update title if row had a placeholder."""
    url = normalize_youtube_url(url)
    try:
        rows = []
        with open(OUTPUT_CSV, 'r', newline='', encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return
            rows.append(header)
            found = False
            for row in reader:
                if len(row) >= 2 and row[1].strip() == url:
                    # Update title so CSV matches downloaded filename
                    row[0] = title
                    if len(row) >= 3:
                        row[2] = "pending"
                    else:
                        row.append("pending")
                    found = True
                rows.append(row)
            if not found:
                rows.append([title, url, "pending"])
        with open(OUTPUT_CSV, 'w', newline='', encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
    except Exception as e:
        print(f"⚠️  Could not update CSV: {e}")

def download_from_youtube(url: str, output_path: str = "./VODs/%(title)s", max_retries: int = 3):
    # First, check if file already exists
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown')
            # Create the expected filename
            expected_filename = f"./VODs/{title}.wav"
            if os.path.exists(expected_filename):
                print(f"Skipping {title} - already downloaded")
                return True, expected_filename
    except Exception as e:
        print(f"Could not check if file exists for {url}: {e}")
    
    cookie_options = get_cookie_options()
    user_agents = get_user_agents()
    
    for attempt in range(max_retries):
        print(f"Attempt {attempt + 1}/{max_retries} for {url}")
        
        # Add random delay between attempts
        if attempt > 0:
            delay = random.uniform(2, 5) * (attempt + 1)  # Exponential backoff
            print(f"Waiting {delay:.1f} seconds before retry...")
            time.sleep(delay)
        
        for cookie_option in cookie_options:
            # Rotate user agents
            user_agent = random.choice(user_agents)
            
            # Prefer android player client to avoid YouTube SABR/403 on media download
            ydl_opts = {
                'outtmpl': output_path,
                'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                    'preferredquality': '192',
                }],
                'postprocessor_args': {
                    'FFmpegExtractAudio': ['-ar', '16000']  # Set sample rate to 16kHz
                },
                'ignoreerrors': False,
                'no_warnings': False,
                'user_agent': user_agent,
                'referer': 'https://www.youtube.com/',
                'sleep_interval': random.uniform(1, 3),
                'max_sleep_interval': 5,
                'sleep_interval_requests': 1,
                'extract_flat': False,
                'writethumbnail': False,
                'writeinfojson': False,
                'writesubtitles': False,
                'writeautomaticsub': False,
                'extractor_args': {
                    'youtube': {'player_client': ['android', 'web']}  # android often avoids 403
                },
                'http_headers': {
                    'User-Agent': user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            }
            
            # Add cookie support - use cookiefile for simple cookies.txt
            if cookie_option:
                ydl_opts['cookiefile'] = cookie_option
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                # Verify the download actually succeeded by checking for the file
                try:
                    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                        info = ydl.extract_info(url, download=False)
                        title = info.get('title', 'Unknown')
                        downloaded_file = f"./VODs/{title}.wav"
                        if os.path.exists(downloaded_file):
                            print(f"Successfully downloaded: {url} -> {downloaded_file}")
                            return True, downloaded_file
                        else:
                            # Fallback: try to find the file
                            import glob
                            wav_files = glob.glob("./VODs/*.wav")
                            if wav_files:
                                # Get the most recently created file
                                latest_file = max(wav_files, key=os.path.getctime)
                                print(f"Successfully downloaded: {url} -> {latest_file}")
                                return True, latest_file
                            else:
                                print(f"Download failed: No file found for {url}")
                                return False, None
                except Exception as e:
                    print(f"Could not verify download for {url}: {e}")
                    return False, None
            except Exception as e:
                error_msg = str(e)
                print(f"Attempt {attempt + 1} failed for {url}: {error_msg}")
                
                # Check for specific error types
                if "403" in error_msg or "Forbidden" in error_msg:
                    print("403 Forbidden - YouTube is blocking the request")
                    print("Trying fallback with android player client...")
                    success, file_path = try_fallback_download(url, output_path, user_agent, cookie_option)
                    if success and file_path:
                        return True, file_path
                    if attempt < max_retries - 1:
                        print("Trying different user agent and longer delay...")
                        time.sleep(random.uniform(10, 20))
                        continue
                    else:
                        print("All retry attempts failed. Try: pip install -U yt-dlp")
                        return False, None
                elif "429" in error_msg or "Too Many Requests" in error_msg:
                    print("Rate limited - waiting longer before retry...")
                    time.sleep(random.uniform(10, 20))
                    continue
                elif "Video unavailable" in error_msg:
                    print("Video is unavailable (private, deleted, or region-blocked)")
                    return False
                elif "format" in error_msg.lower() or "not available" in error_msg.lower():
                    print("Format issue - trying fallback download method...")
                    # Try fallback download method
                    success, file_path = try_fallback_download(url, output_path, user_agent, cookie_option)
                    if success:
                        return True, file_path
                    continue
                else:
                    print(f"Unknown error: {error_msg}")
                    continue
    
    print(f"All attempts failed for {url}")
    return False, None

def _android_ydl_opts(base_opts):
    """Add YouTube android player client to avoid 403/SABR."""
    base_opts['extractor_args'] = {'youtube': {'player_client': ['android']}}
    return base_opts


def try_fallback_download(url, output_path, user_agent, cookie_option):
    """Try alternative download methods when main method fails (android client, different formats)."""
    print("Trying fallback download methods (android player client)...")
    
    # Method 1: Android client + worst audio format (often works when 140 fails)
    try:
        ydl_opts = _android_ydl_opts({
            'outtmpl': output_path,
            'format': 'worstaudio/worst',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'postprocessor_args': {'FFmpegExtractAudio': ['-ar', '16000']},
            'ignoreerrors': True,
            'user_agent': user_agent,
            'referer': 'https://www.youtube.com/',
            'extract_flat': False,
        })
        if cookie_option:
            ydl_opts['cookiefile'] = cookie_option
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("Fallback method 1 succeeded")
        
        # Try to find the downloaded file
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown')
                downloaded_file = f"./VODs/{title}.wav"
                if os.path.exists(downloaded_file):
                    return True, downloaded_file
        except Exception:
            pass
        return True, None
        
    except Exception as e:
        print(f"Fallback method 1 failed: {e}")
    
    # Method 2: Android client, no format specification
    try:
        ydl_opts = _android_ydl_opts({
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'postprocessor_args': {'FFmpegExtractAudio': ['-ar', '16000']},
            'ignoreerrors': True,
            'user_agent': user_agent,
            'referer': 'https://www.youtube.com/',
            'extract_flat': False,
        })
        if cookie_option:
            ydl_opts['cookiefile'] = cookie_option
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("Fallback method 2 succeeded")
        
        # Try to find the downloaded file
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown')
                downloaded_file = f"./VODs/{title}.wav"
                if os.path.exists(downloaded_file):
                    return True, downloaded_file
        except Exception:
            pass
        return True, None
        
    except Exception as e:
        print(f"Fallback method 2 failed: {e}")
    
    # Method 3: Android client, best format (video+audio then extract)
    try:
        ydl_opts = _android_ydl_opts({
            'outtmpl': output_path,
            'format': 'best',
            'ignoreerrors': True,
            'user_agent': user_agent,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'postprocessor_args': {'FFmpegExtractAudio': ['-ar', '16000']},
        })
        if cookie_option:
            ydl_opts['cookiefile'] = cookie_option
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("Fallback method 3 succeeded")
        
        # Try to find the downloaded file
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown')
                downloaded_file = f"./VODs/{title}.wav"
                if os.path.exists(downloaded_file):
                    return True, downloaded_file
        except Exception:
            pass
        return True, None
        
    except Exception as e:
        print(f"Fallback method 3 failed: {e}")
    
    print("All fallback methods failed")
    return False, None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LNG YouTube Downloader")
    parser.add_argument(
        "--url",
        type=str,
        help="Download a single video by URL (e.g. https://youtu.be/VIDEO_ID). Does not overwrite videos.csv.",
    )
    args = parser.parse_args()

    if args.url:
        # Single-video mode: add to CSV if needed, then download
        url = normalize_youtube_url(args.url)
        print("LNG YouTube Downloader - Single video")
        print("=" * 60)
        print(f"URL: {url}")
        try:
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get("title", "Unknown")
        except Exception as e:
            print(f"❌ Failed to get video info: {e}")
            return
        print(f"Title: {title}")
        ensure_video_in_csv(url, title)
        expected_filename = f"./VODs/{title}.wav"
        if os.path.exists(expected_filename):
            print(f"Skipping - already downloaded: {expected_filename}")
            update_csv_status(title, "skipped")
            return
        ok, _ = download_from_youtube(url)
        if ok:
            update_csv_status(title, "completed")
            print("✅ Download completed. Next: run ASR, then load_transcriptions_to_neo4j.py")
        else:
            update_csv_status(title, "failed")
            print("❌ Download failed.")
        return

    print("LNG YouTube Downloader with Enhanced Error Handling")
    print("=" * 60)
    print("Fetching video list...")
    
    videos = get_all_videos(CHANNEL_URL)
    
    if not videos:
        print("No videos found. This might be due to age restrictions or authentication issues.")
        print("Try the following solutions:")
        print("1. Make sure you're logged into YouTube in Chrome")
        print("2. Export fresh cookies from your browser")
        print("3. Try running the script again with a longer delay")
        print("4. Check if the channel URL is correct")
        print("5. Consider using a VPN if you're in a restricted region")
        return

    # Filter out videos that contain "精華" in title
    filtered = [v for v in videos if "精華" not in v.get("title", "")]
    print(f"Found {len(videos)} total videos, {len(filtered)} after filtering")

    # Write to CSV
    with open(OUTPUT_CSV, "w", newline='', encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "url", "status"])
        for v in filtered:
            url = f"https://www.youtube.com/watch?v={v.get('id')}"
            writer.writerow([v.get("title", ""), url, "pending"])

    print(f"Saved {len(filtered)} videos to {OUTPUT_CSV}")
    print("Starting downloads...")
    
    successful_downloads = 0
    failed_downloads = 0
    skipped_downloads = 0
    
    for i, video in enumerate(filtered, 1):
        video_id = video.get('id')
        video_title = video.get('title', 'Unknown')
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        print(f"\n[{i}/{len(filtered)}] Processing: {video_title[:50]}...")
        
        # Check if file already exists before attempting download
        expected_filename = f"./VODs/{video_title}.wav"
        if os.path.exists(expected_filename):
            print(f"Skipping {video_title} - already downloaded")
            skipped_downloads += 1
            update_csv_status(video_title, "skipped")
            continue
        
        if download_from_youtube(url):
            successful_downloads += 1
            print(f"Successfully downloaded: {video_title}")
            update_csv_status(video_title, "completed")
        else:
            failed_downloads += 1
            print(f"Failed to download: {video_title}")
            update_csv_status(video_title, "failed")
        
        # Add delay between downloads to avoid rate limiting
        if i < len(filtered):  # Don't delay after the last video
            delay = random.uniform(2, 5)  # Random delay between 2-5 seconds
            print(f"Waiting {delay:.1f} seconds before next download...")
            time.sleep(delay)
    
    print(f"\nDownload Summary:")
    print(f"Successful: {successful_downloads}")
    print(f"Skipped (already exists): {skipped_downloads}")
    print(f"Failed: {failed_downloads}")
    print(f"Total processed: {len(filtered)}")

if __name__ == "__main__":
    main()