import os
import requests
import yt_dlp
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from ytmusicapi import YTMusic

app = FastAPI(title="Personal Music Service")
ytm = YTMusic()

def get_yt_dlp_options():
    return {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        # Force YouTube Music's native Android client payload
        'extractor_args': {
            'youtube': {
                'player_client': ['android_music', 'android'],
                'player_skip': ['webpage', 'configs', 'js']
            }
        },
        'http_headers': {
            'User-Agent': 'com.google.android.apps.youtube.music/6.41.52 (Linux; U; Android 14; en_US)',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }

@app.get("/")
def read_root():
    return {"status": "Backend service is live"}

@app.get("/api/search")
def search_music(q: str = Query(..., description="Search query")):
    try:
        results = ytm.search(q, filter="songs")
        songs = []
        for item in results:
            songs.append({
                "video_id": item.get("videoId"),
                "title": item.get("title"),
                "artist": ", ".join([a["name"] for a in item.get("artists", [])]),
                "album": item.get("album", {}).get("name") if item.get("album") else None,
                "duration": item.get("duration"),
                "thumbnail": item.get("thumbnails", [{}])[-1].get("url")
            })
        return {"results": songs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stream_url/{video_id}")
def get_stream_url(video_id: str):
    ydl_opts = get_yt_dlp_options()
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "video_id": video_id,
                "stream_url": info.get("url"),
                "expires_at": info.get("url_valid_until")
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract stream: {str(e)}")

@app.get("/api/download/{video_id}")
def download_audio(video_id: str):
    ydl_opts = get_yt_dlp_options()
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get("url")
            headers = info.get("http_headers", {})

        req = requests.get(stream_url, headers=headers, stream=True)
        return StreamingResponse(
            req.iter_content(chunk_size=1024 * 64), 
            media_type="audio/mp4",
            headers={"Content-Disposition": f"attachment; filename={video_id}.m4a"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download audio: {str(e)}")