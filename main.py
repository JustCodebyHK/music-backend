import os
import requests
import redis
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from ytmusicapi import YTMusic
from fastapi.middleware.cors import CORSMiddleware
import urllib3

# Strip any inherited proxy env vars so requests/yt-dlp connect direct.
# A 400 from a CONNECT tunnel usually means a misconfigured system proxy.
for _p in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "REQUEST_PROXY"):
    os.environ.pop(_p, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

# Force requests to disable proxy completely
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["PYTHONHTTPSVERIFY"] = "0"

# Disable urllib3 proxy warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="Personal Music Service")

# Create a requests session that explicitly disables proxies
requests_session = requests.Session()
requests_session.proxies = {"http": "", "https": ""}
requests_session.trust_env = False  # Do NOT trust environment proxy settings

ytm = YTMusic(
    requests_session=requests_session,
    proxies={"http": "", "https": ""}  # Force no proxy
)

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

COBALT_API_URL = os.getenv("COBALT_API_URL", "").rstrip("/")
COBALT_API_KEY = os.getenv("COBALT_API_KEY", "")


def fetch_audio_from_cobalt(video_id: str) -> str:
    """Query local Cobalt instance via Cloudflare Tunnel for raw audio stream."""
    payload = {
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "downloadMode": "audio",
        "audioFormat": "mp3"
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {COBALT_API_KEY}"
    }

    try:
        res = requests_session.post(COBALT_API_URL, json=payload, headers=headers, timeout=20)
        if res.status_code == 200:
            data = res.json()
            if "url" in data:
                return data["url"]
            elif data.get("status") == "redirect":
                return data.get("url")
            elif data.get("status") == "picker" and "picker" in data:
                return data["picker"][0]["url"]
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
    cache_key = f"stream_url_v11:{video_id}"

    try:
        cached_url = redis_client.get(cache_key)
        if cached_url:
            return {"video_id": video_id, "stream_url": cached_url, "cached": True}
    except redis.RedisError:
        pass

    stream_url = fetch_audio_from_cobalt(video_id)

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
    """Redirect client browser directly to Cobalt stream URL to avoid proxy corruption."""
    stream_data = get_stream_url(video_id)
    stream_url = stream_data.get("stream_url")

    if not stream_url:
        raise HTTPException(status_code=404, detail="Stream URL resolution failed.")

    return RedirectResponse(url=stream_url, status_code=307)
