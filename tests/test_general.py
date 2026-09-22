from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

from downloadity.extractor import extract
from downloadity.formats import build_quality_options
from downloadity.downloader import download_audio, download_video
from downloadity import spotify


def download_one(track_url: str, mode: str) -> dict:
    try:
        info = extract(track_url, flat=False)

        if info["type"] == "error":
            return {
                "success": False,
                "error": info["message"],
            }

        opts = build_quality_options(info)

        if mode == "a":
            if not opts.audio:
                return {
                    "success": False,
                    "error": "No audio formats available.",
                }

            best = max(opts.audio, key=lambda a: a.bitrate)

            return download_audio(
                track_url,
                best,
                output_dir=".",
            )

        if not opts.video:
            return {
                "success": False,
                "error": "No video formats available.",
            }

        best = max(opts.video, key=lambda v: v.height)

        return download_video(
            track_url,
            best,
            output_dir=".",
        )

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


url = input("Paste the link: ")

urls_to_process = [url]

if "open.spotify.com" in url:
    print("Spotify link detected, resolving to YouTube...")

    start = perf_counter()

    resolved = spotify.extract(url)

    elapsed = perf_counter() - start

    if not resolved:
        print("Could not resolve this Spotify URL to a YouTube match.")
        raise SystemExit(1)

    urls_to_process = resolved

    print(f"Resolved {len(resolved)} track(s)")
    print(f"Spotify → YouTube: {elapsed:.2f}s")


mode = input("\nDownload (a)udio or (v)ideo? ").lower()

if mode not in ("a", "v"):
    print("Invalid mode.")
    raise SystemExit(1)


start = perf_counter()

with ThreadPoolExecutor(max_workers=3) as executor:
    results = executor.map(
        lambda track_url: download_one(track_url, mode),
        urls_to_process,
    )

    for result in results:
        print(result)

elapsed = perf_counter() - start

print(f"\nDownloads: {elapsed:.2f}s")
print(f"Total: {elapsed:.2f}s")