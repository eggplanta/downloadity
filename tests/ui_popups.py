"""
Screenshots of every popup, no download
Usage: ui_popups.py [playlist url with invalid items]
Saves to tests/output/shots
"""
import sys
from types import SimpleNamespace

import paths

from kivy.clock import Clock
from kivy.core.window import Window

import main
from main import t

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/playlist?list=PLUKxr8xaGTvSSsBXaMSXFbSeJJxEa-fas"
SHOTS = paths.OUTPUT / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

# English, and the real settings untouched
main.DownloadityApp.load_settings = lambda self: {"language": "en"}
main.DownloadityApp.save_settings = lambda self, **values: None
app = main.DownloadityApp()


def fake_start(*args, **kwargs):
    # Player parts the finish popup needs
    app.kind = "audio"
    app.total_items = len(app.media.entries)
    app.started_at = app.ended_at = 0
    app.bar_cols = 20
    app.queue = SimpleNamespace(last_path=None)
    app.swap_player(app.build_music_column())
    app.show_item_placeholder()
    Clock.schedule_once(fake_finish, 0.5)


app.start_download = fake_start


def popup():
    return next(w for w in Window.children if isinstance(w, main.AsciiPopup))


def shoot(name):
    popup().export_to_png(str(SHOTS / f"{name}.png"))
    print(f"saved {name}.png", flush=True)


def press(label):
    for b in popup().walk():
        if isinstance(b, main.AsciiButton) and label in b.text_label.text:
            b.dispatch("on_release")
            return


def then(callback):
    Clock.schedule_once(callback, 0.5)


def type_link(dt):
    app.link_input.text = URL


def wait_valid(dt):
    if not getattr(app, "media", None):
        return Clock.schedule_once(wait_valid, 0.3)

    print(f"invalid: {[e.title for e in app.media.invalid]}", flush=True)
    app.on_quality_select("audio", app.media.options.audio[-1])
    then(confirm)


def confirm(dt):
    shoot("popup_confirm")
    press(t("confirm"))
    then(invalid)


def invalid(dt):
    if app.media.invalid:
        shoot("popup_invalid")
        press(t("ok"))


def fake_finish(dt):
    app.timer_event = Clock.schedule_interval(lambda dt: None, 1)
    app.show_finished(1, ["Bohemian Rhapsody", "unknown title"], main.DOWNLOAD_ROOT)
    then(finished)


def finished(dt):
    shoot("popup_finished")
    press(t("ok"))
    then(failed)


def failed(dt):
    shoot("popup_failed")
    press(t("ok"))
    app.stop()


Clock.schedule_once(type_link, 1)
Clock.schedule_once(wait_valid, 1.5)
app.run()
