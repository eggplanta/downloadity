"""
Shows the YouTube match of each Spotify track
Usage: test_spotify.py [url]
"""
import sys
from time import perf_counter

import paths  # noqa: F401
from downloadity import spotify

url = sys.argv[1] if len(sys.argv) > 1 else input("Paste the Spotify link: ")

name, tracks = spotify.get_collection(url)
print(f"{name or 'track'}: {len(tracks)} track(s)\n")

for index, track in enumerate(tracks, start=1):
    start = perf_counter()
    match = spotify.best_match_url(track)
    elapsed = perf_counter() - start

    print(f"{index}. {', '.join(track.artists)} - {track.title}")
    print(f"   {match or 'no match'} ({elapsed:.1f}s)")
