"""
Self updates: stable libraries and the APK
New libraries apply on the next launch
Broken ones roll back to the previous
"""
import compileall
import hashlib
import importlib
import json
import os
import re
import shutil
import ssl
import sys
import threading
import traceback
import urllib.request
import zipfile
from typing import Optional

import certifi

# PyPI name -> import name
LIBS = {"yt-dlp": "yt_dlp", "spotifyscraper": "spotify_scraper"}
PYPI_URL = "https://pypi.org/pypi/{}/json"
RELEASES_URL = "https://api.github.com/repos/eggplanta/downloadity/releases/latest"
STATE_FILE = "state.json"
TIMEOUT = 20
CHUNK = 1 << 16

_lock = threading.Lock()
_root: Optional[str] = None
active: dict[str, str] = {}


# Libraries

def activate(root: str, app_version: str) -> None:
    """
    Before any import of the libraries
    Applies pending versions, rolls back broken ones
    """
    global _root
    _root = root
    os.makedirs(root, exist_ok=True)
    state = _read_state()

    # New APKs may bundle newer libraries
    if state.get("app_version") != app_version:
        state["bundled"] = {name: _bundled_version(module) for name, module in LIBS.items()}
        state["app_version"] = app_version

    for name, module in LIBS.items():
        lib = state.setdefault(name, {})
        bundled = state["bundled"].get(name) or "0"

        # Unconfirmed launch means it crashed
        if lib.get("trial") or lib.get("revert"):
            _roll_back(lib)
        if lib.get("pending"):
            lib["previous"], lib["current"] = lib.get("current"), lib.pop("pending")
            lib["trial"] = True
        for key in ("current", "previous", "pending"):
            if lib.get(key) and _key(lib[key]) <= _key(bundled):
                lib[key] = None
        if not lib.get("current"):
            lib.pop("trial", None)
            lib["previous"] = None

        while True:
            folder = lib.get("current") and _folder(name, lib["current"])
            if folder and not os.path.isdir(folder):
                _roll_back(lib)
                continue
            if folder:
                sys.path.insert(0, folder)
            try:
                active[name] = _version(importlib.import_module(module))
                print(f"update: using {name} {active[name]} ({'downloaded' if folder else 'bundled'})", flush=True)
                break
            except Exception:
                traceback.print_exc()
                if not folder:
                    raise
                _unload(module, folder)
                _roll_back(lib)

        _clean(name, lib)

    _write_state(state)


def confirm() -> None:
    """
    The app started, trial versions are good
    """
    with _lock:
        state = _read_state()
        for name in LIBS:
            state.get(name, {}).pop("trial", None)
        _write_state(state)


def report(error: BaseException) -> None:
    """
    Errors raised inside an updated library
    roll it back on the next launch
    """
    if not _root:
        return

    files = [frame.filename for frame in traceback.extract_tb(error.__traceback__)]
    with _lock:
        state = _read_state()
        for name in LIBS:
            lib = state.get(name, {})
            folder = lib.get("current") and _folder(name, lib["current"])
            if folder and any(f.startswith(folder + os.sep) for f in files):
                print(f"update: {name} {lib['current']} failed, rolling back", flush=True)
                lib["revert"] = True
        _write_state(state)


def check_libs() -> None:
    """
    Downloads newer stable versions for the next launch
    """
    for name in LIBS:
        try:
            _check_lib(name)
        except Exception as e:
            print(f"update: {name} check failed: {e}", flush=True)


# APK

def latest_apk(current: str) -> Optional[dict]:
    """
    Newer release with an APK, or None
    """
    release = _get_json(RELEASES_URL)
    version = (release.get("tag_name") or "").lstrip("v")
    if not version or _key(version) <= _key(current):
        return None

    for asset in release.get("assets") or []:
        if asset.get("name", "").endswith(".apk"):
            return {"version": version, "url": asset["browser_download_url"], "size": asset.get("size")}
    return None


