from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional, Union

from . import extractor, spotify
from .formats import (
    PlaylistOptions,
    QualityOptions,
    build_playlist_options,
    build_quality_options,
)

AUDIO_ONLY_HOSTS = ("spotify.com", "music.youtube.com")

SAMPLE_RATIO = 0.2
SAMPLE_MIN = 6
SAMPLE_MAX = 12
WORKERS = 3

UNAVAILABLE_TITLES = ("[Deleted video]", "[Private video]")
CAPTION_CHARS = 40


@dataclass
class MediaEntry:
    url: Optional[str]
    duration: Optional[float]
    info: Optional[dict] = None
    spotify_track: Optional[spotify._SpotifyTrack] = None
    title: Optional[str] = None
    invalid: bool = False
    embedded: bool = False


@dataclass
class Media:
    source_url: str
    title: Optional[str]
    is_playlist: bool
    options: Union[QualityOptions, PlaylistOptions]
    entries: list[MediaEntry] = field(default_factory=list)
    invalid: list[MediaEntry] = field(default_factory=list)


# Main function

def resolve_media(url: str) -> Optional[Media]:
    """
    Validates the link and extracts it once
    Playlists only extract an evenly spaced sample
    """
    if "spotify.com" in url:
        title, tracks = spotify.get_collection(url)
        entries = [
            MediaEntry(
                url=None,
                duration=track.duration_ms / 1000,
                spotify_track=track,
                title=f"{', '.join(track.artists)} - {track.title}",
            )
            for track in tracks
        ]
        is_playlist = "/track/" not in url
    else:
        info = extractor.extract(url, flat="in_playlist")

        if info["type"] == "error":
            return None

        if info["type"] == "playlist":
            caption = caption_title(info)
            title = f"{caption} [{info.get('id')}]" if caption else info.get("title")
            entries = [
                MediaEntry(
                    url=e["url"],
                    duration=e.get("duration"),
                    title=e.get("title"),
                    invalid=_is_unavailable(e),
                    info=e["item"] and {"type": "video", **e["item"]},
                    embedded=bool(e["item"]),
                )
                for e in info["entries"]
                if e.get("url")
            ]
            is_playlist = True
        else:
            title = None
            entries = [MediaEntry(url=url, duration=info.get("duration"), info=info)]
            is_playlist = False

    if not entries:
        return None

    samples = _extract_samples(entries)

    sampled = [build_quality_options(e.info) for e in samples if e.info]
    if not sampled:
        return None

    if any(host in url for host in AUDIO_ONLY_HOSTS):
        for options in sampled:
            options.video = []

    if is_playlist:
        options = build_playlist_options(sampled, _total_duration(entries, sampled))
    else:
        options = sampled[0]

    return Media(
        source_url=url,
        title=title,
        is_playlist=is_playlist,
        options=options,
        entries=[e for e in entries if not e.invalid],
        invalid=[e for e in entries if e.invalid],
    )


def caption_title(info: dict) -> Optional[str]:
    """
    Instagram titles are generic, use the caption
    """
    if info.get("extractor_key") != "Instagram":
        return None

    caption = " ".join((info.get("description") or "").split())
    if len(caption) > CAPTION_CHARS:
        caption = caption[:CAPTION_CHARS].rstrip() + "..."
    return caption or info.get("title")


def sample_indices(count: int) -> list[int]:
    """
    20% of the items (6 to 12), evenly spaced
    """
    size = min(count, max(SAMPLE_MIN, min(SAMPLE_MAX, round(count * SAMPLE_RATIO))))
    return [int(i * count / size) for i in range(size)]


# Internal helpers

def _extract_samples(entries: list[MediaEntry]) -> list[MediaEntry]:
    """
    Invalid samples are replaced by the next item
    """
    valid = [i for i, e in enumerate(entries) if not e.invalid]
    picks = [valid[i] for i in sample_indices(len(valid))] if valid else []
    used = set(picks)
    samples = []

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        while picks:
            pending = [entries[i] for i in picks if entries[i].info is None]
            list(executor.map(extract_entry, pending))

            retry = []
            for index in picks:
                entry = entries[index]
                if entry.info:
                    samples.append(entry)
                    continue

                entry.invalid = True
                replacement = _next_unused(entries, index, used)
                if replacement is not None:
                    used.add(replacement)
                    retry.append(replacement)
            picks = retry

    return samples


def _next_unused(entries: list[MediaEntry], index: int, used: set) -> Optional[int]:
    for i in range(index + 1, len(entries)):
        if i not in used and not entries[i].invalid:
            return i
    return None


def _is_unavailable(entry: dict) -> bool:
    return entry.get("title") in UNAVAILABLE_TITLES or entry.get("availability") == "private"


def extract_entry(entry: MediaEntry) -> None:
    """
    Spotify falls back to the next match
    """
    urls = [entry.url] if entry.url else []
    if not urls and entry.spotify_track:
        urls = spotify.best_match_urls(entry.spotify_track)

    for url in urls:
        info = extractor.extract(url)
        if info["type"] == "video":
            entry.url, entry.info = url, info
            return


def _total_duration(entries: list[MediaEntry], sampled: list[QualityOptions]) -> float:
    entries = [e for e in entries if not e.invalid]
    known = [e.duration for e in entries if e.duration]

    if known:
        average = sum(known) / len(known)
    else:
        durations = [s.duration for s in sampled if s.duration]
        average = sum(durations) / len(durations) if durations else 0

    missing = len(entries) - len(known)
    return sum(known) + average * missing
