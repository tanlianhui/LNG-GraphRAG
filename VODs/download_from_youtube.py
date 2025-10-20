import yt_dlp
import os

def download_youtube_playlist(playlist_url, output_path="./VODs/%(title)s.mp4"):
    """
    Downloads a YouTube playlist using yt-dlp.

    Args:
        playlist_url (str): The URL of the YouTube playlist.
        output_path (str): The output file template (default: './downloads/%(title)s.%(ext)s')
    """
    if os.path.exists(output_path):
        print(f"File {output_path} already exists")
        return

    ydl_opts = {
        "outtmpl": output_path,
        "ignoreerrors": True,
        "format": "bestaudio/best",
        "noplaylist": False,  # Ensure playlists are downloaded as playlists
        "extract_flat": False,  # Download actual videos, not just metadata
        "cookiefile": "www.youtube.com_cookies.txt",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([playlist_url])

for i in [
    "https://www.youtube.com/watch?v=G09iuBRfyuQ&list=PLkY58pTw5wdOJWj6p7aoqW6OrVQueTRMI", # 2018
    "https://www.youtube.com/watch?v=pTOut8XQaCo&list=PLkY58pTw5wdNzM9vub2OHy0HGdZJVRfIG", # 2019
    "https://www.youtube.com/watch?v=c4ghCCKjE1Y&list=PLkY58pTw5wdMJncs4x82FNx0qc0xkyP9b", # 實況存檔    
    ]:
    download_youtube_playlist(i)