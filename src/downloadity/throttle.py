import threading
import time

import yt_dlp

BASE_INTERVAL = 0.5
MAX_ATTEMPTS = 6
# Checking reports blocks fast
CHECK_ATTEMPTS = 2

_BLOCK_MARKERS = (
    "confirm you’re not a bot",
    "confirm you're not a bot",
    "HTTP Error 429",
    "rate-limited by YouTube",
    "content isn't available, try again later",
)


class YoutubeBlockedError(Exception):
    pass


class _Throttle:
    """
    Shared spacing between YouTube requests across threads
    Doubles the interval on blocks, resets after
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._interval = BASE_INTERVAL
        self._next_slot = 0.0

    def run(self, request, attempts: int = MAX_ATTEMPTS):
        for attempt in range(1, attempts + 1):
            self._wait()

            try:
                result = request()
            except yt_dlp.utils.DownloadError as e:
                if not is_block(e):
                    raise

                if attempt < attempts:
                    self._back_off(BASE_INTERVAL * 2 ** attempt)
                continue

            self._reset()
            return result

        self._reset()
        raise YoutubeBlockedError(f"YouTube kept blocking after {attempts} attempts")

    def _wait(self):
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_slot)
            self._next_slot = start + self._interval

        time.sleep(start - now)

    def _back_off(self, interval):
        with self._lock:
            self._interval = max(self._interval, interval)
            self._next_slot = time.monotonic() + self._interval

    def _reset(self):
        with self._lock:
            self._interval = BASE_INTERVAL


def is_block(error) -> bool:
    message = str(error)
    return any(marker in message for marker in _BLOCK_MARKERS)


throttle = _Throttle()
