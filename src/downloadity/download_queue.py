import glob
import os
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

import yt_dlp

from .covers import cover_image, embed_tags
from .downloader import cut_video, download_audio, download_video
from .extractor import SilentLogger
from . import library
from .extractor import VIDEO_LONG_SIDES
from .formats import build_quality_options, pick_quality
from .media import AUDIO_ONLY_HOSTS, Media, MediaEntry, caption_title, extract_entry
from .throttle import YoutubeBlockedError, is_block

PAIR = 2
MIN_SHOW = 1.5
DOWNLOAD_SHARE = 0.2
ASSUMED_SPEED = 5 * 2**20
CUT_COST = 0.005
CONVERT_RATE = 0.017
DEFAULT_DURATION = 180
TICK = 0.1
# Video may end in any of these
VIDEO_EXTS = ("mp4", "webm", "mkv")
# Leaves room for name suffixes
NAME_BYTES = 180


@dataclass
class QueueItem:
    position: int
    total: int
    title: str
    artist: str
    extra: object = None


class DownloadQueue:
    """
    Downloads in pairs, single items alone
    Prepares the next items while others download
    Blocked items go to the end of the queue once
    """

    def __init__(self, media: Media, kind: str, value, root_dir: str, listener, prepare_extra=None, cut=None, overwrite=False, on_saved=None):
        self.media = media
        self.cut = cut
        self.overwrite = overwrite
        self.kind = kind
        self.value = value
        self.listener = listener
        self.on_saved = on_saved
        self.prepare_extra = prepare_extra
        self.convert_rate = CONVERT_RATE
        self.last_path = None
        self.audio_only = any(host in media.source_url for host in AUDIO_ONLY_HOSTS)

        self.output_dir = root_dir
        if media.is_playlist:
            self.folder_name = safe_name(media.title or "playlist")
            found = library.find_folder(root_dir, media.playlist_id)
            self.output_dir = found or library.free_folder(root_dir, self.folder_name)

    def run(self) -> None:
        # Renamed playlists rename their folder
        if self.media.is_playlist and os.path.isdir(self.output_dir):
            self.output_dir = library.rename_folder(self.output_dir, self.folder_name)
        os.makedirs(self.output_dir, exist_ok=True)
        self._run_pairs()

    # Internal helpers

    def _run_pairs(self) -> None:
        """
        Downloads PAIR items at a time
        The next batch waits for all
        Single items still get MIN_SHOW
        """
        entries = self.media.entries
        pending = deque(range(len(entries)))
        requeued = set()
        prepared = {}
        done = 0
        failed = []
        video = self.kind == "video"

        def requeue_or_fail(index, name):
            if index in requeued:
                failed.append(name)
            else:
                requeued.add(index)
                pending.append(index)

        with ThreadPoolExecutor(PAIR) as prepare_pool, ThreadPoolExecutor(PAIR) as download_pool:
            while pending:
                # Prepare this batch and the next
                for index in list(pending)[:2 * PAIR]:
                    if index not in prepared:
                        prepared[index] = prepare_pool.submit(self._prepare, index)

                batch = []
                downloads = {}
                while pending and len(batch) < PAIR:
                    index = pending.popleft()
                    entry = entries[index]
                    future = prepared.pop(index, None) or prepare_pool.submit(self._prepare, index)
                    try:
                        extra = future.result()
                    except YoutubeBlockedError:
                        requeue_or_fail(index, failed_title(entry, video))
                        continue

                    if entry.info is None:
                        failed.append(failed_title(entry, video))
                        continue

                    title, artist = display_names(entry, video)
                    item = QueueItem(
                        position=done + len(failed) + len(batch) + 1,
                        total=len(entries),
                        title=title,
                        artist=artist,
                        extra=extra,
                    )

                    # Show A while B prepares
                    if not batch:
                        self.listener.on_item_start(item)
                        shown_at = time.monotonic()

                    # Read now, the download clears info
                    measure = self._measure(entry)
                    # Starts before its pair is ready
                    report = _LateReport(None if batch else self.listener)
                    future = download_pool.submit(self._download, entry, report)
                    downloads[future] = (len(batch), index, failed_title(entry, video), report)
                    batch.append((index, measure, item))

                if not batch:
                    continue

                items = [item for _, _, item in batch]
                weights = self._weights([measure for _, measure, _ in batch])
                display = _PairDisplay(self.listener, items, weights, shown_at)
                for k, _, _, report in downloads.values():
                    report.attach(display.report(k))

                for future in as_completed(downloads):
                    k, index, name, _ = downloads[future]
                    result = future.result()
                    display.complete(k)

                    if result.get("blocked"):
                        requeue_or_fail(index, name)
                    elif result.get("success"):
                        done += 1
                    else:
                        failed.append(name)

                display.finish()

        self.listener.on_finished(done, failed, self.output_dir)

    def _prepare(self, index: int):
        entry = self.media.entries[index]

        if entry.info is None:
            extract_entry(entry)

        if entry.info is not None and self.kind == "audio" and entry.cover is None:
            self._fetch_cover(entry)

        if entry.info is None or self.prepare_extra is None:
            return None

        try:
            return self.prepare_extra(entry)
        except Exception:
            return None

    def _quality(self, entry: MediaEntry):
        options = build_quality_options(entry.info, self.media.formats)
        if self.audio_only:
            options.video = []

        qualities = options.audio if self.kind == "audio" else options.video
        return pick_quality(qualities, self.value)

    def _expected_size(self, quality) -> Optional[int]:
        return quality.filesize if self.kind == "audio" else quality.total_filesize

    def _measure(self, entry: MediaEntry) -> tuple:
        # Expected size and duration
        quality = self._quality(entry)
        return quality and self._expected_size(quality), entry.info.get("duration")

    @staticmethod
    def _weights(measures: list[tuple]) -> list[float]:
        """
        Sizes if all known, else durations
        """
        sizes = [size for size, _ in measures]
        if all(sizes):
            return sizes

        durations = [duration for _, duration in measures]
        if all(durations):
            return durations
        return [1] * len(measures)

    def _download(self, entry: MediaEntry, report) -> dict:
        quality = self._quality(entry)
        if quality is None:
            return {"success": False}

        expected = self._expected_size(quality)
        report = _monotonic(report)
        options = {"overwrite": self.overwrite}

        download = download_audio if self.kind == "audio" else download_video
        conversion = None
        on_download = report

        # Only foreign codecs get converted
        if self.kind == "audio" and not quality.native:
            conversion = _ConversionProgress(self, report, entry.info.get("duration"))
            options["on_postprocess"] = conversion.hook
            on_download = lambda fraction: report(DOWNLOAD_SHARE * fraction)

        info = entry.info["ytdlp_info"]
        caption = caption_title(info)
        if caption:
            options["filename"] = safe_name(f"{caption} [{info.get('id')}]")
        elif self.kind == "audio":
            options["filename"] = safe_name(song_name(entry))
        if not self.cut:
            name = options.get("filename") or safe_name(template_name(info))
            exts = (quality.codec,) if self.kind == "audio" else VIDEO_EXTS
            options["filename"] = free_name(self.output_dir, name, exts)

        # Cuts download the full video first
        if self.cut:
            base = options.get("filename") or safe_name(info.get("title") or "video")
            options["filename"] = f"{base}.full"
            cut_progress = _CutProgress(report, expected, quality.height, info.get("fps"), self.cut)
            on_download = cut_progress.download

        try:
            result = download(
                entry.url,
                quality,
                output_dir=self.output_dir,
                on_progress=self._progress_hook(expected, on_download),
                info=info,
                **options,
            )

            # Expired links need a fresh extraction
            if not result["success"] and not entry.embedded and not is_block(result.get("error") or ""):
                result = download(
                    entry.url,
                    quality,
                    output_dir=self.output_dir,
                    on_progress=self._progress_hook(expected, on_download),
                    **options,
                )
        finally:
            if conversion:
                conversion.stop()

        if result["success"] and self.cut:
            result = self._cut(base, cut_progress.cut)
        if result["success"]:
            self.last_path = result.get("path")
        if result["success"] and self.kind == "audio":
            self._add_tags(entry, result.get("path"))
        if result["success"] and self.on_saved and result.get("path"):
            self.on_saved(result["path"])
        if result["success"] and self.media.is_playlist:
            self._record(entry, result.get("path"))

        if not result["success"] and is_block(result.get("error") or ""):
            result["blocked"] = True

        if not entry.embedded:
            entry.info = None
        return result

    def _fetch_cover(self, entry: MediaEntry) -> None:
        """
        One image for art and file
        """
        track = entry.spotify_track
        try:
            entry.cover = cover_image(entry.info["ytdlp_info"], track and track.cover_url)
        except Exception as e:
            print("cover failed:", e)

    def _add_tags(self, entry: MediaEntry, path: Optional[str]) -> None:
        """
        Missing tags never fail a download
        """
        cover, entry.cover = entry.cover, None
        if not path:
            return

        try:
            embed_tags(path, cover, audio_tags(entry))
        except Exception as e:
            print("tags failed:", e)

    def _record(self, entry: MediaEntry, path: Optional[str]) -> None:
        """
        Notes the file, drops a renamed old one
        """
        if not path:
            return

        old = library.recorded_file(self.output_dir, self.kind, entry.item_id)
        if old and os.path.basename(old) != os.path.basename(path) and os.path.exists(old):
            os.remove(old)
        library.record(self.output_dir, self.kind, entry.item_id, path, self.media.playlist_id, self.media.source_url)

    def _cut(self, base: str, on_cut) -> dict:
        """
        Cuts the full download, then deletes it
        """
        found = glob.glob(os.path.join(glob.escape(self.output_dir), glob.escape(base) + ".full.*"))
        if not found:
            return {"success": False}

        start, end = self.cut
        ext = self.media.formats.video
        name = free_name(self.output_dir, f"{base} [{cut_label(start)}-{cut_label(end)}]", (ext,))
        output = os.path.join(self.output_dir, f"{name}.{ext}")
        success = cut_video(found[0], start, end, output, on_cut)
        os.remove(found[0])
        return {"success": success, "path": output}

    def _progress_hook(self, expected: Optional[int], report):
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

            report(min(fraction, 1.0))

        return hook


