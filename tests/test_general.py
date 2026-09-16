from downloadity.extractor import extract
from downloadity.formats import build_quality_options
from downloadity.downloader import download_audio, download_video
from downloadity import spotify

url = input("Paste the link: ")

urls_to_process = [url]

if "open.spotify.com" in url:
    print("Spotify link detected, resolving to YouTube...")
    resolved = spotify.extract(url)
    if not resolved:
        print("Could not resolve this Spotify URL to a YouTube match.")
        raise SystemExit(1)
    urls_to_process = resolved
    print(f"Resolved {len(resolved)} track(s)")

mode = input("\nDownload (a)udio or (v)ideo? ")

for track_url in urls_to_process:
    info = extract(track_url, flat=False)

    if info["type"] == "error":
        print(f"Error on {track_url}:", info["message"])
        continue

    opts = build_quality_options(info)
    print(f"\n{opts.title}")

    if mode == "a":
        best = max(opts.audio, key=lambda a: a.bitrate)
        result = download_audio(track_url, best, output_dir=".")
    else:
        best = max(opts.video, key=lambda v: v.height)
        result = download_video(track_url, best, output_dir=".")

    print(result)
