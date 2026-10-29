"""
Record of what each playlist folder holds
One hidden JSON file per folder
"""
import json
import os
import threading
from typing import Optional

MANIFEST = ".downloadity.json"

_lock = threading.Lock()


def find_folder(root: str, playlist_id: Optional[str]) -> Optional[str]:
    """
    Folder recorded for this playlist, any name
    """
    if not playlist_id or not os.path.isdir(root):
        return None

    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        if _read(folder).get("playlist_id") == playlist_id:
            return folder
    return None


def rename_folder(folder: str, name: str) -> str:
    """
    Follows the playlist's new name
    """
    target = os.path.join(os.path.dirname(folder), name)
    if os.path.basename(folder) == name or os.path.exists(target):
        return folder

    os.rename(folder, target)
    return target


def previous_kind(folder: str) -> str:
    # Last downloaded kind, likely chosen again
    data = _read(folder)
    items = data.get("items", {})
    return data.get("last_kind") or max(("audio", "video"), key=lambda kind: len(items.get(kind, {})))


def new_entries(folder: Optional[str], kind: str, entries: list) -> list:
    """
    Not recorded for this kind, or file gone
    """
    items = _read(folder).get("items", {}).get(kind, {}) if folder else {}
    return [e for e in entries if not _present(folder, items.get(e.item_id))]


def recorded_file(folder: str, kind: str, item_id: Optional[str]) -> Optional[str]:
    name = _read(folder).get("items", {}).get(kind, {}).get(item_id)
    return name and os.path.join(folder, name)


def record(folder: str, kind: str, item_id: Optional[str], path: str, playlist_id: str, source: str) -> None:
    if not item_id:
        return

    with _lock:
        data = _read(folder) or {"playlist_id": playlist_id, "source": source, "items": {}}
        data["items"].setdefault(kind, {})[item_id] = os.path.basename(path)
        data["last_kind"] = kind
        _write(folder, data)


# Internal helpers

def _present(folder: Optional[str], name: Optional[str]) -> bool:
    return bool(folder and name) and os.path.exists(os.path.join(folder, name))


def _read(folder: Optional[str]) -> dict:
    try:
        with open(os.path.join(folder, MANIFEST), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, TypeError, ValueError):
        return {}


def _write(folder: str, data: dict) -> None:
    # Atomic, a crash keeps the old file
    path = os.path.join(folder, MANIFEST)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(temp, path)