def _monotonic(report):
    best = [0.0]

    def update(fraction):
        best[0] = max(best[0], fraction)
        report(best[0])

    return update


class _ConversionProgress:
    """
    Time-based bar while ffmpeg converts
    Learns seconds per audio second
    """

    def __init__(self, queue: DownloadQueue, report, duration: Optional[float]):
        self.queue = queue
        self.report = report
        self.duration = duration or DEFAULT_DURATION
        self.started = None
        self.thread = None
        self.done = threading.Event()

    def hook(self, d):
        if d["postprocessor"] != "ExtractAudio":
            return

        if d["status"] == "started" and self.started is None:
            self.started = time.monotonic()
            self.thread = threading.Thread(target=self._tick, daemon=True)
            self.thread.start()
        elif d["status"] == "finished" and self.started is not None and not self.done.is_set():
            self.queue.convert_rate = (time.monotonic() - self.started) / self.duration
            self.stop()

    def stop(self) -> None:
        self.done.set()
        if self.thread:
            self.thread.join()

    def _tick(self) -> None:
        while not self.done.wait(TICK):
            elapsed = time.monotonic() - self.started
            fraction = min(0.99, elapsed / (self.queue.convert_rate * self.duration))
            self.report(DOWNLOAD_SHARE + (1 - DOWNLOAD_SHARE) * fraction)


