import yt_dlp
from .throttle import throttle

AUDIO_BITRATES = (32, 48, 64, 96, 128, 160, 192, 256, 320)

# height -> long side of a 16:9 frame
VIDEO_LONG_SIDES = {
    144: 256,
    240: 426,
    360: 640,
    480: 854,
    720: 1280,
    1080: 1920,
    1440: 2560,
    2160: 3840,
    4320: 7680,
}


class SilentLogger:
    # Errors are returned, not printed
    def debug(self, msg):
        pass

    warning = error = debug


def extract(url: str, flat: str | bool = False) -> dict:
    """
    Single media comes with formats
    Playlists need flat="in_playlist"
    """
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": flat,
        "logger": SilentLogger(),
    }

    try:
        info = throttle.run(lambda: _extract_info(url, options))
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

            entries.append(_extract_flat_item(entry))

        return {
            "type": "playlist",
            "title": info.get("title"),
            "id": info.get("id"),
            "description": info.get("description"),
            "extractor_key": info.get("extractor_key"),
            "entries": entries,
        }

    # Single Media
    return {
        "type": "video",
        **_extract_item(info),
    }


def _extract_info(url: str, options: dict) -> dict:
    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False)


def _extract_flat_item(info: dict) -> dict:
    # Instagram carousels come fully extracted
    return {
        "title": info.get("title"),
        "url": info.get("url") or info.get("webpage_url"),
        "duration": info.get("duration"),
        "availability": info.get("availability"),
        "item": _extract_item(info) if info.get("formats") else None,
    }


def _extract_item(info: dict) -> dict:

    formats = info.get("formats", [])
    duration = info.get("duration")

    return {
        "duration": duration,
        "audio": _get_audio_formats(formats, duration),
        "video": _get_video_formats(formats, duration),
        "ytdlp_info": info,
    }


def _get_audio_formats(formats: list, duration) -> list:

    best_by_bitrate = {}

    for fmt in formats:
        if fmt.get("vcodec") != "none":
            continue

        abr = fmt.get("abr")
        if not abr:
            continue

        bitrate = _standard_bitrate(abr)

        existing = best_by_bitrate.get(bitrate)
        if existing is None:
            best_by_bitrate[bitrate] = fmt
        else:
            existing_size = _filesize(existing, duration) or 0
            new_size = _filesize(fmt, duration) or 0
            if new_size and (not existing_size or new_size < existing_size):
                best_by_bitrate[bitrate] = fmt

    result = []
    for bitrate in sorted(best_by_bitrate):
        fmt = best_by_bitrate[bitrate]
        result.append({
            "format_id": fmt.get("format_id"),
            "bitrate": bitrate,
            "filesize": _filesize(fmt, duration),
        })

    return result


def _get_video_formats(formats: list, duration) -> list:

    best_by_height = {}

    for fmt in formats:
        if fmt.get("vcodec") == "none":
            continue

        if not fmt.get("height") or fmt["height"] < 144:
            continue

        height = _standard_height(fmt)

        # Prefer formats that report their size
        existing = best_by_height.get(height)
        if existing is None or _video_rank(fmt) > _video_rank(existing):
            best_by_height[height] = fmt

    result = []
    for height in sorted(best_by_height):
        fmt = best_by_height[height]
        result.append({
            "format_id": fmt.get("format_id"),
            "height": height,
            "has_audio": fmt.get("acodec") != "none",
            "filesize": _filesize(fmt, duration),
        })

    return result


def _video_rank(fmt: dict) -> tuple:
    known_size = bool(fmt.get("filesize") or fmt.get("filesize_approx"))
    return (known_size, fmt.get("tbr") or 0)


def _standard_bitrate(abr: float) -> int:
    return min(AUDIO_BITRATES, key=lambda b: abs(b - abr))


def _standard_height(fmt: dict) -> int:
    width = fmt.get("width")
    height = fmt["height"]

    if width:
        long_side = max(width, height)
        return min(
            VIDEO_LONG_SIDES,
            key=lambda h: abs(VIDEO_LONG_SIDES[h] - long_side),
        )

    return min(VIDEO_LONG_SIDES, key=lambda h: abs(h - height))


def _filesize(fmt: dict, duration):
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if size:
        return size

    # Estimate from total bitrate (kbps)
    tbr = fmt.get("tbr")
    if tbr and duration:
        return int(tbr * 1000 / 8 * duration)

    return None
