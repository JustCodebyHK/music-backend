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

# Initialize Redis client
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

# List of public Cobalt instances for automatic failover
COBALT_INSTANCES = [
    "https://cobalt-api.kwippy.com",
    "https://api.cobalt.tools",
]

# Public Piped API instance for secondary failover
PIPED_API_URL = "https://pipedapi.kavin.rocks"


def fetch_stream_via_cobalt(video_url: str) -> str:
    """Attempt to resolve a direct stream URL using Cobalt instances."""
    payload = {
        "url": video_url,
        "downloadMode": "audio",
        "audioFormat": "mp3"
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    for instance in COBALT_INSTANCES:
        try:
            res = requests.post(instance, json=payload, headers=headers, timeout=8)
            if res.status_code == 200:
                data = res.json()
                if "url" in data:
                    return data["url"]
        except Exception:
            continue
    return None


def fetch_stream_via_piped(video_id: str) -> str:
    """Fallback resolution via Piped API."""
    try:
        res = requests.get(f"{PIPED_API_URL}/streams/{video_id}", timeout=8)
        if res.status_code == 200:
            data = res.json()
            audio_streams = data.get("audioStreams", [])
            if audio_streams:
                # Get highest quality audio stream
                return audio_streams[0].get("url")
    except Exception:
        pass
    return None


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

    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # 2. Try Cobalt primary resolution
    stream_url = fetch_stream_via_cobalt(video_url)

    # 3. Fallback to Piped API
    if not stream_url:
        stream_url = fetch_stream_via_piped(video_id)

    if not stream_url:
        raise HTTPException(status_code=502, detail="Unable to extract stream from extraction providers.")

    # 4. Cache valid stream URL (1 hour TTL)
    try:
        redis_client.setex(cache_key, 3600, stream_url)
    except redis.RedisError:
        pass

    return {
        "video_id": video_id,
        "stream_url": stream_url,
        "cached": False
    }


@app.get("/api/download/{video_id}")
def download_audio(video_id: str):
    # Fetch stream URL using helper logic
    stream_data = get_stream_url(video_id)
    stream_url = stream_data["stream_url"]

    try:
        req = requests.get(stream_url, stream=True)
        return StreamingResponse(
            req.iter_content(chunk_size=1024 * 64),
            media_type="audio/mpeg",
            headers={"Content-Disposition": f"attachment; filename={video_id}.mp3"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stream download: {str(e)}")