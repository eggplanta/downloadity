"""
Spotify to YouTube URL

"""

from dataclasses import dataclass
from typing import Optional

import yt_dlp
from spotify_scraper import SpotifyClient
from spotify_scraper.http.retry import RetryPolicy
from spotify_scraper.models import Track as SpotifyTrackData

NO_TRACK_LIMIT = None

_RETRY = RetryPolicy(max_attempts=5, backoff_base=1.0, backoff_max=20.0)

_CANDIDATES_PER_TRACK = 5

_YDL_SEARCH_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": "in_playlist",
    "skip_download": True,
}


@dataclass
class _SpotifyTrack:
    title: str
    artists: list[str]
    duration_ms: int

    @property
    def search_query(self) -> str:
        artists = ", ".join(self.artists)
        return f"{artists} - {self.title} audio"


def _spotify_client() -> SpotifyClient:
    return SpotifyClient(retry=_RETRY)


def _track_from_data(data: SpotifyTrackData) -> _SpotifyTrack:
    return _SpotifyTrack(
        title=data.name,
        artists=[a.name for a in data.artists],
        duration_ms=data.duration_ms,
    )


def _safe_convert(raw_tracks) -> list[_SpotifyTrack]:
    """Skip individual tracks that fail to parse instead of losing the whole batch."""
    tracks = []
    for raw in raw_tracks:
        try:
            tracks.append(_track_from_data(raw))
        except (AttributeError, KeyError, TypeError):
            continue
    return tracks


def _search_candidates(query: str) -> list[dict]:
    search = f"ytsearch{_CANDIDATES_PER_TRACK}:{query}"
    with yt_dlp.YoutubeDL(_YDL_SEARCH_OPTS) as ydl:
        result = ydl.extract_info(search, download=False)
    return result.get("entries") or []


def _is_topic_channel(entry: dict) -> bool:
    """"Artist - Topic" channels host the plain studio audio uploaded by the
    distributor, which is usually the best match for an audio download."""
    channel = (entry.get("channel") or entry.get("uploader") or "").lower()
    return channel.endswith("- topic") or channel.endswith("-topic")


def _best_match_url(track: _SpotifyTrack) -> Optional[str]:
    """Search YouTube and return the URL whose duration is closest to the Spotify
    track, preferring "- Topic" (official audio) channels on close calls."""
    try:
        candidates = _search_candidates(track.search_query)
    except yt_dlp.utils.DownloadError:
        return None

    target_seconds = track.duration_ms / 1000
    scored = []
    fallback_url = None
    for entry in candidates:
        video_id = entry.get("id")
        if not video_id:
            continue
        url = f"https://www.youtube.com/watch?v={video_id}"
        fallback_url = fallback_url or url
        duration = entry.get("duration")
        if duration is not None:
            score = abs(duration - target_seconds)
            if _is_topic_channel(entry):
                score -= 2  # tiebreak bonus
            scored.append((score, url))

    if scored:
        scored.sort(key=lambda pair: pair[0])
        return scored[0][1]
    return fallback_url


def _resolve_all(tracks: list[_SpotifyTrack]) -> list[str]:
    urls = []
    for track in tracks:
        url = _best_match_url(track)
        if url:
            urls.append(url)
    return urls


def extract_track(url: str) -> Optional[str]:
    """Returns the matching YouTube URL for a single Spotify track, or None if not found."""
    data = _spotify_client().get_track(url)
    return _best_match_url(_track_from_data(data))


def extract_album(url: str) -> list[str]:
    """Returns the matching YouTube URLs for every track in a Spotify album."""
    album = _spotify_client().get_album(url)
    return _resolve_all(_safe_convert(album.tracks))


def extract_playlist(url: str, max_tracks: Optional[int] = NO_TRACK_LIMIT) -> list[str]:
    """Returns the matching YouTube URLs for every track in a Spotify playlist."""
    playlist = _spotify_client().get_playlist(url, max_tracks=max_tracks)
    return _resolve_all(_safe_convert(pt.track for pt in playlist.tracks))


def extract(url: str, max_tracks: Optional[int] = NO_TRACK_LIMIT) -> list[str]:
    """Entry point: dispatches based on URL type (track / album / playlist)."""
    if "/track/" in url:
        match = extract_track(url)
        return [match] if match else []
    if "/album/" in url:
        return extract_album(url)
    if "/playlist/" in url:
        return extract_playlist(url, max_tracks=max_tracks)
    raise ValueError(f"Unsupported Spotify URL: {url}")