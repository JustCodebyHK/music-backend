import os
import json
import requests
import yt_dlp
import redis
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from ytmusicapi import YTMusic

app = FastAPI(title="Personal Music Service")
ytm = YTMusic()

# Initialize Redis client (Connecting to localhost by default)
# Adjust host/port if Redis is running elsewhere (e.g., inside Docker)
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

COOKIE_FILE_PATH = os.path.join(os.path.dirname(__file__), "cookies.txt")

def get_yt_dlp_options():
    opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'js_runtimes': {'deno': {}},
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'mweb']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }
    
    if os.path.exists(COOKIE_FILE_PATH):
        opts['cookiefile'] = COOKIE_FILE_PATH

    return opts

def remove_file(path: str):
    """Helper function for background cleanup of disk files."""
    if os.path.exists(path):
        os.remove(path)

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
    cache_key = f"stream_url:{video_id}"
    
    # 1. Check Redis cache first
    try:
        cached_url = redis_client.get(cache_key)
        if cached_url:
            return {
                "video_id": video_id,
                "stream_url": cached_url,
                "cached": True
            }
    except redis.RedisError:
        pass  # Fall back to live extraction if Redis is unreachable

    # 2. Extract live stream URL if not cached
    ydl_opts = get_yt_dlp_options()
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get("url")
            
            # Cache the extracted URL for 3 hours (10800 seconds)
            try:
                redis_client.setex(cache_key, 10800, stream_url)
            except redis.RedisError:
                pass

            return {
                "video_id": video_id,
                "stream_url": stream_url,
                "expires_at": info.get("url_valid_until"),
                "cached": False
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

@app.get("/api/health/cookies")
def check_cookie_health():
    """Endpoint to check if the cookies.txt file exists and is functioning."""
    if not os.path.exists(COOKIE_FILE_PATH):
        return {"status": "warning", "message": "cookies.txt file not found"}

    test_video_id = "dQw4w9WgXcQ"  # Public test video
    ydl_opts = get_yt_dlp_options()
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(f"https://www.youtube.com/watch?v={test_video_id}", download=False)
        return {"status": "ok", "message": "Cookies are valid and active."}
    except Exception as e:
        return {"status": "invalid_or_expired", "error": str(e)}