import os
import yt_dlp

from .formats import AudioQuality, VideoQuality


# Public functions

def download_audio(url: str, quality: AudioQuality, output_dir: str = ".") -> dict:
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

    options = {
        "quiet": True,
        "no_warnings": True,
        "format": quality.format_id,
        "outtmpl": outtmpl,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(quality.bitrate),
            }
        ],
    }

    return _run_download(url, options, final_ext="mp3")


def download_video(url: str, quality: VideoQuality, output_dir: str = ".") -> dict:
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

    options = {
        "quiet": True,
        "no_warnings": True,
        "format": quality.download_format_id,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
    }

    return _run_download(url, options, final_ext="mp4")


# Internal helpers

def _run_download(url: str, options: dict, final_ext: str) -> dict:
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:
        return {
            "success": False,
            "error": str(e),
        }

    filepath = _resolve_output_path(ydl, info, final_ext)

    return {
        "success": True,
        "filepath": filepath,
        "title": info.get("title"),
    }


def _resolve_output_path(ydl: yt_dlp.YoutubeDL, info: dict, final_ext: str) -> str:
    raw_path = ydl.prepare_filename(info)
    base, _ = os.path.splitext(raw_path)
    return f"{base}.{final_ext}"
