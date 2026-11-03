[app]

title = downloadity
package.name = downloadity
package.domain = io.github.eggplanta
version = 1.0.2

source.dir = .
source.include_exts = py,ttf
source.include_patterns = main.py,service.py,UI/*,src/downloadity/*
source.exclude_patterns = recipes/*,LICENSE,buildozer.spec,pyproject.toml,README.md
source.exclude_dirs = tests,android_src,android_res,bin,.venv,.git,.buildozer,__pycache__

requirements = python3==3.13.18,hostpython3==3.13.18,kivy,pyjnius,ffmpeg_cli,charset_normalizer,yt-dlp,spotifyscraper,mutagen,httpx,httpcore,h11,anyio,sniffio,idna,certifi,typing-extensions

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,POST_NOTIFICATIONS,WAKE_LOCK,REQUEST_INSTALL_PACKAGES
services = Keepalive:service.py:foreground:foregroundServiceType=dataSync
android.add_src = android_src
android.add_resources = android_res/values-v29/theme.xml:values-v29/theme.xml
presplash.filename = android_res/presplash.jpg
android.presplash_color = #000000
p4a.extra_args = --native-service=io.github.eggplanta.downloadity.DownloadAnchor
android.api = 35
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.release_artifact = apk

p4a.local_recipes = ./recipes

[buildozer]

log_level = 2
warn_on_root = 1