class _CutProgress:
    """
    Download and cut share the bar
    Shares follow the estimated times
    """

    def __init__(self, report, size: Optional[int], height: int, fps: Optional[float], cut: tuple):
        self.report = report
        self.size = size or 0
        megapixels = VIDEO_LONG_SIDES.get(height, height * 16 / 9) * height / 1e6
        self.cut_time = (cut[1] - cut[0]) * (fps or 30) * megapixels * CUT_COST
        self.started = time.monotonic()
        self.share = self._share(ASSUMED_SPEED)

    def download(self, fraction: float) -> None:
        # Measured speed replaces the guess
        elapsed = time.monotonic() - self.started
        if self.size and fraction > 0 and elapsed > 1:
            self.share = self._share(self.size * fraction / elapsed)
        self.report(self.share * fraction)

    def cut(self, fraction: float) -> None:
        self.report(self.share + (1 - self.share) * fraction)

    def _share(self, speed: float) -> float:
        download_time = self.size / speed if self.size else self.cut_time
        return download_time / (download_time + self.cut_time)


class _PairDisplay:
    """
    Shows a batch one item at a time
    Each item owns a share of the batch progress
    Bigger items stay longer, at least MIN_SHOW
    """

    def __init__(self, listener, items: list[QueueItem], weights: list[float], shown_at: float):
        self.listener = listener
        self.items = items
        total = sum(weights)
        self.shares = [weight / total for weight in weights]
        self.ends = [sum(self.shares[:k + 1]) for k in range(len(items))]
        self.fractions = [0.0] * len(items)
        self.lock = threading.Lock()
        self.current = 0
        self.shown_at = shown_at

    def report(self, index: int):
        def update(fraction):
            with self.lock:
                self.fractions[index] = fraction
                self._update()

        return update

    def complete(self, index: int) -> None:
        self.report(index)(1.0)

    def finish(self) -> None:
        """
        Shows the rest, each for MIN_SHOW
        """
        while True:
            with self.lock:
                self._update()
                if self.current == len(self.items) - 1 and self._shown_time() >= MIN_SHOW:
                    return
            time.sleep(TICK)

    def _update(self) -> None:
        progress = sum(f * s for f, s in zip(self.fractions, self.shares))
        last = len(self.items) - 1

        # Next item after its share and MIN_SHOW
        while (
            self.current < last
            and progress >= self.ends[self.current]
            and self._shown_time() >= MIN_SHOW
        ):
            self.listener.on_progress(1.0)
            self._show_next()

        start = self.ends[self.current] - self.shares[self.current]
        fraction = (progress - start) / self.shares[self.current]
        # Finished items still fill gradually
        fraction = min(fraction, self._shown_time() / MIN_SHOW)
        self.listener.on_progress(min(1.0, max(0.0, fraction)))

    def _shown_time(self) -> float:
        return time.monotonic() - self.shown_at

    def _show_next(self) -> None:
        self.current += 1
        self.shown_at = time.monotonic()
        self.listener.on_item_start(self.items[self.current])


