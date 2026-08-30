import os
import requests
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

# Private Cobalt Instance Configuration
COBALT_API_URL = os.getenv("COBALT_API_URL", "http://YOUR_SERVER_IP:9000/")
COBALT_API_KEY = os.getenv("COBALT_API_KEY", "YOUR_CUSTOM_SECRET_API_KEY")


def fetch_audio_from_cobalt(video_id: str) -> str:
    """Query self-hosted Cobalt instance for an MP3 audio stream URL."""
    payload = {
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "downloadMode": "audio",
        "audioFormat": "mp3"
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {COBALT_API_KEY}",
        "bypass-tunnel-reminder": "true"  # Bypasses localtunnel landing page
    }

    try:
        res = requests.post(COBALT_API_URL, json=payload, headers=headers, timeout=12)
        if res.status_code == 200:
            data = res.json()
            if "url" in data:
                return data["url"]
            elif data.get("status") == "redirect":
                return data.get("url")
        raise HTTPException(status_code=res.status_code, detail=f"Cobalt error: {res.text}")
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach private Cobalt node: {str(e)}")


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
    # Updated key version to bypass stale localhost cached URLs
    cache_key = f"stream_url_v2:{video_id}"

    # Check Redis cache
    try:
        cached_url = redis_client.get(cache_key)
        if cached_url:
            return {"video_id": video_id, "stream_url": cached_url, "cached": True}
    except redis.RedisError:
        pass

    # Extract via private Cobalt instance
    stream_url = fetch_audio_from_cobalt(video_id)

    # Cache stream URL (3 hours TTL)
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
    stream_data = get_stream_url(video_id)
    stream_url = stream_data["stream_url"]

    try:
        req = requests.get(stream_url, stream=True, timeout=15)
        return StreamingResponse(
            req.iter_content(chunk_size=1024 * 64),
            media_type="audio/mpeg",
            headers={"Content-Disposition": f"attachment; filename={video_id}.mp3"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stream download payload: {str(e)}")