from pathlib import Path
import hashlib
import requests

CACHE_DIR = Path.home() / ".mangakoro" / "covers"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def image_bytes(url: str) -> bytes:
    if not url:
        return b""
    path = CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".jpg")
    if path.exists():
        return path.read_bytes()
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        path.write_bytes(response.content)
        return response.content
    except requests.RequestException:
        return b""