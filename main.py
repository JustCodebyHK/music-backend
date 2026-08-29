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

# Redundant public extraction nodes
COBALT_INSTANCES = [
    "https://cobalt-api.kwippy.com",
    "https://api.cobalt.tools",
    "https://cobalt.api.scie.dev"
]

PIPED_INSTANCES = [
    "https://pipedapi.kavin.rocks",
    "https://api.piped.privacydev.net",
    "https://pipedapi.mha.fi"
]

INVIDIOUS_INSTANCES = [
    "https://invidious.nerdvpn.de",
    "https://inv.tux.pizza",
    "https://vid.pugices.com"
]


def resolve_via_cobalt(video_url: str) -> str:
    """Resolve stream URL using Cobalt nodes."""
    payload = {"url": video_url, "downloadMode": "audio", "audioFormat": "mp3"}
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    for instance in COBALT_INSTANCES:
        try:
            res = requests.post(instance, json=payload, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if "url" in data:
                    return data["url"]
        except Exception:
            continue
    return None


def resolve_via_piped(video_id: str) -> str:
    """Resolve stream URL using Piped API nodes."""
    for instance in PIPED_INSTANCES:
        try:
            res = requests.get(f"{instance}/streams/{video_id}", timeout=5)
            if res.status_code == 200:
                data = res.json()
                audio_streams = data.get("audioStreams", [])
                if audio_streams:
                    return audio_streams[0].get("url")
        except Exception:
            continue
    return None


def resolve_via_invidious(video_id: str) -> str:
    """Resolve stream URL using Invidious API nodes."""
    for instance in INVIDIOUS_INSTANCES:
        try:
            res = requests.get(f"{instance}/api/v1/videos/{video_id}", timeout=5)
            if res.status_code == 200:
                data = res.json()
                adaptive_formats = data.get("adaptiveFormats", [])
                # Filter for pure audio streams
                audio_streams = [f for f in adaptive_formats if f.get("type", "").startswith("audio/")]
                if audio_streams:
                    return audio_streams[0].get("url")
        except Exception:
            continue
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

    # 2. Sequential failover across Cobalt -> Piped -> Invidious
    stream_url = resolve_via_cobalt(video_url)
    
    if not stream_url:
        stream_url = resolve_via_piped(video_id)
        
    if not stream_url:
        stream_url = resolve_via_invidious(video_id)

    if not stream_url:
        raise HTTPException(status_code=502, detail="All extraction nodes failed to return a stream URL.")

    # 3. Cache valid stream URL (30 minutes TTL to account for token expiration)
    try:
        redis_client.setex(cache_key, 1800, stream_url)
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
        raise HTTPException(status_code=500, detail=f"Failed to stream download: {str(e)}")