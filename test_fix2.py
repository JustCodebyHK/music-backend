import yt_dlp

ydl_opts = {
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'cookiefile': 'cookies.txt',
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    },
    'extractor_args': {
        'youtube': {
            'player_client': ['web', 'android'],
            'player_skip': ['configs', 'webpage'],
        }
    }
}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info('https://www.youtube.com/watch?v=ParFA9QU5EM', download=False)
    if not info:
        print('FAIL: no info')
    else:
        stream_url = None
        if 'url' in info:
            stream_url = info.get('url')
        elif info.get('requested_formats'):
            for fmt in info['requested_formats']:
                if fmt.get('acodec') != 'none' and fmt.get('url'):
                    stream_url = fmt['url']
                    break
        print('SUCCESS:', stream_url is not None)
        if stream_url:
            print('URL:', stream_url[:80])