import os
import subprocess
import redis
import requests
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

# Cloudflare Tunnel base URL (e.g., https://corners-editors-seeker-airplane.trycloudflare.com/)
TUNNEL_URL = os.getenv("COBALT_API_URL", "").rstrip("/")


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
    cache_key = f"stream_url_v9:{video_id}"

    try:
        cached_url = redis_client.get(cache_key)
        if cached_url:
            return {"video_id": video_id, "stream_url": cached_url, "cached": True}
    except redis.RedisError:
        pass

    # Extract audio stream using yt-dlp
    cmd = [
        "yt-dlp",
        "-g",
        "-f", "ba[ext=m4a]/ba",
        f"https://www.youtube.com/watch?v={video_id}"
    ]
    
    # Route request through Cloudflare Tunnel proxy if configured
    if TUNNEL_URL:
        cmd.extend(["--proxy", TUNNEL_URL])

    try:
        stream_url = subprocess.check_output(cmd, stderr=subprocess.PIPE).decode('utf-8').strip()
        if not stream_url:
            raise Exception("yt-dlp returned an empty stream URL")
    except subprocess.CalledProcessError as e:
        # Fallback without proxy if tunnel proxy refuses socket forwarding
        try:
            cmd_direct = ["yt-dlp", "-g", "-f", "ba[ext=m4a]/ba", f"https://www.youtube.com/watch?v={video_id}"]
            stream_url = subprocess.check_output(cmd_direct, stderr=subprocess.PIPE).decode('utf-8').strip()
        except Exception:
            raise HTTPException(status_code=500, detail=f"Extraction failed: {e.stderr.decode('utf-8')}")

    try:
        redis_client.setex(cache_key, 10800, stream_url)
    except redis.RedisError:
        pass

    return {
        "video_id": video_id,
        "stream_url": stream_url,
        "cached": False
    }


@app.get("/api/download/{video_id}")
def download_audio(video_id: str):
    """Stream raw audio stream directly to client via chunk generator."""
    stream_data = get_stream_url(video_id)
    stream_url = stream_data.get("stream_url")

    if not stream_url:
        raise HTTPException(status_code=404, detail="Stream URL resolution failed.")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    try:
        req = requests.get(stream_url, headers=headers, stream=True, timeout=30)
        
        if req.status_code != 200:
            raise HTTPException(status_code=req.status_code, detail="Direct stream payload failed.")

        def iterfile():
            for chunk in req.iter_content(chunk_size=1024 * 64):
                if chunk:
                    yield chunk

        return StreamingResponse(
            iterfile(),
            media_type="audio/mp4",
            headers={
                "Content-Disposition": f'attachment; filename="{video_id}.m4a"'
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Streaming error: {str(e)}")