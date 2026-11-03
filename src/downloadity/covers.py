"""
Embeds a cover image in audio files
"""
import base64
import os
import ssl
import subprocess
import tempfile
import urllib.request
from typing import Optional

import certifi
from mutagen.flac import Picture
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus

from . import downloader

JPEG_MAGIC = b"\xff\xd8\xff"
FRONT_COVER = 3
WIDE_RATIO = 16 / 9
# Tag name -> MP4 atom
M4A_KEYS = {"title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb", "date": "\xa9day"}
YOUTUBE_THUMBS = ("maxresdefault", "hq720", "sddefault", "hqdefault")
# 4:3 thumbnails hide bars above and below
SQUARE_CROP = "crop=if(eq(iw*3\\,ih*4)\\,ih*3/4\\,min(iw\\,ih)):if(eq(iw*3\\,ih*4)\\,ih*3/4\\,min(iw\\,ih))"


def thumbnail_urls(info: dict) -> list[str]:
    """
    Jpg thumbnails, best first
    Signed links may serve webp instead
    """
    thumbs = [
        t for t in info.get("thumbnails") or []
        if ".jpg" in t.get("url", "") and t.get("width")
    ]
    # YouTube hides big ones from the list
    urls = []
    if (info.get("extractor_key") or "").startswith("Youtube"):
        urls = [f"https://i.ytimg.com/vi/{info.get('id')}/{name}.jpg" for name in YOUTUBE_THUMBS]

    if thumbs:
        return urls + [t["url"] for t in sorted(thumbs, key=_thumbnail_rank, reverse=True)]

    url = info.get("thumbnail")
    return urls + ([url] if url and ".jpg" in url else [])


def cover_image(info: dict, album_cover: Optional[str] = None) -> bytes:
    """
    Square jpeg, album cover or thumbnail
    """
    if album_cover:
        return _first_jpeg([album_cover])
    return _square(_first_jpeg(thumbnail_urls(info)))


def embed_tags(path: str, cover: Optional[bytes], tags: dict) -> None:
    """
    Cover plus title, artist, album, track, year
    """
    if path.endswith(".opus"):
        _embed_opus(path, cover, tags)
    else:
        _embed_m4a(path, cover, tags)


# Internal helpers

def _thumbnail_rank(thumb: dict) -> tuple:
    height = thumb.get("height") or 0
    wide = bool(height) and abs(thumb["width"] / height - WIDE_RATIO) < 0.05
    return ("sqp=" not in thumb["url"], wide, thumb["width"])


def _square(data: bytes) -> bytes:
    with tempfile.TemporaryDirectory(dir=downloader.TEMP_DIR) as folder:
        source = os.path.join(folder, "cover.jpg")
        output = os.path.join(folder, "square.jpg")
        with open(source, "wb") as f:
            f.write(data)

        subprocess.run(
            [
                downloader.FFMPEG, "-y", "-v", "error", "-i", source,
                "-vf", f"{SQUARE_CROP},format=yuvj420p",
                "-frames:v", "1", "-update", "1", "-q:v", "2", output,
            ],
            check=True,
            capture_output=True,
        )
        with open(output, "rb") as f:
            return f.read()


def _first_jpeg(urls: list[str]) -> bytes:
    for url in urls:
        try:
            data = _download(url)
        except OSError:
            continue
        if data.startswith(JPEG_MAGIC):
            return data
    raise ValueError("no jpeg cover")


def _download(url: str) -> bytes:
    # Android Python lacks system certificates
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(url, timeout=10, context=context) as response:
        return response.read()


def _embed_m4a(path: str, cover: Optional[bytes], tags: dict) -> None:
    audio = MP4(path)
    if cover:
        audio["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
    for key, value in tags.items():
        if key == "tracknumber":
            audio["trkn"] = [(int(value), 0)]
        else:
            audio[M4A_KEYS[key]] = [value]
    audio.save()


def _embed_opus(path: str, cover: Optional[bytes], tags: dict) -> None:
    audio = OggOpus(path)
    if cover:
        picture = Picture()
        picture.type = FRONT_COVER
        picture.mime = "image/jpeg"
        picture.data = cover
        audio["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]
    for key, value in tags.items():
        audio[key] = [value]
    audio.save()
