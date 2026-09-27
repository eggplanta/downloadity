import yt_dlp
from . import spotify


def extract(url: str, flat: bool = False) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": flat,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        return {
            "type": "error",
            "message": str(e),
        }

    if info is None:
        return {
            "type": "error",
            "message": "Could not extract information from this URL.",
        }

    # Playlist
    if info.get("_type") == "playlist":
        entries = []

        for entry in info.get("entries", []):
            if not entry:
                continue

            if flat:
                entries.append(_extract_flat_item(entry))
            else:
                entries.append(_extract_item(entry))

        return {
            "type": "playlist",
            "title": info.get("title"),
            "count": len(entries),
            "entries": entries,
        }

    # Single Media
    if flat:
        return {
            "type": "video",
            **_extract_flat_item(info),
        }

    return {
        "type": "video",
        **_extract_item(info),
    }

def resolve(url: str) -> dict:

    if "open.spotify.com" in url:
        youtube_urls = spotify.extract(url)

        if not youtube_urls:
            return {
                "type": "error",
                "message": "Could not extract information from this URL.",
            }

        if len(youtube_urls) > 1:
            return _playlist_from_urls(youtube_urls)

        url = youtube_urls[0]

    return extract(url, flat=True)


def _playlist_from_urls(urls: list[str]) -> dict:
    return {
        "type": "playlist",
        "title": None,
        "count": len(urls),
        "entries": [
            {"id": None, "title": None, "url": u, "duration": None}
            for u in urls
        ],
    }

def _extract_flat_item(info: dict) -> dict:

    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "url": info.get("url") or info.get("webpage_url"),
        "duration": info.get("duration"),
    }


def _extract_item(info: dict) -> dict:

    formats = info.get("formats", [])

    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "webpage_url": info.get("webpage_url"),
        "audio": _get_audio_formats(formats),
        "video": _get_video_formats(formats),
        "ytdlp_info": info,
    }


def _get_audio_formats(formats: list) -> list:

    best_by_bitrate = {}

    for fmt in formats:
        if fmt.get("vcodec") != "none":
            continue

        bitrate = fmt.get("abr")
        if not bitrate:
            continue

        bitrate = round(bitrate)

        existing = best_by_bitrate.get(bitrate)
        if existing is None:
            best_by_bitrate[bitrate] = fmt
        else:
            existing_size = existing.get("filesize") or existing.get("filesize_approx") or 0
            new_size = fmt.get("filesize") or fmt.get("filesize_approx") or 0
            if new_size and (not existing_size or new_size < existing_size):
                best_by_bitrate[bitrate] = fmt

    result = []
    for bitrate in sorted(best_by_bitrate):
        fmt = best_by_bitrate[bitrate]
        result.append({
            "format_id": fmt.get("format_id"),
            "ext": fmt.get("ext"),
            "bitrate": bitrate,
            "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
        })

    return result


def _get_video_formats(formats: list) -> list:

    best_by_height = {}

    for fmt in formats:
        if fmt.get("vcodec") == "none":
            continue

        height = fmt.get("height")
        if not height or height < 144:
            continue

        existing = best_by_height.get(height)
        if existing is None:
            best_by_height[height] = fmt
        else:
            existing_tbr = existing.get("tbr") or 0
            new_tbr = fmt.get("tbr") or 0
            if new_tbr > existing_tbr:
                best_by_height[height] = fmt

    result = []
    for height in sorted(best_by_height):
        fmt = best_by_height[height]
        result.append({
            "format_id": fmt.get("format_id"),
            "ext": fmt.get("ext"),
            "height": height,
            "resolution": f"{height}p",
            "has_audio": fmt.get("acodec") != "none",
            "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
        })

    return result
