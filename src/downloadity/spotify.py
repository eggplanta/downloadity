"""
Spotify URL -> YouTube URL

"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional
import re
import unicodedata

import yt_dlp
from spotify_scraper import SpotifyClient
from spotify_scraper.http.retry import RetryPolicy
from spotify_scraper.models import Track as SpotifyTrackData


NO_TRACK_LIMIT = None

_RETRY = RetryPolicy(
    max_attempts=5,
    backoff_base=1.0,
    backoff_max=20.0,
)

_CANDIDATES_PER_QUERY = 5

_YDL_SEARCH_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": "in_playlist",
    "skip_download": True,
}

# Score weights: higher score = better candidate
_POSITION_POINTS = (5.0, 4.0, 3.0, 2.0, 1.0)
_TOPIC_BONUS = 4.0
_OFFICIAL_AUDIO_BONUS = 4.0
_REPEATED_QUERY_BONUS = 2.0
_ALTERNATE_VERSION_PENALTY = 5.0

@dataclass
class _SpotifyTrack:
    title: str
    artists: list[str]
    duration_ms: int

    @property
    def search_queries(self) -> list[tuple[str, str]]:
        title = _clean_search_text(self.title)
        artist = _clean_search_text(self.artists[0])

        base = f"{artist} - {title}"

        return [
        ("topic", f"{base} Topic"),
        ("official_audio", f"{base} Official Audio"),
        ]


@dataclass
class _Candidate:
    video_id: str
    url: str
    title: str
    channel: str = ""
    duration: Optional[float] = None

    # Evidence collected from the different searches.
    positions: list[int] = field(default_factory=list)
    query_types: set[str] = field(default_factory=set)


def _spotify_client() -> SpotifyClient:
    return SpotifyClient(retry=_RETRY)


def _track_from_data(data: SpotifyTrackData) -> _SpotifyTrack:
    return _SpotifyTrack(
        title=data.name,
        artists=[artist.name for artist in data.artists],
        duration_ms=data.duration_ms,
    )


def _safe_convert(raw_tracks) -> list[_SpotifyTrack]:
    """Skip individual tracks that fail to parse."""
    tracks = []

    for raw in raw_tracks:
        try:
            tracks.append(_track_from_data(raw))
        except (AttributeError, KeyError, TypeError):
            continue

    return tracks


def _search_candidates(query: str) -> list[dict]:
    search = f"ytsearch{_CANDIDATES_PER_QUERY}:{query}"

    with yt_dlp.YoutubeDL(_YDL_SEARCH_OPTS) as ydl:
        result = ydl.extract_info(search, download=False)

    return result.get("entries") or []


def _normalize_text(text: str) -> str:
    """
    Normalize text for comparisons
    This removes accents, punctuation and common YouTube metadata words
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()

    text = re.sub(
        r"\b("
        r"official\s+audio|"
        r"official\s+video|"
        r"official|"
        r"audio|"
        r"video|"
        r"lyrics?|"
        r"lyric\s+video|"
        r"hd|"
        r"4k|"
        r"topic"
        r")\b",
        " ",
        text,
    )

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def _clean_search_text(text: str) -> str:
    text = re.sub(r"[-–—]+", " ", text)
    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _tokens(text: str) -> set[str]:
    return set(_normalize_text(text).split())


def _token_similarity(a: str, b: str) -> float:
    """
    Token overlap using Jaccard similarity
    Word order does not matter
    """
    a_tokens = _tokens(a)
    b_tokens = _tokens(b)

    if not a_tokens or not b_tokens:
        return 0.0

    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def _sequence_similarity(a: str, b: str) -> float:
    """
    Character similarity as a secondary signal
    """
    from difflib import SequenceMatcher

    a = _normalize_text(a)
    b = _normalize_text(b)

    if not a or not b:
        return 0.0

    return SequenceMatcher(None, a, b).ratio()


def _title_similarity(track: _SpotifyTrack, candidate_title: str) -> float:
    """
    Compare the Spotify title with the YouTube title
    """
    token_score = _token_similarity(track.title, candidate_title)
    sequence_score = _sequence_similarity(track.title, candidate_title)

    return 0.7 * token_score + 0.3 * sequence_score


