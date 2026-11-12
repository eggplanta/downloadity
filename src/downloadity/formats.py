from dataclasses import dataclass, field
from typing import Optional, Union

VIDEO_MARGIN = 1.05
AUDIO_FORMATS = ("m4a", "opus", "mp3", "flac")
VIDEO_FORMATS = ("mp4", "mkv")
# Converted, so any bitrate works
MP3_BITRATES = (320, 192, 128)
# Typical lossless music bitrate
FLAC_KBPS = 900
# Higher ranks win, then bitrate
VIDEO_CODEC_RANKS = {
    # H.264 first, it plays everywhere
    "mp4": {"avc": 2, "vp9": 1},
    # Any codec, most data wins
    "mkv": {},
}
# Audio merged into each container
PAIRED_CODECS = {"mp4": "m4a", "mkv": "opus"}

# Data structures

@dataclass(frozen=True)
class Formats:
    audio: str = "m4a"
    video: str = "mp4"


@dataclass
class AudioQuality:
    format_id: str
    # None for lossless
    bitrate: Optional[int]
    filesize: Optional[int]
    codec: str = "m4a"
    native: bool = True

    @property
    def value(self) -> int:
        return self.bitrate or 0

    @property
    def label(self) -> str:
        return audio_label(self.codec, self.bitrate)

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
    container: str = "mp4"

    @property
    def value(self) -> int:
        return self.height

    @property
    def label(self) -> str:
        return f"{self.container.upper()} {self.height}p"

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
    # Audio codec or video container
    codec: str = ""

    @property
    def label(self) -> str:
        if self.kind == "audio":
            return audio_label(self.codec, self.value)
        return f"{self.codec.upper()} {self.value}p"

    @property
    def filesize_label(self) -> Optional[str]:
        return _human_filesize(self.filesize)


@dataclass
class PlaylistOptions:
    audio: list[PlaylistQuality] = field(default_factory=list)
    video: list[PlaylistQuality] = field(default_factory=list)


# Main functions

def build_quality_options(item: dict, formats: Formats = Formats()) -> QualityOptions:
    raw_audio = [a for a in item.get("audio", []) if a.get("format_id") is not None]
    raw_video = [v for v in item.get("video", []) if v.get("format_id") is not None]
    duration = item.get("duration")

    paired = _paired_audio(raw_audio, formats.video)

    return QualityOptions(
        duration=duration,
        audio=_build_audio_qualities(raw_audio, formats.audio, duration),
        video=_build_video_qualities(raw_video, paired, formats.video),
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
            codec=next(q.codec for s in samples for q in s.audio if q.value == bitrate),
        )
        for bitrate in bitrates
    ]

    video = [
        PlaylistQuality(
            kind="video",
            value=height,
            filesize=_estimate_size(samples, "video", height, total_duration),
            codec=next(q.container for s in samples for q in s.video if q.value == height),
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


def audio_label(codec: str, bitrate: Optional[int]) -> str:
    if not bitrate:
        return codec.upper()
    return f"{codec.upper()} {bitrate} kbps"


# Internal helpers

def _estimate_size(
    samples: list[QualityOptions],
    kind: str,
    value: Union[int, str],
    total_duration: float,
) -> Optional[int]:
    size = 0
    duration = 0

    for sample in samples:
        quality = pick_quality(getattr(sample, kind), value)
        if quality is None or not sample.duration:
            continue

        if kind == "audio":
            item_size = quality.filesize or _audio_size(quality.bitrate, sample.duration)
        else:
            item_size = quality.total_filesize

        if item_size:
            size += item_size
            duration += sample.duration

    if not duration:
        return None

    margin = VIDEO_MARGIN if kind == "video" else 1
    return int(size / duration * total_duration * margin)


def _build_audio_qualities(raw_audio: list, target: str, duration) -> list[AudioQuality]:
    """
    Native copies of the chosen codec
    Else conversions from the best source
    """
    sources = _without_drc(raw_audio)
    if not sources:
        return []

    # No Opus encoder, M4A instead
    if target == "opus" and not any(a["codec"] == "opus" for a in sources):
        target = "m4a"

    native = [a for a in sources if a["codec"] == target]
    if native and target == "flac":
        native = [max(native, key=lambda a: a["abr"])]
    if native:
        by_bitrate = {}
        for a in native:
            if a["bitrate"] not in by_bitrate or a["abr"] > by_bitrate[a["bitrate"]]["abr"]:
                by_bitrate[a["bitrate"]] = a
        return [
            AudioQuality(
                format_id=a["format_id"],
                bitrate=None if target == "flac" else a["bitrate"],
                filesize=a.get("filesize"),
                codec=target,
            )
            for a in by_bitrate.values()
        ]

    source = _best_source(sources)
    if target == "flac":
        bitrates = (None,)
    elif target == "mp3":
        bitrates = MP3_BITRATES
    else:
        bitrates = (source["bitrate"],)

    return [
        AudioQuality(
            format_id=source["format_id"],
            bitrate=bitrate,
            filesize=_audio_size(bitrate, duration),
            codec=target,
            native=False,
        )
        for bitrate in bitrates
    ]


def _build_video_qualities(
    raw_video: list,
    paired: Optional[AudioQuality],
    container: str,
) -> list[VideoQuality]:
    """
    Best format per height
    Codec rank, direct files, then bitrate
    HLS copies declare peak bitrates
    """
    ranks = VIDEO_CODEC_RANKS[container]
    best = {}
    for v in raw_video:
        rank = (ranks.get(v["codec"], 0), not v.get("hls"), v["tbr"])
        if v["height"] not in best or rank > best[v["height"]][0]:
            best[v["height"]] = (rank, v)

    return [
        VideoQuality(
            format_id=v["format_id"],
            height=height,
            filesize=v.get("filesize"),
            has_audio=v["has_audio"],
            paired_audio=None if v["has_audio"] else paired,
            container=container,
        )
        for height, (_, v) in sorted(best.items())
    ]


def _paired_audio(raw_audio: list, container: str) -> Optional[AudioQuality]:
    """
    Best audio for the container
    """
    sources = _without_drc(raw_audio)
    if not sources:
        return None

    codec = PAIRED_CODECS[container]
    matching = [a for a in sources if a["codec"] == codec]
    best = _best_source(matching or sources)
    return AudioQuality(
        format_id=best["format_id"],
        bitrate=best["bitrate"],
        filesize=best.get("filesize"),
        codec=best["codec"],
    )


def _best_source(sources: list) -> dict:
    # Opus wins ties, better per bit
    return max(sources, key=lambda a: (a["codec"] != "other", a["bitrate"], a["codec"] == "opus", a["abr"]))


def _without_drc(raw_audio: list) -> list:
    # Compressed loudness sounds worse
    clean = [a for a in raw_audio if not a.get("drc")]
    return clean or raw_audio


def _audio_size(bitrate: Optional[int], duration) -> Optional[int]:
    if not duration:
        return None
    return int((bitrate or FLAC_KBPS) * 1000 / 8 * duration)


def _human_filesize(num_bytes: Optional[int]) -> Optional[str]:
    if not num_bytes:
        return None

    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        # Avoids labels like 1001.4 MB
        if size < 1000:
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"