def download(url: str, file, on_progress=None, sha256: Optional[str] = None) -> None:
    """
    Streams url into an open binary file
    """
    digest = hashlib.sha256()
    with _open(url) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(CHUNK):
            file.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if on_progress and total:
                on_progress(done / total)

    if sha256 and digest.hexdigest() != sha256:
        raise ValueError("checksum mismatch")


# Internal helpers

def _check_lib(name: str) -> None:
    info = _get_json(PYPI_URL.format(name))
    # Info holds the latest stable
    version = info["info"]["version"]

    with _lock:
        state = _read_state()
    lib = state.get(name, {})
    newest = max(active.get(name, "0"), state.get("bundled", {}).get(name) or "0", key=_key)
    known = {lib.get("pending"), *lib.get("bad", [])}
    if version in known or _key(version) <= _key(newest):
        return

    wheel = next(
        (f for f in info.get("urls", []) if f.get("packagetype") == "bdist_wheel" and f["filename"].endswith("py3-none-any.whl")),
        None,
    )
    if wheel is None:
        return

    folder = _folder(name, version)
    temp = folder + ".tmp"
    shutil.rmtree(temp, ignore_errors=True)
    os.makedirs(temp)
    archive = os.path.join(temp, "wheel.zip")
    try:
        with open(archive, "wb") as f:
            download(wheel["url"], f, sha256=wheel["digests"]["sha256"])
        with zipfile.ZipFile(archive) as z:
            z.extractall(temp)
        os.remove(archive)
        # First launch skips compiling
        compileall.compile_dir(temp, quiet=1, workers=1)
        shutil.rmtree(folder, ignore_errors=True)
        os.replace(temp, folder)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise

    with _lock:
        state = _read_state()
        state.setdefault(name, {})["pending"] = version
        _write_state(state)
    print(f"update: {name} {version} ready for next launch", flush=True)


def _bundled_version(module: str) -> Optional[str]:
    try:
        version = _version(importlib.import_module(module))
    except Exception:
        return None
    _unload(module, None)
    return version


def _roll_back(lib: dict) -> None:
    bad = lib.get("current")
    if bad:
        lib.setdefault("bad", []).append(bad)
    lib["current"], lib["previous"] = lib.get("previous"), None
    lib.pop("trial", None)
    lib.pop("revert", None)


def _unload(module: str, folder: Optional[str]) -> None:
    if folder in sys.path:
        sys.path.remove(folder)
    for loaded in [m for m in sys.modules if m == module or m.startswith(module + ".")]:
        del sys.modules[loaded]
    importlib.invalidate_caches()


def _clean(name: str, lib: dict) -> None:
    # Keeps only versions in use
    keep = {lib.get("current"), lib.get("previous"), lib.get("pending")}
    base = os.path.join(_root, name)
    if not os.path.isdir(base):
        return
    for version in os.listdir(base):
        if version not in keep:
            shutil.rmtree(os.path.join(base, version), ignore_errors=True)


def _folder(name: str, version: str) -> str:
    return os.path.join(_root, name, version)


def _version(module) -> str:
    version = getattr(module, "__version__", None)
    if version is None:
        version = importlib.import_module(f"{module.__name__}.version").__version__
    return version


def _key(version: str) -> tuple:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def _read_state() -> dict:
    try:
        with open(os.path.join(_root, STATE_FILE), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_state(state: dict) -> None:
    path = os.path.join(_root, STATE_FILE)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(path + ".tmp", path)


def _get_json(url: str) -> dict:
    with _open(url) as response:
        return json.load(response)


def _open(url: str):
    # Android Python lacks system certificates
    context = ssl.create_default_context(cafile=certifi.where())
    request = urllib.request.Request(url, headers={"User-Agent": "downloadity"})
    return urllib.request.urlopen(request, timeout=TIMEOUT, context=context)
