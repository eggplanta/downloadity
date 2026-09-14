from downloadity.extractor import extract
from downloadity.formats import build_quality_options
from downloadity.downloader import download_audio, download_video
from downloadity import spotify

url = input("Paste the link: ")

if "open.spotify.com" in url:
    print("Spotify link detected, resolving to YouTube...")
    resolved = spotify.extract(url)
    if not resolved:
        print("Could not resolve this Spotify URL to a YouTube match.")
        raise SystemExit(1)
    url = resolved[0]
    print(f"Resolved to: {url}")

info = extract(url, flat=False)

if info["type"] == "error":
    print("Error:", info["message"])
    raise SystemExit(1)
elif info["type"] == "playlist":
    print(f"Playlist with {info['count']} items — using the first one for testing")
    item = info["entries"][0]
    opts = build_quality_options(item)
else:
    opts = build_quality_options(info)

print(f"\n{opts.title}")
print("Audio:", [a.label for a in opts.audio])
print("Video:", [v.label for v in opts.video])

mode = input("\nDownload (a)udio or (v)ideo? ")

if mode == "a":
    best = max(opts.audio, key=lambda a: a.bitrate)
    result = download_audio(url, best, output_dir=".")
else:
    best = max(opts.video, key=lambda v: v.height)
    result = download_video(url, best, output_dir=".")

print(result)
