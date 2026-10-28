import copy
import os
from typing import Optional

import yt_dlp

from .extractor import SilentLogger
from .formats import AudioQuality, VideoQuality


def download_audio(
    url: str,
    quality: AudioQuality,
    output_dir: str = ".",
    on_progress=None,
    filename: Optional[str] = None,
    info: Optional[dict] = None,
) -> dict:
    outtmpl = _outtmpl(output_dir, filename)

    options = {
        "quiet": True,
        "no_warnings": True,
        "logger": SilentLogger(),
        "format": quality.format_id,
        "outtmpl": outtmpl,

        "retries": 3,
        "fragment_retries": 3,
        "retry_sleep_functions": {
            "http": lambda n: min(2 ** (n - 1), 20),
            "fragment": lambda n: min(2 ** (n - 1), 20),
        },

        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(quality.bitrate),
            }
        ],
    }

    return _run_download(
        url,
        options,
        on_progress=on_progress,
        info=info,
    )


def download_video(
    url: str,
    quality: VideoQuality,
    output_dir: str = ".",
    on_progress=None,
    filename: Optional[str] = None,
    info: Optional[dict] = None,
) -> dict:
    outtmpl = _outtmpl(output_dir, filename)

    options = {
        "quiet": True,
        "no_warnings": True,
        "logger": SilentLogger(),
        "format": quality.download_format_id,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",

        "retries": 3,
        "fragment_retries": 3,
        "retry_sleep_functions": {
            "http": lambda n: min(2 ** (n - 1), 20),
            "fragment": lambda n: min(2 ** (n - 1), 20),
        },
    }

    return _run_download(
        url,
        options,
        on_progress=on_progress,
        info=info,
    )


def _outtmpl(output_dir: str, filename: Optional[str]) -> str:
    name = filename.replace("%", "%%") if filename else "%(title)s"
    return os.path.join(output_dir, f"{name}.%(ext)s")


def _run_download(
    url: str,
    options: dict,
    on_progress=None,
    max_retries: int = 2,
    info: Optional[dict] = None,
) -> dict:
    if on_progress:
        options["progress_hooks"] = [on_progress]

    for attempt in range(max_retries + 1):
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                # Embedded items have no page to re-extract
                if info:
                    ydl.process_ie_result(copy.deepcopy(info), download=True)
                else:
                    ydl.extract_info(url, download=True)
            return {"success": True}

        except yt_dlp.utils.DownloadError as e:
            # Unavailable videos get one retry
            if attempt == max_retries or (attempt >= 1 and _is_unavailable(e)):
                return {"success": False, "error": str(e)}


def _is_unavailable(error: yt_dlp.utils.DownloadError) -> bool:
    cause = error.exc_info[1] if error.exc_info else None
    return isinstance(cause, yt_dlp.utils.ExtractorError) and cause.expected
