"""
Drives the app: link -> quality -> confirm -> download -> OK
Usage: ui_download.py url audio|video kbps|height [shots name]
Shots and files go to tests/output, per shots name
"""
import os
import re
import sys
import time

import paths

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle

import main
from downloadity.formats import VIDEO_MARGIN, VideoQuality, pick_quality

URL, KIND, VALUE = sys.argv[1], sys.argv[2], int(sys.argv[3])
NAME = sys.argv[4] if len(sys.argv) > 4 else "single"
SHOTS = paths.OUTPUT / "shots" / NAME
SHOTS.mkdir(parents=True, exist_ok=True)
main.DOWNLOAD_ROOT = str(paths.OUTPUT / "downloadity" / NAME)

app = main.DownloadityApp()
state = {"item": None, "shot": set(), "t0": 0.0, "arts": []}


def log(text):
    print(f"{time.perf_counter() - state['t0']:7.1f}s  {text}", flush=True)


def popup():
    return next((w for w in Window.children if isinstance(w, main.AsciiPopup)), None)


def popup_text(p):
    return [w.text for w in p.walk() if isinstance(w, main.Label) and w.text and "─" not in w.text]


def press(p, label):
    for b in p.walk():
        if isinstance(b, main.AsciiButton) and label in b.text_label.text:
            b.dispatch("on_release")
            return


def black_background():
    with app.root.canvas.before:
        Color(0, 0, 0, 1)
        Rectangle(pos=app.root.pos, size=app.root.size)


def shown_size(quality):
    # Same size the confirm popup shows
    if isinstance(quality, VideoQuality):
        return quality.total_filesize and quality.total_filesize * VIDEO_MARGIN
    return quality.filesize


def art_summary(markup):
    colors = set(re.findall(r"#([0-9a-f]{6})", markup))
    rows = markup.count("\n") + 1 if markup else 0
    return f"rows={rows} colors={len(colors)}"


# Flow

def type_link(dt):
    black_background()
    state["t0"] = time.perf_counter()
    app.link_input.text = URL


def wait_valid(dt):
    if not getattr(app, "media", None):
        return Clock.schedule_once(wait_valid, 0.3)

    media = app.media
    log(f"valid: {len(media.entries)} items, {len(media.invalid)} invalid")
    app.download_button.dispatch("on_release")
    quality = pick_quality(getattr(media.options, KIND), VALUE)
    state["estimate"] = shown_size(quality)
    app.on_quality_select(KIND, quality)
    Clock.schedule_once(confirm, 0.5)


def confirm(dt):
    p = popup()
    log(f"confirm: {popup_text(p)[0]!r}")
    press(p, "confirm")
    Clock.schedule_once(skip_invalid, 0.5)


def skip_invalid(dt):
    p = popup()
    if p:
        log(f"invalid popup: {popup_text(p)}")
        press(p, "OK")
    Clock.schedule_once(wait_done, 1)


def wait_done(dt):
    p = popup()
    if not p:
        return Clock.schedule_once(wait_done, 0.5)

    log(f"final: {popup_text(p)}")
    press(p, "OK")
    Clock.schedule_once(finish, 0.5)


def finish(dt):
    p = popup()
    if p:
        log(f"failed popup: {popup_text(p)}")
        press(p, "OK")
        return Clock.schedule_once(finish, 0.5)

    folder = state.get("folder")
    files = sorted(os.listdir(folder)) if folder and os.path.isdir(folder) else []
    total = sum(os.path.getsize(os.path.join(folder, f)) for f in files)
    estimate = state.get("estimate")

    log(f"home: screen={app.screens.current} text={app.link_input.text!r}")
    log(f"folder: {folder} ({len(files)} files, {total / 2**20:.1f} MB)")
    if estimate:
        log(f"estimate: {estimate / 2**20:.1f} MB ({(estimate / total - 1) * 100:+.1f}%)")
    for name in files:
        print(f"          - {name}")

    no_art = [title for title, ok in state["arts"] if not ok]
    log(f"art missing: {no_art or 'none'}")
    app.stop()


# Hooks

original_show_item = app.show_item


def show_item(item):
    original_show_item(item)
    markup, cols, rows = item.extra or ("", 0, 0)
    state["arts"].append((item.title, bool(markup)))
    state["item"] = item.position
    log(f"[{item.position}/{item.total}] {item.title!r} by {item.artist!r} art {cols}x{rows}: {art_summary(markup)}")


original_draw_bar = app.draw_bar


def draw_bar(fraction):
    original_draw_bar(fraction)
    item = state["item"]
    if item and item not in state["shot"] and fraction > 0.3:
        state["shot"].add(item)
        app.root.export_to_png(str(SHOTS / f"player_{item:02d}.png"))


original_finished = app.show_finished


def show_finished(done, failed, folder, error=None):
    state["folder"] = folder
    log(f"finished: done={done} failed={failed} error={error}")
    original_finished(done, failed, folder, error)


app.show_item = show_item
app.draw_bar = draw_bar
app.show_finished = show_finished

Clock.schedule_once(type_link, 1)
Clock.schedule_once(wait_valid, 1.5)
app.run()
