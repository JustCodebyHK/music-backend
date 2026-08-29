import yt_dlp
import main

print("Testing real YouTube download with fixed cookies...")
ydl_opts = main.get_yt_dlp_options()

url = "https://www.youtube.com/watch?v=rEhY11e6BCs"
print(f"URL: {url}")

try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info:
            print(f"✓ SUCCESS: Got info for video")
            print(f"  Title: {info.get('title', 'N/A')[:60]}")
            print(f"  Duration: {info.get('duration', 'N/A')}s")
            if 'url' in info:
                print(f"  Stream URL: {info['url'][:80]}...")
            elif info.get('requested_formats'):
                print(f"  Found {len(info['requested_formats'])} formats")
        else:
            print("✗ No info returned")
except Exception as e:
    print(f"✗ FAILED: {str(e)[:400]}")
