import yt_dlp
import main

opts = main.get_yt_dlp_options()
print('Testing yt-dlp with fixed cookies...')
print('Cookie file:', opts.get('cookiefile'))

try:
    with yt_dlp.YoutubeDL(opts) as ydl:
        pass
    print('✓ SUCCESS: yt-dlp can load the cookies file!')
except Exception as e:
    print('✗ FAILED:', str(e)[:300])
