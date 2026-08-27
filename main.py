import os
import json
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

RENDER_SECRET_COOKIE_PATH = "/etc/secrets/cookies.txt"
WRITABLE_COOKIE_PATH = "/tmp/cookies.txt"
LOCAL_COOKIE_PATH = os.path.join(os.path.dirname(__file__), "cookies.txt")

def get_cookie_path():
    if os.path.exists(RENDER_SECRET_COOKIE_PATH):
        try:
            shutil.copyfile(RENDER_SECRET_COOKIE_PATH, WRITABLE_COOKIE_PATH)
            return WRITABLE_COOKIE_PATH
        except Exception as e:
            print(f"Error copying secret cookies file: {e}")
            return RENDER_SECRET_COOKIE_PATH
    elif os.path.exists(LOCAL_COOKIE_PATH):
        return LOCAL_COOKIE_PATH
    return None

def get_yt_dlp_options():
    opts = {
        # Omit 'format' so yt-dlp automatically selects the default working stream
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
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
    
    try:
        cached_url = redis_client.get(cache_key)
        if cached_url:
            return {
                "video_id": video_id,
                "stream_url": cached_url,
                "cached": True
            }
    except redis.RedisError:
        pass

    ydl_opts = get_yt_dlp_options()
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=404, detail="Audio stream URL not found for this video.")
            
            stream_url = None
            if "url" in info:
                stream_url = info.get("url")
            elif info.get("requested_formats"):
                for fmt in info["requested_formats"]:
                    if fmt.get("acodec") != "none" and fmt.get("url"):
                        stream_url = fmt["url"]
                        break
            
            if not stream_url:
                raise HTTPException(status_code=404, detail="Audio stream URL not found for this video.")
            
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
            
            if not info:
                raise HTTPException(status_code=404, detail="Could not extract audio download link from YouTube.")
                
            stream_url = None
            if "url" in info:
                stream_url = info.get("url")
            elif info.get("requested_formats"):
                for fmt in info["requested_formats"]:
                    if fmt.get("acodec") != "none" and fmt.get("url"):
                        stream_url = fmt["url"]
                        headers = fmt.get("http_headers", {})
                        break
            
            if not stream_url:
                raise HTTPException(status_code=404, detail="Could not extract audio download link from YouTube.")

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