class _LateReport:
    """
    Progress sent before the batch display exists
    The shown item feeds the bar directly
    """

    def __init__(self, listener=None):
        self.listener = listener
        self.target = None
        self.last = 0.0
        self.lock = threading.Lock()

    def __call__(self, fraction: float) -> None:
        with self.lock:
            self.last = fraction
            if self.target:
                self.target(fraction)
            elif self.listener:
                self.listener.on_progress(min(1.0, fraction))

    def attach(self, target) -> None:
        with self.lock:
            self.target = target
            target(self.last)


def audio_tags(entry: MediaEntry) -> dict:
    title, artist = display_names(entry)
    track = entry.spotify_track
    info = (entry.info or {}).get("ytdlp_info") or {}
    tags = {
        "title": title,
        "artist": artist,
        "album": track.album if track else info.get("album"),
        "tracknumber": track.track_number if track else info.get("track_number"),
        "date": track.year if track else info.get("release_year"),
    }
    return {key: str(value) for key, value in tags.items() if value}


def song_name(entry: MediaEntry) -> str:
    """
    "Artist - Title" for music files
    """
    title, artist = display_names(entry)
    if not (artist and title):
        return title or artist or "audio"

    # Long credits drop trailing artists
    artists = artist.split(", ")
    while len(artists) > 1 and len(f"{', '.join(artists)} - {title}".encode()) > NAME_BYTES:
        artists.pop()
    return f"{', '.join(artists)} - {title}"


def display_names(entry: MediaEntry, video: bool = False) -> tuple[str, str]:
    track = entry.spotify_track
    if track:
        return track.title, ", ".join(track.artists)

    info = (entry.info or {}).get("ytdlp_info") or {}
    caption = caption_title(info)
    if caption:
        return caption, info.get("uploader") or info.get("channel") or ""

    if video:
        return info.get("title") or "", info.get("uploader") or info.get("channel") or ""

    title = info.get("track") or info.get("title") or ""
    artist = info.get("artist") or info.get("uploader") or info.get("channel") or ""

    artist = ", ".join(dict.fromkeys(artist.removesuffix(" - Topic").split(", ")))
    for dash in ("-", "–", "—"):
        title = title.removeprefix(f"{artist} {dash} ")
    return title, artist


def failed_title(entry: MediaEntry, video: bool = False) -> str:
    return display_names(entry, video)[0] or entry.title or "unknown title"


def cut_label(seconds: float) -> str:
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}.{minutes:02d}.{secs:02d}" if hours else f"{minutes}.{secs:02d}"


def template_name(info: dict) -> str:
    # Same name yt-dlp would pick
    with yt_dlp.YoutubeDL({"outtmpl": "%(title)s", "logger": SilentLogger()}) as ydl:
        return ydl.prepare_filename(info)


def free_name(folder: str, name: str, exts: tuple) -> str:
    """
    Files from a previous install
    can't be overwritten, so pick another name
    """
    candidate = name
    for number in range(2, 100):
        if all(_usable(os.path.join(folder, f"{candidate}.{ext}")) for ext in exts):
            if candidate != name:
                print("name taken, saving as", candidate, flush=True)
            return candidate
        candidate = f"{name} ({number})"
    return name


def _usable(path: str) -> bool:
    # Ours to overwrite, or free
    if os.path.exists(path):
        try:
            open(path, "r+b").close()
        except OSError:
            return False
        return True
    # Missing folders are made later
    if not os.path.isdir(os.path.dirname(path)):
        return True
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except OSError:
        return False
    os.remove(path)
    return True


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip(" .")
    # Names are capped at 255 bytes
    name = name.encode()[:NAME_BYTES].decode(errors="ignore").strip(" .")
    return name or "playlist"
