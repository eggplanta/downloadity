import os
import re
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

from . import extractor, spotify
from .downloader import download_audio, download_video
from .formats import build_quality_options, pick_quality
from .media import AUDIO_ONLY_HOSTS, Media, MediaEntry
from .throttle import YoutubeBlockedError, is_block


@dataclass
class QueueItem:
    position: int
    total: int
    title: str
    artist: str
    extra: object = None


class DownloadQueue:
    """
    Downloads one item at a time
    Prepares the next item while the current one downloads
    Blocked items go to the end of the queue once
    """

    def __init__(self, media: Media, kind: str, value: int, root_dir: str, listener, prepare_extra=None):
        self.media = media
        self.kind = kind
        self.value = value
        self.listener = listener
        self.prepare_extra = prepare_extra
        self.audio_only = any(host in media.source_url for host in AUDIO_ONLY_HOSTS)

        self.output_dir = root_dir
        if media.is_playlist:
            self.output_dir = os.path.join(root_dir, safe_name(media.title or "playlist"))

    def run(self) -> None:
        os.makedirs(self.output_dir, exist_ok=True)

        entries = self.media.entries
        pending = deque(range(len(entries)))
        requeued = set()
        done = 0
        failed = []

        with ThreadPoolExecutor(max_workers=1) as executor:
            future, future_index = None, None

            while pending:
                index = pending.popleft()
                if future_index != index:
                    future = executor.submit(self._prepare, index)

                try:
                    extra = future.result()
                    blocked = False
                except YoutubeBlockedError:
                    extra, blocked = None, True

                if blocked:
                    if index in requeued:
                        failed.append(failed_title(entries[index]))
                    else:
                        requeued.add(index)
                        pending.append(index)

                # Prepare the next item in the background
                future_index = pending[0] if pending else None
                if future_index is not None:
                    future = executor.submit(self._prepare, future_index)

                if blocked:
                    continue

                entry = entries[index]
                if entry.info is None:
                    failed.append(failed_title(entry))
                    continue

                title, artist = display_names(entry)
                self.listener.on_item_start(QueueItem(
                    position=done + len(failed) + 1,
                    total=len(entries),
                    title=title,
                    artist=artist,
                    extra=extra,
                ))

                failed_name = failed_title(entry)
                result = self._download(entry)

                if result.get("blocked") and index not in requeued:
                    requeued.add(index)
                    pending.append(index)
                elif result.get("success"):
                    done += 1
                else:
                    failed.append(failed_name)

        self.listener.on_finished(done, failed, self.output_dir)

    # Internal helpers

    def _prepare(self, index: int):
        entry = self.media.entries[index]

        if entry.info is None:
            if entry.url is None and entry.spotify_track:
                entry.url = spotify.best_match_url(entry.spotify_track)

            if entry.url:
                info = extractor.extract(entry.url)
                if info["type"] == "video":
                    entry.info = info

        if entry.info is None or self.prepare_extra is None:
            return None

        try:
            return self.prepare_extra(entry)
        except Exception:
            return None

    def _download(self, entry: MediaEntry) -> dict:
        options = build_quality_options(entry.info)
        if self.audio_only:
            options.video = []

        qualities = options.audio if self.kind == "audio" else options.video
        quality = pick_quality(qualities, self.value)
        if quality is None:
            return {"success": False}

        if self.kind == "audio":
            expected = quality.filesize
            download = download_audio
        else:
            expected = quality.total_filesize
            download = download_video

        result = download(
            entry.url,
            quality,
            output_dir=self.output_dir,
            on_progress=self._progress_hook(expected),
        )

        if not result["success"] and is_block(result.get("error") or ""):
            result["blocked"] = True

        entry.info = None
        return result

    def _progress_hook(self, expected: Optional[int]):
        downloaded = {}

        def hook(d):
            if d["status"] not in ("downloading", "finished"):
                return

            name = d.get("filename")
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded[name] = d.get("downloaded_bytes") or total or 0

            # Video + audio are two files
            if expected:
                fraction = sum(downloaded.values()) / expected
            elif total:
                fraction = downloaded[name] / total
            else:
                return

            self.listener.on_progress(min(fraction, 1.0))

        return hook


def display_names(entry: MediaEntry) -> tuple[str, str]:
    track = entry.spotify_track
    if track:
        return track.title, ", ".join(track.artists)

    info = (entry.info or {}).get("ytdlp_info") or {}
    title = info.get("track") or info.get("title") or ""
    artist = info.get("artist") or info.get("uploader") or info.get("channel") or ""

    artist = artist.removesuffix(" - Topic")
    return title.removeprefix(f"{artist} - "), artist


def failed_title(entry: MediaEntry) -> str:
    return display_names(entry)[0] or entry.title or "unknown title"


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip(" .")
    return name or "playlist"