def _artist_similarity(track: _SpotifyTrack, candidate_title: str, channel: str) -> float:
    """
    Check whether Spotify artists appear in the YouTube title/channel
    """
    candidate_text = _normalize_text(f"{candidate_title} {channel}")

    if not candidate_text:
        return 0.0

    scores = []

    for artist in track.artists:
        artist_normalized = _normalize_text(artist)

        if not artist_normalized:
            continue

        if artist_normalized in candidate_text:
            scores.append(1.0)
            continue

        artist_tokens = set(artist_normalized.split())
        candidate_tokens = set(candidate_text.split())

        if artist_tokens:
            scores.append(
                len(artist_tokens & candidate_tokens)
                / len(artist_tokens | candidate_tokens)
            )

    if not scores:
        return 0.0

    return max(scores)


def _has_official_audio(title: str) -> bool:
    return "official audio" in title.lower()


def _has_alternate_version_marker(title: str) -> bool:
    lowered = _normalize_text(title)

    return bool(
        re.search(
            r"\b("
            r"live|"
            r"cover|"
            r"remix|"
            r"karaoke|"
            r"instrumental|"
            r"nightcore|"
            r"sped\s+up|"
            r"slowed|"
            r"8d|"
            r"reaction|"
            r"mashup"
            r"sub(?:title)?s?"
            r"acoustic|"
            r")\b",
            lowered,
        )
    )


def _duration_score(candidate: float, target: float) -> float:
    """
    Convert duration difference into points
    """
    difference = abs(candidate - target)

    if difference <= 1:
        return 12.0
    if difference <= 2:
        return 11.0
    if difference <= 3:
        return 10.0
    if difference <= 5:
        return 8.0
    if difference <= 10:
        return 5.0
    if difference <= 20:
        return 2.0

    return 0.0


def _position_score(candidate: _Candidate) -> float:
    if not candidate.positions:
        return 0.0

    # Best position is the strongest positional evidence.
    best_position = min(candidate.positions)

    if best_position < len(_POSITION_POINTS):
        return _POSITION_POINTS[best_position]

    return 0.0


def _score_candidate(
    candidate: _Candidate,
    track: _SpotifyTrack,
) -> float:
    score = 0.0

    target_seconds = track.duration_ms / 1000

    # Duration: strongest individual signal.
    if candidate.duration is not None:
        score += _duration_score(candidate.duration, target_seconds)

    # Title and artist similarity.
    title_similarity = _title_similarity(track, candidate.title)
    artist_similarity = _artist_similarity(
        track,
        candidate.title,
        candidate.channel,
    )

    score += title_similarity * 10.0
    score += artist_similarity * 10.0

    # Search ranking.
    score += _position_score(candidate)

    # Query-specific evidence.
    if "topic" in candidate.query_types:
        score += _TOPIC_BONUS

    if (
        "official_audio" in candidate.query_types
        or _has_official_audio(candidate.title)
    ):
        score += _OFFICIAL_AUDIO_BONUS

    repeated_queries = len(candidate.query_types)

    if repeated_queries == 2:
        score += _REPEATED_QUERY_BONUS

    if (
        _has_alternate_version_marker(candidate.title)
        and not _has_alternate_version_marker(track.title)
    ):
        score -= _ALTERNATE_VERSION_PENALTY

    return score


def _search_query(item: tuple[str, str]) -> tuple[str, list[dict]]:
    """
    Run one YouTube search and return its type together with the entries
    """
    query_type, query = item

    try:
        return query_type, _search_candidates(query)
    except yt_dlp.utils.DownloadError:
        # One failed query should not discard the other searches for this track.
        return query_type, []


