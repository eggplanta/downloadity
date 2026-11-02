"""
Embeds a cover image in audio files
"""
import base64
import ssl
import urllib.request
from typing import Optional

import certifi
from mutagen.flac import Picture
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus

JPEG_MAGIC = b"\xff\xd8\xff"
FRONT_COVER = 3


def thumbnail_url(info: dict) -> Optional[str]:
    """
    Largest jpg, players can't show webp
    """
    thumbs = [
        t for t in info.get("thumbnails") or []
        if ".jpg" in t.get("url", "") and t.get("width")
    ]
    if thumbs:
        return max(thumbs, key=lambda t: t["width"])["url"]

    url = info.get("thumbnail")
    return url if url and ".jpg" in url else None


def embed_cover(path: str, url: str) -> None:
    data = _download(url)
    if not data.startswith(JPEG_MAGIC):
        raise ValueError("cover is not a jpeg")

    if path.endswith(".opus"):
        _embed_opus(path, data)
    else:
        _embed_m4a(path, data)


# Internal helpers

def _download(url: str) -> bytes:
    # Android Python lacks system certificates
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(url, timeout=10, context=context) as response:
        return response.read()


def _embed_m4a(path: str, data: bytes) -> None:
    audio = MP4(path)
    audio["covr"] = [MP4Cover(data, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


def _embed_opus(path: str, data: bytes) -> None:
    picture = Picture()
    picture.type = FRONT_COVER
    picture.mime = "image/jpeg"
    picture.data = data

    audio = OggOpus(path)
    audio["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]
    audio.save()
