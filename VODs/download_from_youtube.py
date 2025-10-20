import yt_dlp
import csv
import os
import sys
from pathlib import Path

# Change this to your target channel URL
CHANNEL_URL = "https://www.youtube.com/@LNGworkshop/videos"
OUTPUT_CSV = "./VODs/videos.csv"

def get_cookie_options():
    """
    Get cookie options for yt-dlp. Uses cookies.txt file in VODs directory.
    """
    cookie_options = []
    
    # Use cookies file in VODs directory
    cookie_file = Path("./VODs/www.youtube.com_cookies.txt")
    if cookie_file.exists():
        cookie_options.append(str(cookie_file))
        print(f"✅ Using cookies file: {cookie_file}")
    else:
        print(f"⚠️  Cookies file not found: {cookie_file}")
        print("💡 Please export YouTube cookies to VODs/cookies.txt")
        print("💡 You can export cookies using browser extensions or yt-dlp")
    
    return cookie_options

def get_all_videos(channel_url):
    cookie_options = get_cookie_options()
    
    for cookie_option in cookie_options:
        ydl_opts = {
            "extract_flat": True,      # only fetch metadata, not download
            "dump_single_json": True,  # get all items as one JSON
            "quiet": True,
            "ignoreerrors": True,  # Continue even if some videos fail
        }
        
        # Add cookie support - use cookiefile for simple cookies.txt
        ydl_opts["cookiefile"] = cookie_option
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
                videos = info.get("entries", [])
                if videos:
                    print(f"✅ Successfully fetched {len(videos)} videos using {cookie_option}")
                    return videos
        except Exception as e:
            print(f"⚠️  Cookie method {cookie_option} failed: {e}")
            continue
    
    print("❌ All cookie methods failed")
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

def download_from_youtube(url: str, output_path: str = "./VODs/%(title)s"):
    # First, check if file already exists
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown')
            # Create the expected filename
            expected_filename = f"./VODs/{title}.wav"
            if os.path.exists(expected_filename):
                print(f"⏭️  Skipping {title} - already downloaded")
                return True
    except Exception as e:
        print(f"⚠️  Could not check if file exists for {url}: {e}")
    
    cookie_options = get_cookie_options()
    
    for cookie_option in cookie_options:
        ydl_opts = {
            'outtmpl': output_path,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'postprocessor_args': {
                'FFmpegExtractAudio': ['-ar', '16000']  # Set sample rate to 16kHz
            },
            'ignoreerrors': True,  # Continue even if some videos fail
            'no_warnings': False,  # Show warnings for debugging
        }
        
        # Add cookie support - use cookiefile for simple cookies.txt
        ydl_opts['cookiefile'] = cookie_option
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return True
        except Exception as e:
            print(f"⚠️  Cookie method {cookie_option} failed for {url}: {e}")
            continue
    
    print(f"❌ All cookie methods failed for {url}")
    return False


def main():
    print("Fetching video list...")
    videos = get_all_videos(CHANNEL_URL)
    
    if not videos:
        print("❌ No videos found. This might be due to age restrictions or authentication issues.")
        print("💡 Try the following solutions:")
        print("1. Make sure you're logged into YouTube in Chrome")
        print("2. Try running the script again")
        print("3. Check if the channel URL is correct")
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

    print(f"📝 Saved {len(filtered)} videos to {OUTPUT_CSV}")
    print("🎬 Starting downloads...")
    
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
            print(f"⏭️  Skipping {video_title} - already downloaded")
            skipped_downloads += 1
            update_csv_status(video_title, "skipped")
            continue
        
        if download_from_youtube(url):
            successful_downloads += 1
            print(f"✅ Successfully downloaded: {video_title}")
            update_csv_status(video_title, "completed")
        else:
            failed_downloads += 1
            print(f"❌ Failed to download: {video_title}")
            update_csv_status(video_title, "failed")
    
    print(f"\n📊 Download Summary:")
    print(f"✅ Successful: {successful_downloads}")
    print(f"⏭️  Skipped (already exists): {skipped_downloads}")
    print(f"❌ Failed: {failed_downloads}")
    print(f"📝 Total processed: {len(filtered)}")

if __name__ == "__main__":
    main()