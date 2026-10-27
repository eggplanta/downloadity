"""
Downloads a link from the terminal, like the app
Usage: test_general.py [url] [audio|video] [kbps|height]
Files go to tests/output/downloadity
"""
import sys
from time import perf_counter

import paths
from downloadity.download_queue import DownloadQueue
from downloadity.media import resolve_media

args = sys.argv[1:]
url = args[0] if args else input("Paste the link: ")

start = perf_counter()
media = resolve_media(url)
if media is None:
    raise SystemExit("Invalid link")
print(f"validated in {perf_counter() - start:.1f}s")

for kind in ("audio", "video"):
    labels = [f"{q.label} ({q.filesize_label})" for q in getattr(media.options, kind)]
    print(f"{kind}: {', '.join(labels) or '-'}")

kind = args[1] if len(args) > 1 else input("\naudio or video? ")
value = int(args[2] if len(args) > 2 else input("kbps or height: "))


class Printer:
    def on_item_start(self, item):
        print(f"[{item.position}/{item.total}] {item.artist} - {item.title}")

    def on_progress(self, fraction):
        pass

    def on_finished(self, done, failed, folder):
        print(f"\ndone: {done}, failed: {failed}\nfolder: {folder}")


start = perf_counter()
DownloadQueue(media, kind, value, str(paths.OUTPUT / "downloadity"), Printer()).run()
print(f"downloaded in {perf_counter() - start:.1f}s")
