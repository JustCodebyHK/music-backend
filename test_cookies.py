import yt_dlp

ydl = yt_dlp.YoutubeDL({'cookiefile': 'cookies.txt', 'quiet': False, 'no_warnings': False})
info = ydl.extract_info('https://www.youtube.com/watch?v=ParFA9QU5EM', download=False)

with open('debug.txt', 'w') as f:
    f.write('info: ' + str(info is not None))
    if info:
        f.write('\nkeys: ' + str(list(info.keys())))
        f.write('\nurl in info: ' + str('url' in info))
        f.write('\nformats: ' + str(len(info.get('formats', []))))