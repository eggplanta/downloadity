import yt_dlp
from .throttle import MAX_ATTEMPTS, throttle

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

    def warning(self, msg):
        pass

    error = warning


def extract(url: str, flat: str | bool = False, audio_only: bool = False, attempts: int = MAX_ATTEMPTS) -> dict:
    """
    Single media comes with formats
    Playlists need flat="in_playlist"
    Audio only skips the HLS request
    """
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": flat,
        "logger": SilentLogger(),
    }
    # HLS only adds video formats
    if audio_only:
        options["extractor_args"] = {"youtube": {"skip": ["hls"]}}

    try:
        info = throttle.run(lambda: _extract_info(url, options), attempts)
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
        "id": info.get("id"),
        "site": info.get("ie_key") or info.get("extractor_key"),
        "title": info.get("title"),
        "url": info.get("url") or info.get("webpage_url"),
        "duration": info.get("duration"),
        "availability": info.get("availability"),
        "item": _extract_item(info) if info.get("formats") else None,
    }


def _extract_item(info: dict) -> dict:

    formats = _without_dubs(info.get("formats", []))
    duration = info.get("duration")

    return {
        "duration": duration,
        "audio": _get_audio_formats(formats, duration),
        "video": _get_video_formats(formats, duration),
        "ytdlp_info": info,
    }


def _without_dubs(formats: list) -> list:
    # Original audio ranks highest
    ranks = [_language_rank(fmt) for fmt in formats if fmt.get("acodec") != "none"]
    best = max(ranks, default=-1)
    return [fmt for fmt in formats if fmt.get("acodec") == "none" or _language_rank(fmt) == best]


def _language_rank(fmt: dict) -> int:
    rank = fmt.get("language_preference")
    return -1 if rank is None else rank


def _get_audio_formats(formats: list, duration) -> list:
    """
    Every audio-only format
    formats.py picks per user choice
    """
    return [
        {
            "format_id": fmt.get("format_id"),
            "abr": fmt["abr"],
            "bitrate": _standard_bitrate(fmt["abr"]),
            "filesize": _filesize(fmt, duration),
            "codec": _audio_codec(fmt),
            "drc": bool(fmt.get("has_drc") or "drc" in str(fmt.get("format_id"))),
        }
        for fmt in formats
        if fmt.get("vcodec") == "none" and fmt.get("abr")
    ]


def _audio_codec(fmt: dict) -> str:
    # Other codecs always get converted
    acodec = fmt.get("acodec") or ""
    for prefix, codec in (("opus", "opus"), ("mp4a", "m4a"), ("mp3", "mp3"), ("flac", "flac")):
        if acodec.startswith(prefix):
            return codec
    return "other"


def _get_video_formats(formats: list, duration) -> list:
    """
    Every video format, heights standardized
    """
    return [
        {
            "format_id": fmt.get("format_id"),
            "height": _standard_height(fmt),
            "codec": _video_codec(fmt),
            "tbr": fmt.get("tbr") or 0,
            "hls": "m3u8" in (fmt.get("protocol") or ""),
            "has_audio": fmt.get("acodec") != "none",
            "filesize": _filesize(fmt, duration),
        }
        for fmt in formats
        if fmt.get("vcodec") != "none" and fmt.get("height") and fmt["height"] >= 144
    ]


def _video_codec(fmt: dict) -> str:
    vcodec = fmt.get("vcodec") or ""
    for prefixes, codec in ((("avc1", "h264"), "avc"), (("vp9", "vp09"), "vp9"), (("av01",), "av1"), (("hev", "hvc", "h265"), "hevc")):
        if vcodec.startswith(prefixes):
            return codec
    return "other"


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
