from downloadity import spotify

url = input("Paste the Spotify playlist link: ")

playlist = spotify._spotify_client().get_playlist(url)
tracks = spotify._safe_convert(pt.track for pt in playlist.tracks)

index = int(input("Which track index was wrong? "))
spotify.debug_match(tracks[index])
track = tracks[index]

artists = ", ".join(track.artists)
print(f"Search this on YouTube: {artists} - {track.title}")