def _collect_candidates(track: _SpotifyTrack) -> list[_Candidate]:
    """
    Run the n searches in parallel and merge duplicate YouTube videos
    """
    candidates: dict[str, _Candidate] = {}

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = executor.map(
            _search_query,
            track.search_queries,
        )

        for query_type, entries in results:
            for position, entry in enumerate(entries):
                video_id = entry.get("id")

                if not video_id:
                    continue

                title = entry.get("title") or ""
                channel = (
                    entry.get("channel")
                    or entry.get("uploader")
                    or ""
                )
                duration = entry.get("duration")

                existing = candidates.get(video_id)

                if existing is None:
                    existing = _Candidate(
                        video_id=video_id,
                        url=f"https://www.youtube.com/watch?v={video_id}",
                        title=title,
                        channel=channel,
                        duration=duration,
                    )
                    candidates[video_id] = existing

                existing.positions.append(position)
                existing.query_types.add(query_type)

                # Prefer non-empty metadata if the first occurrence lacked it.
                if not existing.title and title:
                    existing.title = title

                if not existing.channel and channel:
                    existing.channel = channel

                if existing.duration is None and duration is not None:
                    existing.duration = duration

    return list(candidates.values())


def _rank_candidates(
    track: _SpotifyTrack,
) -> list[tuple[float, _Candidate]]:
    """
    Return all candidates sorted from highest to lowest score
    """
    candidates = _collect_candidates(track)

    scored = [
        (
            _score_candidate(candidate, track),
            candidate,
        )
        for candidate in candidates
    ]

    scored.sort(
        key=lambda pair: pair[0],
        reverse=True,
    )

    return scored


def _best_match_url(track: _SpotifyTrack) -> Optional[str]:
    """
    Return the URL of the best candidate
    """
    ranked = _rank_candidates(track)

    if not ranked:
        return None

    return ranked[0][1].url


def debug_match(track: _SpotifyTrack, limit: int = 10) -> None:
    """
    Print the top matching candidates for manual testing/debugging
    """
    ranked = _rank_candidates(track)

    print()
    print(f"Spotify: {', '.join(track.artists)} - {track.title}")
    print(f"Duration: {track.duration_ms / 1000:.0f}s")
    print()
    print("Top candidates:")

    for index, (score, candidate) in enumerate(ranked[:limit], start=1):
        duration = (
            f"{candidate.duration:.0f}s"
            if candidate.duration is not None
            else "unknown"
        )
        positions = ", ".join(
            f"{position + 1}"
            for position in sorted(candidate.positions)
        )
        query_types = ", ".join(sorted(candidate.query_types))

        print(f"{index}. [{score:.2f}] {candidate.title}")
        print(f"   Channel: {candidate.channel or 'unknown'}")
        print(f"   Duration: {duration}")
        print(f"   Positions: {positions}")
        print(f"   Queries: {query_types}")
        print(f"   URL: {candidate.url}")


def extract_track(url: str) -> Optional[str]:
    """
    Return the matching YouTube URL for one Spotify track
    """
    data = _spotify_client().get_track(url)
    return _best_match_url(_track_from_data(data))


def extract_album(url: str) -> list[str]:
    """
    Return matching YouTube URLs for every track in a Spotify album
    """
    album = _spotify_client().get_album(url)
    return _resolve_all(_safe_convert(album.tracks))


def extract_playlist(
    url: str,
    max_tracks: Optional[int] = NO_TRACK_LIMIT,
) -> list[str]:
    """
    Return matching YouTube URLs for every track in a Spotify playlist
    """
    playlist = _spotify_client().get_playlist(
        url,
        max_tracks=max_tracks,
    )

    return _resolve_all(
        _safe_convert(pt.track for pt in playlist.tracks)
    )


def _resolve_all(tracks: list[_SpotifyTrack]) -> list[str]:
    """
    Resolve tracks one by one
    """
    urls = []

    for track in tracks:
        try:
            url = _best_match_url(track)
        except yt_dlp.utils.DownloadError:
            continue

        if url:
            urls.append(url)

    return urls


def extract(
    url: str,
    max_tracks: Optional[int] = NO_TRACK_LIMIT,
) -> list[str]:

    if "/track/" in url:
        match = extract_track(url)
        return [match] if match else []

    if "/album/" in url:
        return extract_album(url)

    if "/playlist/" in url:
        return extract_playlist(
            url,
            max_tracks=max_tracks,
        )

    raise ValueError(f"Unsupported Spotify URL: {url}")
