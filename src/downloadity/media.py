import dataclasses
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional, Union

import yt_dlp
from spotify_scraper.errors import NotFoundError

from . import extractor, spotify
from .throttle import CHECK_ATTEMPTS, MAX_ATTEMPTS
from .formats import (
    PlaylistOptions,
    QualityOptions,
    build_playlist_options,
    build_quality_options,
)

AUDIO_ONLY_HOSTS = ("spotify.com", "music.youtube.com")

SAMPLE_MIN = 4
SAMPLE_MAX = 8
SAMPLE_STEP = 10
WORKERS = 3

UNAVAILABLE_TITLES = ("[Deleted video]", "[Private video]")
DETAIL_CHARS = 90

# yt-dlp message -> short reason
REASONS = (
    ("is not a valid URL", "this is not a link"),
    ("Unsupported URL", "this site is not supported"),
    ("Private video", "this video is private"),
    ("playlist does not exist", "playlist is private or doesn't exist"),
    ("playlist is private", "playlist is private or doesn't exist"),
    ("confirm your age", "age-restricted, needs a login"),
    ("members-only", "members-only content"),
    ("Join this channel", "members-only content"),
    ("not available in your country", "not available in your country"),
    ("not made this video available", "not available in your country"),
    ("live event will begin", "this live hasn't started yet"),
    ("Premieres in", "this premiere hasn't started yet"),
    ("video is unavailable", "this video is unavailable"),
    ("Video unavailable", "this video is unavailable"),
    ("HTTP Error 404", "page not found"),
    ("Failed to resolve", "no internet connection"),
    ("getaddrinfo", "no internet connection"),
    ("timed out", "connection timed out"),
    ("no match found on YouTube", "no match found on YouTube"),
)
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
    item_id: Optional[str] = None
    cover: Optional[bytes] = None
    audio_only: bool = False
    error: Optional[str] = None


class CheckError(Exception):
    """
    Short reason shown to the user
    """


@dataclass
class Media:
    source_url: str
    title: Optional[str]
    is_playlist: bool
    options: Union[QualityOptions, PlaylistOptions]
    entries: list[MediaEntry] = field(default_factory=list)
    invalid: list[MediaEntry] = field(default_factory=list)
    playlist_id: Optional[str] = None
    samples: list[QualityOptions] = field(default_factory=list)


# Main function

def resolve_media(url: str) -> Media:
    """
    Validates the link and extracts it once
    Playlists only extract an evenly spaced sample
    Raises CheckError with a short reason
    """
    audio_only = any(host in url for host in AUDIO_ONLY_HOSTS)

    if "spotify.com" in url:
        title, tracks = _spotify_collection(url)
        entries = [
            MediaEntry(
                url=None,
                duration=track.duration_ms / 1000,
                spotify_track=track,
                title=f"{', '.join(track.artists)} - {track.title}",
                item_id=track.id and f"spotify:{track.id}",
            )
            for track in tracks
        ]
        is_playlist = "/track/" not in url
        match = re.search(r"/(playlist|album)/([A-Za-z0-9]+)", url)
        playlist_id = match and f"spotify:{match.group(1)}:{match.group(2)}"
    else:
        info = extractor.extract(url, flat="in_playlist", audio_only=audio_only, attempts=CHECK_ATTEMPTS)

        if info["type"] == "error":
            raise CheckError(describe_error(info["message"]))

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
                    item_id=_item_id(e),
                )
                for e in info["entries"]
                if e.get("url")
            ]
            is_playlist = True
            playlist_id = f"{(info.get('extractor_key') or 'site').lower()}:{info.get('id')}"
        else:
            title = None
            entries = [MediaEntry(url=url, duration=info.get("duration"), info=info)]
            is_playlist = False
            playlist_id = None

    if not entries:
        raise CheckError("this playlist is empty")
    for entry in entries:
        entry.audio_only = audio_only

    samples = _extract_samples(entries)

    sampled = [build_quality_options(e.info) for e in samples if e.info]
    if not sampled:
        errors = [e.error for e in entries if e.error]
        raise CheckError(describe_error(errors[0]) if errors else "no playable items found")

    if audio_only:
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
        playlist_id=playlist_id if is_playlist else None,
        samples=sampled,
    )


def subset(media: Media, entries: list[MediaEntry]) -> Media:
    """
    Same playlist, fewer items, sizes re-estimated
    """
    options = build_playlist_options(media.samples, _total_duration(entries, media.samples))
    return dataclasses.replace(media, options=options, entries=entries)


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
    One more per 10 items (4 to 8), evenly spaced
    """
    extra = max(0, count - 1) // SAMPLE_STEP
    size = min(count, SAMPLE_MAX, SAMPLE_MIN + extra)
    return [int(i * count / size) for i in range(size)]


def describe_error(message: str) -> str:
    """
    Short reason plus the raw detail
    """
    for marker, reason in REASONS:
        if marker in message:
            return reason
    # "ERROR: [site] id: text" -> "text"
    detail = re.sub(r"ERROR: (\[[^\]]+\] )?([^:\s]+: )?", "", message.strip())
    return "couldn't read this link\n" + _shorten(detail)


# Internal helpers

def _spotify_collection(url: str):
    try:
        return spotify.get_collection(url)
    except NotFoundError:
        raise CheckError("spotify: private or unavailable")
    except ValueError:
        raise CheckError("spotify: only tracks, albums\nand playlists")
    except Exception as e:
        raise CheckError("spotify: couldn't read this link\n" + _shorten(str(e) or type(e).__name__))


def _shorten(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= DETAIL_CHARS else text[:DETAIL_CHARS - 1] + "…"


def _extract_samples(entries: list[MediaEntry]) -> list[MediaEntry]:
    """
    Invalid samples are replaced by the next item
    """
    valid = [i for i, e in enumerate(entries) if not e.invalid]
    picks = [valid[i] for i in sample_indices(len(valid))] if valid else []
    used = set(picks)
    samples = []

    executor = ThreadPoolExecutor(max_workers=WORKERS)
    try:
        while picks:
            pending = [entries[i] for i in picks if entries[i].info is None]
            futures = [executor.submit(extract_entry, e, CHECK_ATTEMPTS) for e in pending]
            for future in as_completed(futures):
                future.result()

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
    finally:
        # First block skips the other samples
        executor.shutdown(wait=False, cancel_futures=True)

    return samples


def _next_unused(entries: list[MediaEntry], index: int, used: set) -> Optional[int]:
    for i in range(index + 1, len(entries)):
        if i not in used and not entries[i].invalid:
            return i
    return None


def _item_id(entry: dict) -> Optional[str]:
    if not entry.get("id"):
        return None
    return f"{(entry.get('site') or 'site').lower()}:{entry['id']}"


def _is_unavailable(entry: dict) -> bool:
    return entry.get("title") in UNAVAILABLE_TITLES or entry.get("availability") == "private"


def extract_entry(entry: MediaEntry, attempts: int = MAX_ATTEMPTS) -> None:
    """
    Spotify falls back to the next match
    """
    urls = [entry.url] if entry.url else []
    if not urls and entry.spotify_track:
        try:
            urls = spotify.best_match_urls(entry.spotify_track, attempts)
        except yt_dlp.utils.DownloadError as e:
            entry.error = "youtube search: " + str(e)
            return
        if not urls:
            entry.error = "no match found on YouTube"

    for url in urls:
        info = extractor.extract(url, audio_only=entry.audio_only, attempts=attempts)
        if info["type"] == "video":
            entry.url, entry.info, entry.error = url, info, None
            return
        entry.error = info.get("message")


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
