import yt_dlp

ydl = yt_dlp.YoutubeDL({'cookiefile': 'cookies.txt'})
info = ydl.extract_info('https://www.youtube.com/watch?v=ParFA9QU5EM', download=False)

if info and 'format' in info:
    fmt = info['format']
    print('format keys:', list(fmt.keys()))
    print('format url exists:', 'url' in fmt)
    if 'url' in fmt:
        print('url:', fmt['url'][:80])