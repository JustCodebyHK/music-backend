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

RENDER_SECRET_TOKEN_PATH = "/etc/secrets/youtube_oauth2.json"
WRITABLE_TOKEN_PATH = "/tmp/youtube_oauth2.json"
LOCAL_TOKEN_PATH = os.path.join(os.path.dirname(__file__), "youtube_oauth2.json")

def get_oauth2_token_path():
    """Copy Render Secret OAuth2 token to /tmp for write access."""
    if os.path.exists(RENDER_SECRET_TOKEN_PATH):
        try:
            shutil.copyfile(RENDER_SECRET_TOKEN_PATH, WRITABLE_TOKEN_PATH)
            return WRITABLE_TOKEN_PATH
        except Exception:
            return RENDER_SECRET_TOKEN_PATH
    elif os.path.exists(LOCAL_TOKEN_PATH):
        return LOCAL_TOKEN_PATH
    return None

def get_yt_dlp_options():
    token_path = get_oauth2_token_path()
    
    opts = {
        'format': 'ba/b/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'username': 'oauth2',
        'extractor_args': {
            'youtube': {
                'player_client': ['tv']
            }
        }
    }
    
    if token_path:
        # Pass token file location directly and via extractor arguments for full plugin compatibility
        opts['oauth2_token_file'] = token_path
        opts['extractor_args']['youtube']['oauth2_token_file'] = token_path

    return opts

@app.get("/api/health/oauth2")
def check_oauth2_health():
    token_path = get_oauth2_token_path()
    if not token_path or not os.path.exists(token_path):
        return {
            "status": "missing",
            "message": "OAuth2 token file not found at /etc/secrets/youtube_oauth2.json or local path."
        }
    
    return {
        "status": "ok",
        "message": "OAuth2 token file exists and is copied to writable path.",
        "path": token_path
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
    cache_key = f"stream_url:{video_id}"
    
    try:
        cached_url = redis_client.get(cache_key)
        if cached_url:
            return {"video_id": video_id, "stream_url": cached_url, "cached": True}
    except redis.RedisError:
        pass

    ydl_opts = get_yt_dlp_options()
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info or "url" not in info:
                raise HTTPException(status_code=404, detail="Audio stream URL not found.")
            
            stream_url = info.get("url")
            
            try:
                redis_client.setex(cache_key, 10800, stream_url)
            except redis.RedisError:
                pass

            return {
                "video_id": video_id,
                "stream_url": stream_url,
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
                raise HTTPException(status_code=404, detail="Could not extract stream link.")
                
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