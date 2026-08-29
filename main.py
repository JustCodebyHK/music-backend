import os
import shutil
import requests
import yt_dlp
import redis
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from ytmusicapi import YTMusic
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Personal Music Service")
ytm = YTMusic()

# Enable CORS for frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Redis client
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

# Cookie resolution paths
RENDER_SECRET_COOKIE_PATH = "/etc/secrets/cookies.txt"
WRITABLE_COOKIE_PATH = "/tmp/cookies.txt"
LOCAL_COOKIE_PATH = os.path.join(os.path.dirname(__file__), "cookies.txt")

def get_cookie_path():
    """Copy Render Secret File to /tmp so yt-dlp gets write access without crash."""
    if os.path.exists(RENDER_SECRET_COOKIE_PATH):
        try:
            shutil.copyfile(RENDER_SECRET_COOKIE_PATH, WRITABLE_COOKIE_PATH)
            return WRITABLE_COOKIE_PATH
        except Exception:
            return RENDER_SECRET_COOKIE_PATH
    elif os.path.exists(LOCAL_COOKIE_PATH):
        return LOCAL_COOKIE_PATH
    return None

def get_yt_dlp_options():
    opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        # Force yt-dlp to rely on standard web/android extractor clients without header overrides
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android'],
                'player_skip': ['js', 'configs']
            }
        }
    }
    
    cookie_path = get_cookie_path()
    if cookie_path:
        opts['cookiefile'] = cookie_path

    return opts

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
    
    # 1. Check Redis cache
    try:
        cached_url = redis_client.get(cache_key)
        if cached_url:
            return {"video_id": video_id, "stream_url": cached_url, "cached": True}
    except redis.RedisError:
        pass

    # 2. Extract live stream URL
    ydl_opts = get_yt_dlp_options()
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info or "url" not in info:
                raise HTTPException(status_code=404, detail="Audio stream URL not found for this video.")
            
            stream_url = info.get("url")
            
            try:
                redis_client.setex(cache_key, 10800, stream_url)  # Cache for 3 hours
            except redis.RedisError:
                pass

            return {
                "video_id": video_id,
                "stream_url": stream_url,
                "expires_at": info.get("url_valid_until"),
                "cached": False
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract stream: {str(e)}")

@app.get("/api/download/{video_id}")
def download_audio(video_id: str):
    ydl_opts = get_yt_dlp_options()
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info or "url" not in info:
                raise HTTPException(status_code=404, detail="Could not extract audio download link from YouTube.")
                
            stream_url = info.get("url")
            headers = info.get("http_headers", {})

        req = requests.get(stream_url, headers=headers, stream=True)
        return StreamingResponse(
            req.iter_content(chunk_size=1024 * 64), 
            media_type="audio/mp4",
            headers={"Content-Disposition": f"attachment; filename={video_id}.m4a"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download audio: {str(e)}")

@app.get("/api/health/cookies")
def check_cookie_health():
    cookie_path = get_cookie_path()
    if not cookie_path:
        return {"status": "warning", "message": "cookies.txt file not found"}

    test_video_id = "dQw4w9WgXcQ"
    ydl_opts = get_yt_dlp_options()
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={test_video_id}", download=False)
            if not info:
                return {"status": "error", "message": "Extraction returned None"}
        return {"status": "ok", "message": f"Cookies are valid and active (Source: {cookie_path})."}
    except Exception as e:
        return {"status": "invalid_or_expired", "error": str(e), "path": cookie_path}