import os
import yt_dlp

from .formats import AudioQuality, VideoQuality


def download_audio(
    url: str,
    quality: AudioQuality,
    output_dir: str = ".",
) -> dict:
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

    options = {
        "quiet": True,
        "no_warnings": True,
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
        final_ext="mp3",
    )


def download_video(
    url: str,
    quality: VideoQuality,
    output_dir: str = ".",
) -> dict:
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

    options = {
        "quiet": True,
        "no_warnings": True,
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
        final_ext="mp4",
    )


def _run_download(
    url: str,
    options: dict,
    final_ext: str,
    max_retries: int = 2,
) -> dict:
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                current_info = ydl.extract_info(url, download=True)

        except yt_dlp.utils.DownloadError as e:
            last_error = str(e)
            print(f"Download attempt {attempt + 1}/{max_retries + 1} failed: {last_error}")

            if attempt < max_retries:
                continue

            return {
                "success": False,
                "error": last_error,
            }

        filepath = _resolve_output_path(ydl, current_info, final_ext)

        return {
            "success": True,
            "filepath": filepath,
            "title": current_info.get("title"),
        }

    return {
        "success": False,
        "error": last_error,
    }


def _resolve_output_path(
    ydl: yt_dlp.YoutubeDL,
    info: dict,
    final_ext: str,
) -> str:
    raw_path = ydl.prepare_filename(info)
    base, _ = os.path.splitext(raw_path)

    return f"{base}.{final_ext}"