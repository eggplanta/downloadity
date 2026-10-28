from dataclasses import dataclass, field
from typing import Optional

VIDEO_MARGIN = 1.05

# Data structures

@dataclass
class AudioQuality:
    format_id: str
    bitrate: int
    filesize: Optional[int]

    @property
    def value(self) -> int:
        return self.bitrate

    @property
    def label(self) -> str:
        return f"{self.bitrate} kbps"

    @property
    def filesize_label(self) -> Optional[str]:
        return _human_filesize(self.filesize)


@dataclass
class VideoQuality:
    format_id: str
    height: int
    filesize: Optional[int]
    has_audio: bool
    paired_audio: Optional[AudioQuality] = None

    @property
    def value(self) -> int:
        return self.height

    @property
    def label(self) -> str:
        return f"{self.height}p"

    @property
    def download_format_id(self) -> str:
        if self.has_audio or self.paired_audio is None:
            return self.format_id
        return f"{self.format_id}+{self.paired_audio.format_id}"

    @property
    def total_filesize(self) -> Optional[int]:
        total = self.filesize or 0
        if self.paired_audio and self.paired_audio.filesize:
            total += self.paired_audio.filesize

        return total or None

    @property
    def filesize_label(self) -> Optional[str]:
        if not self.total_filesize:
            return None
        return _human_filesize(int(self.total_filesize * VIDEO_MARGIN))


@dataclass
class QualityOptions:
    duration: Optional[int]

    audio: list[AudioQuality] = field(default_factory=list)
    video: list[VideoQuality] = field(default_factory=list)


@dataclass
class PlaylistQuality:
    kind: str
    value: int
    filesize: Optional[int]

    @property
    def label(self) -> str:
        return f"{self.value} kbps" if self.kind == "audio" else f"{self.value}p"

    @property
    def filesize_label(self) -> Optional[str]:
        return _human_filesize(self.filesize)


@dataclass
class PlaylistOptions:
    audio: list[PlaylistQuality] = field(default_factory=list)
    video: list[PlaylistQuality] = field(default_factory=list)


# Main functions

def build_quality_options(item: dict) -> QualityOptions:
    raw_audio = item.get("audio", [])
    raw_video = item.get("video", [])

    audio_qualities = _build_audio_qualities(raw_audio)
    best_audio = _pick_best_audio(audio_qualities)

    video_qualities = _build_video_qualities(raw_video, best_audio)

    return QualityOptions(
        duration=item.get("duration"),
        audio=audio_qualities,
        video=video_qualities,
    )


def build_playlist_options(
    samples: list[QualityOptions],
    total_duration: float,
) -> PlaylistOptions:
    """
    Sampled MB/second x total duration
    Video gets +5% safety margin
    """
    bitrates = sorted({q.value for s in samples for q in s.audio})
    heights = sorted({q.value for s in samples for q in s.video})

    audio = [
        PlaylistQuality(
            kind="audio",
            value=bitrate,
            filesize=_estimate_size(samples, "audio", bitrate, total_duration),
        )
        for bitrate in bitrates
    ]

    video = [
        PlaylistQuality(
            kind="video",
            value=height,
            filesize=_estimate_size(samples, "video", height, total_duration),
        )
        for height in heights
    ]

    return PlaylistOptions(audio=audio, video=video)


def pick_quality(qualities: list, target: int):
    """
    Same quality, else closest above, else best below
    """
    above = [q for q in qualities if q.value >= target]
    if above:
        return min(above, key=lambda q: q.value)

    below = [q for q in qualities if q.value < target]
    if below:
        return max(below, key=lambda q: q.value)

    return None


# Internal helpers

def _estimate_size(
    samples: list[QualityOptions],
    kind: str,
    value: int,
    total_duration: float,
) -> Optional[int]:
    size = 0
    duration = 0

    for sample in samples:
        quality = pick_quality(getattr(sample, kind), value)
        if quality is None or not sample.duration:
            continue

        # Final mp3 uses the picked bitrate
        if kind == "audio":
            item_size = quality.bitrate * 1000 / 8 * sample.duration
        else:
            item_size = quality.total_filesize

        if item_size:
            size += item_size
            duration += sample.duration

    if not duration:
        return None

    margin = VIDEO_MARGIN if kind == "video" else 1
    return int(size / duration * total_duration * margin)


def _build_audio_qualities(raw_audio: list) -> list[AudioQuality]:
    return [
        AudioQuality(
            format_id=item["format_id"],
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
