"""
Compares the playlist estimate with the real total
Real total = every item extracted (slow)
Usage: estimate.py url
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

import paths  # noqa: F401
from downloadity import media
from downloadity.formats import build_quality_options, pick_quality

url = sys.argv[1] if len(sys.argv) > 1 else input("Paste the playlist link: ")

start = perf_counter()
result = media.resolve_media(url)
if result is None:
    raise SystemExit("Invalid link")
print(f"validated in {perf_counter() - start:.1f}s, {len(result.entries)} items")

with ThreadPoolExecutor(max_workers=media.WORKERS) as executor:
    list(executor.map(media._extract_entry, [e for e in result.entries if e.info is None]))

items = [build_quality_options(e.info) for e in result.entries if e.info]
if any(host in url for host in media.AUDIO_ONLY_HOSTS):
    for item in items:
        item.video = []
print(f"real total from {len(items)}/{len(result.entries)} items\n")


def real_size(kind, value):
    total = 0
    for item in items:
        quality = pick_quality(getattr(item, kind), value)
        if quality is None or not item.duration:
            continue
        if kind == "audio":
            total += quality.bitrate * 1000 / 8 * item.duration
        else:
            total += quality.total_filesize or 0
    return total


for kind in ("audio", "video"):
    for quality in getattr(result.options, kind):
        real = real_size(kind, quality.value)
        if real and quality.filesize:
            diff = (quality.filesize / real - 1) * 100
            print(f"{quality.label:>9}: estimate {quality.filesize / 2**20:8.1f} MB, real {real / 2**20:8.1f} MB ({diff:+.1f}%)")
