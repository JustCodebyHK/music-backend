import yt_dlp

ydl = yt_dlp.YoutubeDL({'cookiefile': 'cookies.txt'})
info = ydl.extract_info('https://www.youtube.com/watch?v=ParFA9QU5EM', download=False)

print('format (id):', info.get('format'))
print('format_id:', info.get('format_id'))
print()
print('requested_formats:', info.get('requested_formats'))
if info.get('requested_formats'):
    for f in info['requested_formats']:
        print('  format:', f.get('format_id'), 'url exists:', 'url' in f)
        if 'url' in f:
            print('  url:', f['url'][:80])