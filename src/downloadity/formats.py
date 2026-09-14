from dataclasses import dataclass, field
from typing import Optional


# Data structures

@dataclass
class AudioQuality:
    format_id: str
    ext: str
    bitrate: int
    filesize: Optional[int]

    @property
    def label(self) -> str:
        return f"{self.bitrate} kbps"

    @property
    def filesize_label(self) -> Optional[str]:
        return _human_filesize(self.filesize)


@dataclass
class VideoQuality:
    format_id: str
    ext: str
    height: int
    filesize: Optional[int]
    has_audio: bool
    paired_audio: Optional[AudioQuality] = None

    @property
    def resolution(self) -> str:
        return f"{self.height}p"

    @property
    def label(self) -> str:
        return self.resolution

    @property
    def download_format_id(self) -> str:
        if self.has_audio or self.paired_audio is None:
            return self.format_id
        return f"{self.format_id}+{self.paired_audio.format_id}"

    @property
    def filesize_label(self) -> Optional[str]:
        total = self.filesize or 0
        if self.paired_audio and self.paired_audio.filesize:
            total += self.paired_audio.filesize

        return _human_filesize(total) if total else None


@dataclass
class QualityOptions:
    title: Optional[str]
    duration: Optional[int]
    thumbnail: Optional[str]
    uploader: Optional[str]
    webpage_url: Optional[str]

    audio: list[AudioQuality] = field(default_factory=list)
    video: list[VideoQuality] = field(default_factory=list)


# Main function

def build_quality_options(item: dict) -> QualityOptions:
    raw_audio = item.get("audio", [])
    raw_video = item.get("video", [])

    audio_qualities = _build_audio_qualities(raw_audio)
    best_audio = _pick_best_audio(audio_qualities)

    video_qualities = _build_video_qualities(raw_video, best_audio)

    return QualityOptions(
        title=item.get("title"),
        duration=item.get("duration"),
        thumbnail=item.get("thumbnail"),
        uploader=item.get("uploader"),
        webpage_url=item.get("webpage_url"),
        audio=audio_qualities,
        video=video_qualities,
    )


# Internal helpers

def _build_audio_qualities(raw_audio: list) -> list[AudioQuality]:
    return [
        AudioQuality(
            format_id=item["format_id"],
            ext=item["ext"],
            bitrate=item["bitrate"],
            filesize=item.get("filesize"),
        )
        for item in raw_audio
        if item.get("format_id") is not None
    ]


def _build_video_qualities(
    raw_video: list,
    best_audio: Optional[AudioQuality],
) -> list[VideoQuality]:

    result = []

    for item in raw_video:
        if item.get("format_id") is None:
            continue

        has_audio = item.get("has_audio", False)

        result.append(
            VideoQuality(
                format_id=item["format_id"],
                ext=item["ext"],
                height=item["height"],
                filesize=item.get("filesize"),
                has_audio=has_audio,
                paired_audio=None if has_audio else best_audio,
            )
        )

    return result


def _pick_best_audio(audio_qualities: list[AudioQuality]) -> Optional[AudioQuality]:
    if not audio_qualities:
        return None

    return max(audio_qualities, key=lambda a: a.bitrate)


def _human_filesize(num_bytes: Optional[int]) -> Optional[str]:
    if not num_bytes:
        return None

    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"
