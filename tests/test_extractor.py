"""
Prints the qualities of one link
Usage: test_extractor.py [url]
"""
import sys

import paths  # noqa: F401
from downloadity.media import resolve_media

url = sys.argv[1] if len(sys.argv) > 1 else input("Paste the link: ")

media = resolve_media(url)
if media is None:
    raise SystemExit("Invalid link")

print(f"title: {media.title}")
print(f"playlist: {media.is_playlist} ({len(media.entries)} items)")
print(f"invalid: {[e.title for e in media.invalid]}")

for kind in ("audio", "video"):
    print(f"\n{kind.upper()}")
    for quality in getattr(media.options, kind):
        print(f"  {quality.label:>9}  {quality.filesize_label}")
