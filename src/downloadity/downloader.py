import copy
import os
import subprocess
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
    on_postprocess=None,
    overwrite: bool = False,
) -> dict:
    outtmpl = _outtmpl(output_dir, filename)

    options = {
        "quiet": True,
        "no_warnings": True,
        "logger": SilentLogger(),
        "format": quality.format_id,
        "outtmpl": outtmpl,
        "overwrites": overwrite,

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
    if on_postprocess:
        options["postprocessor_hooks"] = [on_postprocess]

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
    overwrite: bool = False,
) -> dict:
    outtmpl = _outtmpl(output_dir, filename)

    options = {
        "quiet": True,
        "no_warnings": True,
        "logger": SilentLogger(),
        "format": quality.download_format_id,
        "outtmpl": outtmpl,
        "overwrites": overwrite,
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


def cut_video(source: str, start: float, end: float, output: str, on_progress=None) -> bool:
    """
    Re-encodes the range for an exact cut
    Both streams re-encoded keep A/V sync
    """
    length = end - start
    command = [
        "ffmpeg", "-y", "-v", "error", "-nostats",
        "-ss", str(start), "-t", str(length), "-i", source,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        output,
    ]

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    for line in process.stdout:
        key, _, value = line.strip().partition("=")
        if key == "out_time_us" and value.isdigit() and on_progress:
            on_progress(min(1.0, int(value) / 1e6 / length))
    process.wait()

    if process.returncode != 0 and os.path.exists(output):
        os.remove(output)
    return process.returncode == 0


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

    # Last postprocessor holds the final path
    final = {}

    def capture(d):
        if d["status"] == "finished" and d.get("info_dict", {}).get("filepath"):
            final["path"] = d["info_dict"]["filepath"]

    options["postprocessor_hooks"] = list(options.get("postprocessor_hooks") or []) + [capture]

    for attempt in range(max_retries + 1):
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                # Reuse the extraction when given
                if info:
                    # Drop the extraction's format choice
                    fresh = copy.deepcopy(info)
                    fresh.pop("requested_formats", None)
                    ydl.process_ie_result(fresh, download=True)
                else:
                    ydl.extract_info(url, download=True)
            return {"success": True, "path": final.get("path")}

        except yt_dlp.utils.DownloadError as e:
            # Unavailable videos get one retry
            if attempt == max_retries or (attempt >= 1 and _is_unavailable(e)):
                return {"success": False, "error": str(e)}


def _is_unavailable(error: yt_dlp.utils.DownloadError) -> bool:
    cause = error.exc_info[1] if error.exc_info else None
    return isinstance(cause, yt_dlp.utils.ExtractorError) and cause.expected
