"""
Downloads a set of short playlists through the UI
Logs go to tests/output/logs
"""
import subprocess
import sys
import time

import paths

PLAYLISTS = [
    ("https://www.youtube.com/playlist?list=PLpY7hx7jry7yO2su3JjgsaPdp2-bZGPth", "audio", 48),
    ("https://www.youtube.com/playlist?list=PLXaRb6luN8VJJJlotgmqxsdny5sABG0Km", "audio", 48),
    ("https://www.youtube.com/playlist?list=PLf-4hVC2QHho", "video", 144),
    ("https://www.youtube.com/playlist?list=PLy0tzzdIA_JBPQre0idTQwyxb4sUZJgj5", "audio", 48),
    ("https://www.youtube.com/playlist?list=PLfiMjLyNWxeZl828zfvlnymKB2c9o3cKp", "audio", 48),
    ("https://open.spotify.com/playlist/00WazrS70WN7Mx3OtsB61s", "audio", 48),
    ("https://open.spotify.com/playlist/7fyuMn8ZZh8N3FoJnaP7jo", "audio", 48),
    ("https://open.spotify.com/playlist/6HSu6LcLZ955Rm8KzbHaMB", "audio", 48),
    ("https://open.spotify.com/playlist/5L9PJwHWclFverWwxsnpbS", "audio", 48),
    ("https://open.spotify.com/playlist/1S0YQMmTc4Q1ffRV6zoP7y", "audio", 48),
]

logs = paths.OUTPUT / "logs"
logs.mkdir(parents=True, exist_ok=True)
selected = [int(i) for i in sys.argv[1:]] or range(len(PLAYLISTS))

for index in selected:
    url, kind, value = PLAYLISTS[index]
    start = time.perf_counter()
    with open(logs / f"playlist_{index:02d}.log", "w") as log:
        subprocess.run(
            [sys.executable, "-u", str(paths.ROOT / "tests" / "ui_download.py"), url, kind, str(value), f"playlist_{index:02d}"],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    print(f"{index}: {time.perf_counter() - start:.0f}s {url}", flush=True)
