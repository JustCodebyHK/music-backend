"""Test each YouTube player client individually to find which one works
from this server's IP. Run:  python test_clients.py <video_id>
"""
import sys
import yt_dlp

VIDEO = sys.argv[1] if len(sys.argv) > 1 else "Yme6ZSHBb7E"

# Client families: the "web"/"mweb" clients need a PO token; the android/ios/tv
# and *_embedded clients use API keys and usually DON'T need a PO token.
CLIENTS = [
    "web",
    "web_embedded",
    "mweb",
    "android",
    "android_vr",
    "android_music",
    "ios",
    "tv",
    "tv_embedded",
]

def try_client(client: str, cookie: str | None) -> str:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {"youtube": {"player_client": [client]}},
        "format": "bestaudio/best",
    }
    if cookie:
        opts["cookiefile"] = cookie
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={VIDEO}", download=False
            )
        if not info:
            return "NO INFO"
        url = info.get("url") or (
            info["requested_formats"][0].get("url")
            if info.get("requested_formats")
            else None
        )
        return "OK" if url else "NO URL"
    except Exception as e:
        return f"ERR: {str(e)[:120]}"


if __name__ == "__main__":
    import os
    cookie = sys.argv[2] if len(sys.argv) > 2 else None
    if not cookie:
        for p in ("/etc/secrets/cookies.txt", "cookies.txt"):
            if os.path.exists(p):
                cookie = p
                break
    print(f"video={VIDEO}  cookiefile={cookie}\n")
    for c in CLIENTS:
        print(f"{c:18} -> {try_client(c, cookie)}")