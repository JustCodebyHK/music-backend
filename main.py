import os
import requests
import yt_dlp
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from ytmusicapi import YTMusic

app = FastAPI(title="Music API")
ytm = YTMusic()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOCAL_COOKIE_PATH = os.path.join(os.path.dirname(__file__), "cookies.txt")


def sanitize_proxy_env():
    if os.getenv("PROXY_URL"):
        return
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)


def get_proxy():
    proxy = os.getenv("PROXY_URL")
    return proxy.strip() if proxy and proxy.strip() else None


def get_cookie_path():
    if os.path.exists(LOCAL_COOKIE_PATH):
        return LOCAL_COOKIE_PATH
    return None


def get_yt_dlp_options():
    sanitize_proxy_env()

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["tv", "web_embedded", "android"],
            }
        },
        "format": "bestaudio/best",
    }

    cookie_path = get_cookie_path()
    if cookie_path:
        opts["cookiefile"] = cookie_path

    proxy = get_proxy()
    if proxy:
        opts["proxy"] = proxy

    return opts


@app.get("/")
def read_root():
    return {"status": "ok", "service": "music-api"}


@app.get("/api/search")
def search_music(q: str = Query(..., description="Search query")):
    try:
        results = ytm.search(q, filter="songs")
        songs = []
        for item in results:
            songs.append(
                {
                    "video_id": item.get("videoId"),
                    "title": item.get("title"),
                    "artist": ", ".join([a["name"] for a in item.get("artists", [])]),
                    "album": item.get("album", {}).get("name") if item.get("album") else None,
                    "duration": item.get("duration"),
                    "thumbnail": item.get("thumbnails", [{}])[-1].get("url"),
                }
            )
        return {"results": songs}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/stream_url/{video_id}")
def get_stream_url(video_id: str):
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

            return {
                "video_id": video_id,
                "stream_url": stream_url,
                "expires_at": info.get("url_valid_until"),
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to extract stream: {str(exc)}")


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
            headers = {}
            if "url" in info:
                stream_url = info.get("url")
                headers = info.get("http_headers", {})
            elif info.get("requested_formats"):
                for fmt in info["requested_formats"]:
                    if fmt.get("acodec") != "none" and fmt.get("url"):
                        stream_url = fmt["url"]
                        headers = fmt.get("http_headers", {})
                        break

            if not stream_url:
                raise HTTPException(status_code=404, detail="Could not extract audio download link from YouTube.")

        session = requests.Session()
        session.trust_env = False
        response = session.get(stream_url, headers=headers, stream=True)
        response.raise_for_status()

        return StreamingResponse(
            response.iter_content(chunk_size=1024 * 64),
            media_type="audio/mp4",
            headers={"Content-Disposition": f"attachment; filename={video_id}.m4a"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to download audio: {str(exc)}")