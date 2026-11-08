import json
import locale
import logging
import math
import os
import re
import threading
import time
import webbrowser

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp
from kivy.uix.textinput import TextInput
from kivy.core.text import Label as CoreLabel, LabelBase
from kivy.clock import Clock
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.modalview import ModalView
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.utils import escape_markup, platform

from downloadity import downloader, library, updates
from downloadity.download_queue import DownloadQueue, display_names
from downloadity.media import CheckError, resolve_media, subset
from downloadity.throttle import YoutubeBlockedError
from ascii_art import RAMP, cover_markup
import i18n
from i18n import t

Window.clearcolor = (0, 0, 0, 1)
# Focused field stays above keyboard
Window.softinput_mode = "below_target"

# Bundled, Android has no DejaVu
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
LabelBase.register(
    "DejaVuSansMono",
    os.path.join(FONTS_DIR, "DejaVuSansMono.ttf"),
    fn_bold=os.path.join(FONTS_DIR, "DejaVuSansMono-Bold.ttf"),
)
# Only the app texts' Chinese glyphs
LabelBase.register("NotoSansMonoCJK", os.path.join(FONTS_DIR, "NotoSansMonoCJKtc-subset.ttf"))
CJK_CHARS = {c for text in i18n.all_texts() for c in text if ord(c) >= 0x2E80}

# Kivy logs third-party debug otherwise
logging.getLogger().setLevel(logging.WARNING)

def spec_version():
    # Desktop runs read the build spec
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "buildozer.spec")
    try:
        with open(path) as f:
            return re.search(r"^version\s*=\s*(\S+)", f.read(), re.M).group(1)
    except (OSError, AttributeError):
        return "dev"


APP_VERSION = spec_version()
APK_TYPE = "application/vnd.android.package-archive"
UPDATE_NAME = "downloadity-update.apk"
REPO_URL = "https://github.com/eggplanta/downloadity"
# Ko-fi link pending
DONATE_URL = None

LINE_FONT = dp(12)
POPUP_SIDE = dp(40)
CHECKING_DOTS = (" ..", ". .", ".. ", "...")

ART_FONT = dp(7)
ART_COLS = 72
# User's phone sets the proportions
REFERENCE_WIDTH = dp(427)
ART_SHARE = 0.72
PLAYER_PADDING = dp(20)
GRAY = (0.5, 0.5, 0.5, 1)
CONTROLS = "⇄    ▮◀    ❚❚    ▶▮    ↻"
VIDEO_CONTROLS = "▮◀   ❚❚   ▶▮"
VIDEO_ASPECT = 16 / 9
VIDEO_ASPECTS = (0.5, 2.4)
BACK_KEY = 27
# Background time before starting over
RESTART_AFTER = 10 * 60
SERVICE_ID = 1
PROGRESS_CHANNEL = "downloads"

if platform == "android":
    from jnius import autoclass, cast

    DOWNLOAD_ROOT = "/storage/emulated/0/Download/downloadity"

    # Bundled ffmpeg ships as native lib
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    lib_dir = activity.getApplicationInfo().nativeLibraryDir
    downloader.FFMPEG = os.path.join(lib_dir, "libffmpeg.so")
    # Internal storage, avoids media scans
    downloader.TEMP_DIR = os.path.join(activity.getCacheDir().getAbsolutePath(), "work")

    from android.runnable import run_on_ui_thread

    APP_VERSION = activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0).versionName
    SDK = autoclass("android.os.Build$VERSION").SDK_INT

    def save_update(url, on_progress, sha256=None):
        """
        Public downloads, the installer reads it
        """
        ContentValues = autoclass("android.content.ContentValues")
        Integer = autoclass("java.lang.Integer")
        downloads = autoclass("android.provider.MediaStore$Downloads").EXTERNAL_CONTENT_URI
        resolver = activity.getContentResolver()

        values = ContentValues()
        values.put("_display_name", UPDATE_NAME)
        values.put("mime_type", APK_TYPE)
        values.put("is_pending", Integer(1))
        uri = resolver.insert(downloads, values)
        try:
            descriptor = resolver.openFileDescriptor(uri, "w")
            with os.fdopen(descriptor.detachFd(), "wb") as f:
                updates.download(url, f, on_progress, sha256)
        except Exception:
            resolver.delete(uri, None, None)
            raise

        values = ContentValues()
        values.put("is_pending", Integer(0))
        resolver.update(uri, values, None, None)
        return uri

    def remove_update():
        """
        Installed, declined or interrupted
        Interrupted ones stay pending, hidden by default
        """
        MediaStore = autoclass("android.provider.MediaStore")
        downloads = autoclass("android.provider.MediaStore$Downloads").EXTERNAL_CONTENT_URI
        resolver = activity.getContentResolver()
        if SDK >= 30:
            ContentResolver = autoclass("android.content.ContentResolver")
            args = autoclass("android.os.Bundle")()
            args.putString(ContentResolver.QUERY_ARG_SQL_SELECTION, "_display_name LIKE ?")
            args.putStringArray(ContentResolver.QUERY_ARG_SQL_SELECTION_ARGS, ["downloadity-update%"])
            args.putInt(MediaStore.QUERY_ARG_MATCH_PENDING, MediaStore.MATCH_INCLUDE)
            resolver.delete(downloads, args)
        else:
            downloads = MediaStore.setIncludePending(downloads)
            resolver.delete(downloads, "_display_name LIKE ?", ["downloadity-update%"])

    def install_apk(uri):
        Intent = autoclass("android.content.Intent")
        # Only installers handle it, no chooser
        intent = Intent(Intent.ACTION_INSTALL_PACKAGE)
        intent.setDataAndType(uri, APK_TYPE)
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK)
        activity.startActivity(intent)

    def can_install():
        # "Allow from this source" toggle
        return activity.getPackageManager().canRequestPackageInstalls()

    def open_install_settings():
        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")
        package = Uri.parse("package:" + activity.getPackageName())
        activity.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, package))

    def open_url(url):
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        activity.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))

    def system_locale():
        return autoclass("java.util.Locale").getDefault().toLanguageTag()

    @run_on_ui_thread
    def clear_system_bars():
        # No scrim, light icons on black
        window = activity.getWindow()
        sdk = autoclass("android.os.Build$VERSION").SDK_INT
        if sdk >= 29:
            window.setNavigationBarContrastEnforced(False)
            window.setStatusBarContrastEnforced(False)
        window.setNavigationBarColor(autoclass("android.graphics.Color").BLACK)
        window.setStatusBarColor(autoclass("android.graphics.Color").BLACK)
        if sdk >= 30:
            light = autoclass("android.view.WindowInsetsController")
            flags = light.APPEARANCE_LIGHT_NAVIGATION_BARS | light.APPEARANCE_LIGHT_STATUS_BARS
            window.getInsetsController().setSystemBarsAppearance(0, flags)
    service = autoclass("io.github.eggplanta.downloadity.ServiceKeepalive")
    power = activity.getSystemService(autoclass("android.content.Context").POWER_SERVICE)
    wake_lock = power.newWakeLock(autoclass("android.os.PowerManager").PARTIAL_WAKE_LOCK, "downloadity:download")

    def keep_alive(on, label=""):
        # Network and CPU survive minimizing
        if on:
            service.start(activity, "", label, "", "")
            if not wake_lock.isHeld():
                wake_lock.acquire()
        else:
            service.stop(activity)
            if wake_lock.isHeld():
                wake_lock.release()

    def ask_notifications():
        from android.permissions import Permission, request_permissions
        request_permissions([Permission.POST_NOTIFICATIONS])

    def show_progress(position, total, label):
        # Same id replaces the service notification
        Context = autoclass("android.content.Context")
        Notification = autoclass("android.app.Notification$Builder")
        Channel = autoclass("android.app.NotificationChannel")
        manager = activity.getSystemService(Context.NOTIFICATION_SERVICE)
        importance = autoclass("android.app.NotificationManager").IMPORTANCE_LOW
        manager.createNotificationChannel(Channel(PROGRESS_CHANNEL, t("downloads_channel"), importance))

        Intent = autoclass("android.content.Intent")
        PendingIntent = autoclass("android.app.PendingIntent")
        flags = PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT
        opening = PendingIntent.getActivity(activity, 0, Intent(activity, activity.getClass()), flags)

        text = autoclass("java.lang.String")(f"{position} / {total}")
        builder = Notification(activity, PROGRESS_CHANNEL)
        builder.setContentTitle(cast("java.lang.CharSequence", autoclass("java.lang.String")(label)))
        builder.setContentText(cast("java.lang.CharSequence", text))
        builder.setSmallIcon(activity.getApplicationInfo().icon)
        builder.setContentIntent(opening)
        builder.setOngoing(True)
        builder.setOnlyAlertOnce(True)
        builder.setProgress(total, position, False)
        manager.notify(SERVICE_ID, builder.build())

    def scan_file(path):
        # New files stay hidden until scanned
        scanner = autoclass("android.media.MediaScannerConnection")
        scanner.scanFile(activity, [path], None, None)

    def share_file(path):
        # The media store grants shareable links
        videos = autoclass("android.provider.MediaStore$Video$Media").EXTERNAL_CONTENT_URI
        cursor = activity.getContentResolver().query(videos, ["_id"], "_data=?", [path], None)
        found = cursor is not None and cursor.moveToFirst()
        media_id = cursor.getLong(0) if found else None
        if cursor is not None:
            cursor.close()
        if media_id is None:
            return False

        Intent = autoclass("android.content.Intent")
        uri = autoclass("android.content.ContentUris").withAppendedId(videos, media_id)
        intent = Intent(Intent.ACTION_SEND)
        intent.setType("video/mp4")
        intent.putExtra(Intent.EXTRA_STREAM, cast("android.os.Parcelable", uri))
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        activity.startActivity(Intent.createChooser(intent, cast("java.lang.CharSequence", autoclass("java.lang.String")("share video"))))
        return True
else:
    DOWNLOAD_ROOT = os.path.expanduser("~/Downloads/downloadity")

    def keep_alive(on, label=""):
        pass

    def ask_notifications():
        pass

    def show_progress(position, total, label):
        pass

    def scan_file(path):
        pass

    def share_file(path):
        return False

    def can_install():
        return True

    def open_install_settings():
        pass

    def open_url(url):
        webbrowser.open(url)

    def system_locale():
        return locale.getlocale()[0] or os.environ.get("LANG", "")

LOGO = f"""
▗▄▖             ▝▜            ▐  ▝   ▗      
▐ ▝▖ ▄▖ ▖  ▖▗▗▖  ▐   ▄▖  ▄▖  ▄▟ ▗▄  ▗▟▄ ▗ ▗ 
▐  ▌▐▘▜ ▚▗▗▘▐▘▐  ▐  ▐▘▜ ▝ ▐ ▐▘▜  ▐   ▐  ▝▖▞ 
▐  ▌▐ ▐ ▐▟▟ ▐ ▐  ▐  ▐ ▐ ▗▀▜ ▐ ▐  ▐   ▐   ▙▌ 
▐▄▞ ▝▙▛  ▌▌ ▐ ▐  ▝▄ ▝▙▛ ▝▄▜ ▝▙█ ▗▟▄  ▝▄  ▜  
                                         ▞  
                            v {APP_VERSION}  ▝▘
"""

def char_width(char, font_size, count=50):
    # Width per char inside a run
    label = CoreLabel(
        text=char * count,
        font_name="DejaVuSansMono",
        font_size=font_size,
    )
    label.refresh()
    return label.texture.size[0] / count

def text_width(text, font_size):
    font = "NotoSansMonoCJK" if not CJK_CHARS.isdisjoint(text) else "DejaVuSansMono"
    label = CoreLabel(text=text, font_name=font, font_size=font_size)
    label.refresh()
    return label.texture.size[0]


def uniform_font(font_size):
    # A grid needs equal glyph widths
    size = math.ceil(font_size)
    for candidate in range(size, size + 6):
        if len({char_width(char, candidate) for char in RAMP}) == 1:
            return candidate
    return font_size


def art_font(max_width):
    # Largest grid font that fits
    for size in range(math.ceil(ART_FONT), 3, -1):
        widths = {char_width(char, size) for char in RAMP}
        if len(widths) == 1 and ART_COLS * widths.pop() <= max_width:
            return size
    return uniform_font(ART_FONT)


def line_height(font_size):
    label = CoreLabel(
        text="Mg",
        font_name="DejaVuSansMono",
        font_size=font_size,
    )
    label.refresh()
    return label.texture.size[1]

def bar_markup(fraction, cols):
    played = int(fraction * (cols - 1))
    rest = cols - 1 - played
    return (
        f"[color=#ffffff]{'━' * played}●[/color]"
        f"[color=#555555]{'─' * rest}[/color]"
    )

def download_label(media):
    # Playlist name, else the song
    name = media.title and re.sub(r" \[[^\]]+\]$", "", media.title)
    if not name and media.entries:
        name = display_names(media.entries[0])[0]
    return t("downloading_name", name=name) if name else t("downloading")

def mono_label(text, font_size, **kwargs):
    kwargs.setdefault("halign", "center")
    kwargs.setdefault("valign", "middle")
    kwargs.setdefault("color", (1, 1, 1, 1))
    return TextLabel(
        text=text,
        font_name="DejaVuSansMono",
        font_size=font_size,
        **kwargs,
    )


class TextLabel(Label):
    # Chinese text switches font
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.on_text(self, self.text)

    def on_text(self, _instance, text):
        cjk = not CJK_CHARS.isdisjoint(text)
        self.font_name = "NotoSansMonoCJK" if cjk else "DejaVuSansMono"

def line_gap():
    # Room for a drawn line
    return Widget(size_hint_x=None, width=char_width("│", LINE_FONT))

def parse_time(text):
    """
    min:sec or h:min:sec to seconds
    """
    parts = text.strip().split(":")
    if not 2 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
        return None

    values = [int(part) for part in parts]
    if values[-1] > 59 or (len(values) == 3 and values[1] > 59):
        return None
    hours, minutes, seconds = [0] * (3 - len(values)) + values
    return hours * 3600 + minutes * 60 + seconds

def wrap_path(path, width=26):
    # Breaks only after a slash
    lines = [""]
    for part in path.replace("/", "/\0").split("\0"):
        if lines[-1] and len(lines[-1]) + len(part) > width:
            lines.append("")
        lines[-1] += part
    return "\n".join(lines)

def format_time(seconds):
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"

class TimeInput(TextInput):
    """
    Digits fill from the right
    Colons stay fixed
    """

    def __init__(self, long=False, **kwargs):
        super().__init__(**kwargs)
        self.slots = 6 if long else 4
        self.digits = ""
        self.show_digits()

    def insert_text(self, substring, from_undo=False):
        typed = "".join(c for c in substring if c.isdigit())
        self.digits = (self.digits + typed)[:self.slots]
        self.show_digits()

    def do_backspace(self, from_undo=False, mode="bkspc"):
        self.digits = self.digits[:-1]
        self.show_digits()

    def show_digits(self):
        padded = self.digits.rjust(self.slots, "0")
        self.text = ":".join(padded[i:i + 2] for i in range(0, self.slots, 2))
        self.foreground_color = (1, 1, 1, 1) if self.digits else GRAY
        self.cursor = (len(self.text), 0)

def quality_column():
    column = BoxLayout(
        orientation="vertical",
        size_hint_y=None,
        padding=[0, dp(30), 0, dp(12)],
        spacing=dp(30),
    )
    column.bind(minimum_height=column.setter("height"))

    # Bar shows only while scrolling
    scroll = ScrollView(do_scroll_x=False, bar_inactive_color=(0, 0, 0, 0))
    scroll.add_widget(column)
    return scroll, column

class AsciiButton(Button):
    BORDER_FONT = dp(12)

    def __init__(self, label, font_size=dp(15), border=True, rows=None, **kwargs):
        super().__init__(**kwargs)
        self.show_border = border
        self.rows = rows
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.text = ""

        if self.rows:
            self.height = self.rows * line_height(self.BORDER_FONT) * 1.3

        self.border_label = Label(
            font_name="DejaVuSansMono",
            font_size=self.BORDER_FONT,
            halign="center",
            valign="middle",
        )
        self.border_label.bind(size=self.border_label.setter("text_size"))

        self.text_label = TextLabel(
            text=label,
            font_name="DejaVuSansMono",
            font_size=font_size,
            halign="center",
            valign="middle",
            markup=True,
        )

        # Disabled buttons turn gray
        self.border_label.disabled_color = GRAY
        self.text_label.disabled_color = GRAY

        self.add_widget(self.border_label)
        self.add_widget(self.text_label)

        self.bind(
            pos=self.update_layout,
            size=self.update_layout,
            state=self.update_color,
        )
        self.update_layout()

    def update_layout(self, *args):
        self.border_label.pos = self.pos
        self.border_label.size = self.size
        self.text_label.pos = self.pos
        self.text_label.size = self.size

        if not self.show_border:
            self.border_label.text = ""
            return

        cw = char_width("─", self.BORDER_FONT)
        line_h = line_height(self.BORDER_FONT)
        cols = max(4, int(self.width / cw))
        rows = self.rows or max(3, int(self.height / line_h))
        inner = cols - 2

        lines = ["┌" + "─" * inner + "┐"]
        lines += ["│" + " " * inner + "│"] * (rows - 2)
        lines += ["└" + "─" * inner + "┘"]
        self.border_label.text = "\n".join(lines)

    def update_color(self, *args):
        c = (0.6, 0.6, 0.6, 1) if self.state == "down" else (1, 1, 1, 1)
        self.border_label.color = c
        self.text_label.color = c

class AsciiPopup(ModalView):
    def __init__(self, message, buttons, items=None, body=None, height=None, width=dp(320), closable=True, **kwargs):
        self.closable = closable
        super().__init__(
            size_hint=(None, None),
            size=(min(width, Window.width - dp(24)), height or (dp(420) if items else dp(230))),
            auto_dismiss=False,
            background="",
            background_color=(0, 0, 0, 1),
            overlay_color=(0, 0, 0, 0.75),
            **kwargs,
        )

        layout = FloatLayout()

        self.frame = mono_label("", LINE_FONT, pos_hint={"x": 0, "y": 0})
        self.frame.bind(size=self.redraw_frame)
        layout.add_widget(self.frame)

        content = BoxLayout(
            orientation="vertical",
            padding=[POPUP_SIDE, dp(28), POPUP_SIDE, dp(18) if buttons else dp(28)],
            spacing=dp(8),
            pos_hint={"x": 0, "y": 0},
        )

        # Body alone when no message
        if message is not None:
            text = mono_label(message, dp(15), markup=True)
            self.message = text
            if items:
                # Grows with longer translations
                text.size_hint_y = None
                text.bind(
                    width=lambda label, width: setattr(label, "text_size", (width, None)),
                    texture_size=lambda label, size: setattr(label, "height", max(dp(40), size[1])),
                )
            else:
                text.bind(size=text.setter("text_size"))
            content.add_widget(text)

        if items:
            content.add_widget(self.item_list(items))
        if body:
            content.add_widget(body)

        self.buttons = []
        if buttons:
            row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(16))
            for label, callback in buttons:
                button = AsciiButton(escape_markup(f"[ {label} ]"), border=False, font_size=dp(15))
                button.bind(on_release=lambda _b, cb=callback: self.choose(cb))
                row.add_widget(button)
                self.buttons.append(button)
            content.add_widget(row)

        layout.add_widget(content)
        self.add_widget(layout)

    def item_list(self, items):
        scroll = ScrollView(bar_width=dp(2), bar_color=GRAY, bar_inactive_color=GRAY)
        label = mono_label(
            escape_markup("\n".join(f"- {item}" for item in items)),
            dp(12),
            size_hint_y=None,
            color=GRAY,
            markup=True,
            halign="left",
        )
        label.bind(
            width=lambda l, w: setattr(l, "text_size", (w, None)),
            texture_size=lambda l, s: setattr(l, "height", s[1]),
        )
        scroll.add_widget(label)
        return scroll

    def choose(self, callback):
        # Hides the Android keyboard
        for widget in self.walk():
            if isinstance(widget, TextInput):
                widget.focus = False
        self.dismiss()
        callback()

    def redraw_frame(self, label, size):
        cols = int(size[0] / char_width("─", LINE_FONT))
        rows = int(size[1] / line_height(LINE_FONT))
        inner = max(0, cols - 2)

        lines = ["┌" + "─" * inner + "┐"]
        lines += ["│" + " " * inner + "│"] * max(0, rows - 2)
        lines += ["└" + "─" * inner + "┘"]
        label.text = "\n".join(lines)

class DownloadityApp(App):
    pending_apk = None
    paused_at = None
    updating = False

    def on_text_change(self, instance, value):
        if hasattr(self, "check_event"):
            self.check_event.cancel()

        if not value.strip():
            for widget in (
                self.pipe_left,
                self.pipe_right,
                self.top_border,
                self.bottom_border,
            ):
                widget.color = (1, 1, 1, 1)

            self.show_in_result_area(None)
            return

        self.start_checking()
        self.check_event = Clock.schedule_once(
            lambda dt: threading.Thread(
                target=self.check_link,
                args=(value.strip(),),
                daemon=True,
            ).start(),
            0.3,
        )

    def check_link(self, url):
        media, error = None, None
        try:
            media = resolve_media(url)
        except YoutubeBlockedError:
            error = t("blocked")
        except CheckError as e:
            error = i18n.error(str(e))
        except Exception as e:
            import traceback; traceback.print_exc()
            updates.report(e)
            error = f"{t('unexpected_error')}\n{type(e).__name__}: {str(e)[:80]}"

        Clock.schedule_once(
            lambda dt: self.show_result(url, media, error)
        )

    def show_result(self, url, media, error=None):
        if url != self.link_input.text.strip():
            return

        self.media = self.checked_media = media
        valid = media is not None
        color = (0, 1, 0, 1) if valid else (1, 0, 0, 1)

        for widget in (
            self.pipe_left,
            self.pipe_right,
            self.top_border,
            self.bottom_border,
        ):
            widget.color = color

        # Keyboard would hide the button
        if valid:
            self.link_input.focus = False
        if error:
            # Wraps long reasons to the screen
            self.error_label.text_size = (Window.width - dp(60), None)
            self.error_label.text = error
            self.error_label.texture_update()
            self.error_label.height = self.error_label.texture_size[1] + dp(8)
            self.show_in_result_area(self.error_label)
        else:
            self.show_in_result_area(self.download_button if valid else None)

    def start_checking(self):
        if self.checking_event:
            return

        self.checking_frame = 0
        self.checking_label.text = t("checking") + CHECKING_DOTS[0]
        self.show_in_result_area(self.checking_label)
        self.checking_event = Clock.schedule_interval(self.animate_checking, 0.3)

    def animate_checking(self, dt):
        self.checking_frame = (self.checking_frame + 1) % len(CHECKING_DOTS)
        self.checking_label.text = t("checking") + CHECKING_DOTS[self.checking_frame]

    def show_in_result_area(self, widget):
        if widget is not self.checking_label and self.checking_event:
            self.checking_event.cancel()
            self.checking_event = None

        self.buttons.clear_widgets()

        if widget is None:
            self.buttons.height = 0
            self.buttons.opacity = 0
            return

        self.buttons.add_widget(widget)
        self.buttons.height = widget.height
        self.buttons.opacity = 1

    def on_download_press(self, *args):
        self.media = self.checked_media
        self.overwrite = False

        # Known playlists offer only the new items
        folder = self.media.is_playlist and library.find_folder(DOWNLOAD_ROOT, self.media.playlist_id)
        if folder:
            self.ask_repeat(folder)
        else:
            self.show_qualities()

    def ask_repeat(self, folder):
        kind = library.previous_kind(folder)
        new = library.new_entries(folder, kind, self.media.entries)
        count = t("new_items", n=len(new)) if new else t("no_new_items")

        popup = AsciiPopup(
            t("downloaded_before", count=count),
            [
                (t("all"), self.repeat_all),
                (t("new"), lambda: self.repeat_new(new)),
            ],
        )
        popup.buttons[1].disabled = not new
        popup.open()

    def repeat_all(self):
        self.overwrite = True
        self.show_qualities()

    def repeat_new(self, entries):
        self.media = subset(self.media, entries)
        self.show_qualities()

    def show_qualities(self):
        options = self.media.options
        self.link_input.focus = False

        has_options = options.audio or options.video
        self.qualities_status.text = "" if has_options else t("no_options")
        scale = self.quality_scale(options.audio + options.video)
        self.fill_quality_column(self.audio_column, "audio", options.audio, scale)
        self.fill_quality_column(self.video_column, "video", options.video, scale)

        self.screens.current = "qualities"

    def quality_scale(self, qualities):
        # Long labels shrink to fit
        table = (Window.width - dp(40)) * 0.9
        column = (table - char_width("│", LINE_FONT)) / 2 - dp(8)
        widest = max((text_width(f"[ {q.label} ]", dp(17)) for q in qualities), default=0)
        return min(1, column / widest) if widest else 1

    def fill_quality_column(self, column, kind, qualities, scale=1):
        column.clear_widgets()

        for quality in sorted(qualities, key=lambda q: q.value, reverse=True):
            text = escape_markup(f"[ {quality.label} ]")
            if quality.filesize_label:
                text += f"\n[size={int(dp(13) * scale)}]({quality.filesize_label})[/size]"

            button = AsciiButton(
                text,
                border=False,
                size_hint_y=None,
                height=dp(52),
                font_size=dp(17) * scale,
            )
            button.bind(
                on_release=lambda _b, q=quality: self.on_quality_select(kind, q)
            )
            column.add_widget(button)

    def on_quality_select(self, kind, quality):
        size = quality.filesize_label
        usage = ""
        if size:
            usage = f"~{size}" if self.media.is_playlist else size
            usage = "\n\n" + t("storage_use", size=usage)

        # Single videos can be cut
        if kind == "video" and not self.media.is_playlist:
            AsciiPopup(
                t("full_or_cut") + usage,
                [
                    (t("cut_video"), lambda: self.ask_cut(quality)),
                    (t("full_video"), lambda: self.start_download(kind, quality)),
                ],
            ).open()
            return

        message = t("download_in", quality=quality.label.replace(" ", "\u00a0")) + usage
        AsciiPopup(
            message,
            [
                (t("cancel"), lambda: None),
                (t("confirm"), lambda: self.confirm_invalid(kind, quality)),
            ],
        ).open()

    def ask_cut(self, quality):
        duration = self.media.entries[0].duration
        box = BoxLayout(orientation="vertical", spacing=dp(10))
        fields = []

        for name in ("start", "end"):
            row = BoxLayout(size_hint_y=None, height=dp(32))
            label = mono_label(t(name), dp(15), halign="left", size_hint_x=None, width=dp(60))
            label.bind(size=label.setter("text_size"))
            row.add_widget(label)
            row.add_widget(mono_label("[", dp(15), size_hint_x=None, width=dp(12)))

            field = TimeInput(
                long=bool(duration and duration >= 3600),
                multiline=False,
                input_type="number",
                halign="center",
                background_color=(0, 0, 0, 1),
                cursor_color=(1, 1, 1, 1),
                padding=[dp(6), dp(6)],
                font_name="DejaVuSansMono",
                font_size=dp(15),
                write_tab=False,
            )
            row.add_widget(field)
            row.add_widget(mono_label("]", dp(15), size_hint_x=None, width=dp(12)))
            box.add_widget(row)
            fields.append(field)

        if duration:
            box.add_widget(mono_label(t("video_length", time=format_time(duration)), dp(12), color=GRAY))

        def cut_range():
            start, end = (parse_time(field.text) for field in fields)
            if start is None or end is None or end - start < 1:
                return None
            if duration and end > duration:
                return None
            return start, end

        popup = AsciiPopup(
            t("cut_the_video"),
            [
                (t("cancel"), lambda: None),
                (t("download"), lambda: self.start_download("video", quality, cut_range())),
            ],
            body=box,
            height=dp(300),
        )
        download_button = popup.buttons[1]
        download_button.disabled = True

        def validate(*_args):
            download_button.disabled = cut_range() is None

        for field in fields:
            field.bind(text=validate)
        popup.open()

    def confirm_invalid(self, kind, quality):
        if not self.media.invalid:
            self.start_download(kind, quality)
            return

        AsciiPopup(
            t("invalid_items"),
            [(t("ok"), lambda: self.start_download(kind, quality))],
            items=[e.title or t("unknown_title") for e in self.media.invalid],
        ).open()

    #====================DOWNLOAD======================#

    def start_download(self, kind, quality, cut=None):
        self.download_label = download_label(self.media)
        keep_alive(True, self.download_label)
        self.kind = kind
        self.total_items = len(self.media.entries)
        self.swap_player(self.build_video_column() if kind == "video" else self.build_music_column())
        self.show_item_placeholder()
        self.screens.current = "downloading"

        # Clock pauses while minimized
        self.started_at = time.monotonic()
        self.ended_at = None
        self.timer_label.text = "00:00"
        self.timer_event = Clock.schedule_interval(self.tick_timer, 1)

        queue = self.queue = DownloadQueue(
            self.media,
            kind,
            quality.value,
            DOWNLOAD_ROOT,
            listener=self,
            prepare_extra=self.make_art,
            cut=cut,
            overwrite=self.overwrite,
            on_saved=scan_file,
        )
        threading.Thread(target=self.run_queue, args=(queue,), daemon=True).start()

    def run_queue(self, queue):
        try:
            queue.run()
        except Exception as e:
            updates.report(e)
            error = str(e)
            Clock.schedule_once(lambda dt: self.show_finished(0, [], queue.output_dir, error))
        finally:
            # UI thread sleeps while minimized
            self.ended_at = time.monotonic()
            keep_alive(False)

    def make_art(self, entry):
        info = entry.info["ytdlp_info"]
        cols, rows = self.art_dims(info)
        aspect = cols * self.art_cw / (rows * self.art_lh)
        return cover_markup(info, cols, rows, aspect, entry.cover), cols, rows

    def art_dims(self, info):
        if self.kind != "video":
            return self.art_cols, self.art_rows

        # Playlists keep a fixed 16:9 frame
        width, height = (info or {}).get("width"), (info or {}).get("height")
        aspect = VIDEO_ASPECT
        if width and height and not self.media.is_playlist:
            aspect = min(VIDEO_ASPECTS[1], max(VIDEO_ASPECTS[0], width / height))
        area = self.art_cols * self.art_cw * self.art_rows * self.art_lh
        cols = round(math.sqrt(area * aspect) / self.art_cw)
        rows = round(math.sqrt(area / aspect) / self.art_lh)

        # Wide frames shrink to the screen
        if cols > self.max_cols:
            rows = max(1, round(rows * self.max_cols / cols))
            cols = self.max_cols
        return cols, rows

    # Queue listener (worker thread)

    def on_item_start(self, item):
        Clock.schedule_once(lambda dt: self.show_item(item))
        # Clock sleeps while minimized
        if self.media.is_playlist:
            show_progress(item.position, item.total, self.download_label)

    def on_progress(self, fraction):
        Clock.schedule_once(lambda dt: self.draw_bar(fraction))

    def on_finished(self, done, failed, folder):
        Clock.schedule_once(lambda dt: self.show_finished(done, failed, folder))

    # Player screen

    def show_item_placeholder(self):
        info = self.media.entries[0].info
        self.set_art("", *self.art_dims(info and info["ytdlp_info"]))
        self.song_label.text = ""
        self.artist_label.text = ""
        self.counter_label.text = f"1 / {self.total_items}"
        self.draw_bar(0)

    def show_item(self, item):
        markup, cols, rows = item.extra or ("", *self.art_dims(None))
        self.set_art(markup, cols, rows)
        self.song_label.text = escape_markup(item.title)
        self.artist_label.text = escape_markup(item.artist)
        self.counter_label.text = f"{item.position} / {item.total}"
        self.draw_bar(0)

    def set_art(self, markup, cols, rows):
        width = cols * self.art_cw
        self.player_column.width = width
        self.art_label.height = rows * self.art_lh
        self.art_label.text = markup or "[color=#333333]" + "\n".join(["·" * cols] * rows) + "[/color]"
        self.bar_cols = int(width / char_width("━", LINE_FONT * self.scale))

    def draw_bar(self, fraction):
        self.bar_label.text = bar_markup(fraction, self.bar_cols)

    def tick_timer(self, dt):
        elapsed = int((self.ended_at or time.monotonic()) - self.started_at)
        minutes, seconds = divmod(elapsed, 60)
        self.timer_label.text = f"{minutes:02d}:{seconds:02d}"

    def show_finished(self, done, failed, folder, error=None):
        self.timer_event.cancel()
        self.tick_timer(0)
        self.draw_bar(1)

        if error:
            message = t("download_failed", error=i18n.error(error))
        else:
            # Short path, no mid-word wrap
            shown = wrap_path(folder.replace("/storage/emulated/0/", ""))
            message = t("download_finished", path=shown)

        after = lambda: self.show_failed(failed) if failed else self.reset_home()
        buttons = [(t("ok"), after)]

        # Single videos can go straight out
        path = self.queue.last_path
        if self.kind == "video" and not self.media.is_playlist and path and not error:
            buttons.insert(0, (t("share"), lambda: self.share(path)))
        AsciiPopup(escape_markup(message), buttons, closable=False).open()

    def share(self, path):
        if share_file(path):
            self.reset_home()
        else:
            AsciiPopup(t("share_failed"), [(t("ok"), self.reset_home)], closable=False).open()

    def show_failed(self, failed):
        AsciiPopup(
            t("items_failed", n=len(failed)),
            [(t("ok"), self.reset_home)],
            items=failed,
            closable=False,
        ).open()

    def reset_home(self):
        self.media = self.checked_media = None
        self.link_input.text = ""
        self.screens.current = "home"


    #=====================SETTINGS=====================#

    def show_settings(self, *_args):
        popup_width = min(dp(340), Window.width - dp(24))
        inner = popup_width - 2 * POPUP_SIDE
        # Top pad offsets the title's spacing
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=[0, dp(7.5), 0, 0])
        # Equal gaps center the language row
        box.add_widget(Widget())

        # Label and choice kept together
        language = t("language")
        choice = escape_markup(f"[ {self.language_name(self.language_choice)} ]")
        font = dp(15)
        total = text_width(language, font) + dp(16) + text_width(choice, font)
        # Long names shrink a little
        if total > inner:
            font *= inner / total
        label_width, choice_width = text_width(language, font), text_width(choice, font)
        row = BoxLayout(
            size_hint=(None, None),
            size=(label_width + dp(16) + choice_width, dp(44)),
            spacing=dp(16),
            pos_hint={"center_x": 0.5},
        )
        row.add_widget(mono_label(language, font, size_hint_x=None, width=label_width))
        picker = AsciiButton(choice, border=False, font_size=font, size_hint_x=None, width=choice_width)
        row.add_widget(picker)
        box.add_widget(row)
        box.add_widget(Widget())

        links = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(16))
        # Donate appears once URL exists
        for text, url in ((t("donate"), DONATE_URL), ("github", REPO_URL)):
            if not url:
                continue
            button = AsciiButton(escape_markup(f"[ {text} ]"), border=False, font_size=dp(15))
            button.url = url
            links.add_widget(button)
        # Github sits close to version
        footer = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(66), spacing=dp(2))
        footer.add_widget(links)
        footer.add_widget(mono_label(f"v{APP_VERSION}", dp(12), color=GRAY, size_hint_y=None, height=dp(20)))
        box.add_widget(footer)

        popup = AsciiPopup(t("settings"), None, body=box, height=dp(270), width=popup_width)
        popup.message.size_hint_y = None
        popup.message.height = dp(30)
        picker.bind(on_release=lambda _b: (popup.dismiss(), self.show_languages()))
        # Closed so it isn't stale
        for button in links.children:
            button.bind(on_release=lambda b: (popup.dismiss(), open_url(b.url)))
        # Tap outside closes it
        popup.auto_dismiss = True
        popup.open()

    def show_languages(self):
        box = BoxLayout(orientation="vertical")
        for choice in ("auto", *i18n.LANGUAGES):
            name = self.language_name(choice)
            text = f"› {name} ‹" if choice == self.language_choice else name
            button = AsciiButton(escape_markup(text), border=False, font_size=dp(15))
            button.bind(on_release=lambda _b, c=choice: self.choose_language(c))
            box.add_widget(button)

        popup = AsciiPopup(t("language"), None, body=box, height=dp(340), width=dp(340))
        popup.message.size_hint_y = None
        popup.message.height = dp(30)
        popup.auto_dismiss = True
        popup.open()

    def choose_language(self, choice):
        for popup in [w for w in Window.children if isinstance(w, AsciiPopup)]:
            popup.dismiss()
        self.save_settings(language=choice)
        self.apply_language()
        self.rebuild()
        self.show_settings()

    # Each name in its own language
    def language_name(self, choice):
        if choice == "auto":
            return f"auto ({i18n.NAMES[i18n.system_language(system_locale())]})"
        return i18n.NAMES[choice]

    @property
    def language_choice(self):
        choice = self.load_settings().get("language")
        return choice if choice in i18n.LANGUAGES else "auto"

    def apply_language(self):
        choice = self.language_choice
        i18n.set_language(i18n.system_language(system_locale()) if choice == "auto" else choice)

    def settings_path(self):
        return os.path.join(self.user_data_dir, "settings.json")

    def load_settings(self):
        try:
            with open(self.settings_path()) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_settings(self, **values):
        settings = {**self.load_settings(), **values}
        with open(self.settings_path(), "w") as f:
            json.dump(settings, f)

    def rebuild(self):
        # Screens rebuilt in the new language
        if hasattr(self, "check_event"):
            self.check_event.cancel()
        self.show_in_result_area(None)
        self.media = self.checked_media = None
        self.frame.clear_widgets()
        self.screens = self.build_screens()
        self.frame.add_widget(self.screens)

    #======================BUILD=======================#

    def on_start(self):
        # Shows download progress when minimized
        ask_notifications()
        if platform == "android":
            updates.confirm()
            threading.Thread(target=self.check_updates, daemon=True).start()

    # Updates (worker thread)

    def check_updates(self):
        """
        A new APK comes with its libraries
        """
        # Cleanup never blocks the check
        try:
            remove_update()
        except Exception as e:
            print("update: cleanup failed:", e)

        try:
            apk = SDK >= 29 and updates.latest_apk(APP_VERSION)
        except Exception as e:
            print("update: release check failed:", e)
            apk = None

        if apk:
            Clock.schedule_once(lambda dt: self.offer_update(apk))
        else:
            updates.check_libs()

    def offer_update(self, apk):
        # Asked again on every launch
        AsciiPopup(
            t("new_version", version=apk["version"]),
            [(t("yes"), lambda: self.start_update(apk)), (t("no"), self.skip_update)],
            closable=False,
        ).open()

    def start_update(self, apk):
        # Without permission the download is wasted
        if can_install():
            self.update_app(apk)
        else:
            self.ask_install_permission(apk)

    def ask_install_permission(self, apk):
        AsciiPopup(
            t("allow_install"),
            [(t("open_settings"), lambda: self.open_settings(apk)), (t("later"), self.skip_update)],
            height=dp(260),
            closable=False,
        ).open()

    def open_settings(self, apk):
        self.pending_apk = apk
        open_install_settings()

    def on_pause(self):
        self.paused_at = time.time()
        return True

    def on_resume(self):
        # Back from the permission screen
        apk, self.pending_apk = self.pending_apk, None
        if apk:
            self.start_update(apk)
        elif self.stale():
            self.restart()

    def stale(self):
        # Wall clock counts deep sleep too
        away = time.time() - (self.paused_at or time.time())
        busy = self.updating or self.screens.current == "downloading"
        return away > RESTART_AFTER and not busy

    def restart(self):
        """
        Long pauses start over, checking updates
        """
        for popup in [w for w in Window.children if isinstance(w, AsciiPopup)]:
            popup.dismiss()
        self.reset_home()
        if platform == "android":
            threading.Thread(target=self.check_updates, daemon=True).start()

    def skip_update(self):
        threading.Thread(target=updates.check_libs, daemon=True).start()

    def update_app(self, apk):
        self.updating = True
        title = mono_label(t("downloading_version", version=apk["version"]), dp(15), size_hint_y=None, height=dp(24))
        bar = mono_label("", LINE_FONT, markup=True, size_hint_y=None, height=dp(20))
        percent = mono_label("0%", dp(13), color=GRAY, size_hint_y=None, height=dp(20))
        body = BoxLayout(orientation="vertical")
        for widget in (Label(), title, Label(size_hint_y=None, height=dp(14)), bar, percent, Label()):
            body.add_widget(widget)

        popup = AsciiPopup(None, [], body=body, closable=False)
        cols = int((popup.width - 2 * POPUP_SIDE) / char_width("━", LINE_FONT))
        bar.text = bar_markup(0, cols)
        popup.open()
        shown = [0]

        def show(fraction):
            bar.text = bar_markup(fraction, cols)
            percent.text = f"{int(fraction * 100)}%"

        def progress(fraction):
            value = int(fraction * 100)
            if value != shown[0]:
                shown[0] = value
                Clock.schedule_once(lambda dt: show(fraction))

        def failed():
            self.updating = False
            popup.dismiss()
            AsciiPopup(t("update_failed"), [(t("ok"), self.skip_update)], closable=False).open()

        def work():
            try:
                uri = save_update(apk["url"], progress, apk.get("sha256"))
            except Exception as e:
                print("update: apk download failed:", e)
                Clock.schedule_once(lambda dt: failed())
                return
            Clock.schedule_once(lambda dt: installed(uri))

        def installed(uri):
            self.updating = False
            popup.dismiss()
            install_apk(uri)

        threading.Thread(target=work, daemon=True).start()

    def on_back(self, window, key, *args):
        if key != BACK_KEY:
            return False

        popup = next((w for w in Window.children if isinstance(w, AsciiPopup)), None)
        if popup:
            if popup.closable:
                popup.choose(lambda: None)
            return True

        if self.screens.current == "qualities":
            self.screens.current = "home"
            return True
        return False

    def build(self):
        Window.bind(on_keyboard=self.on_back)
        self.apply_language()
        self.screens = self.build_screens()

        # Keeps clear of system bars
        self.frame = BoxLayout()
        self.frame.add_widget(self.screens)
        if platform == "android":
            clear_system_bars()
            Clock.schedule_once(self.fit_system_bars, 0.5)
        return self.frame

    def build_screens(self):
        screens = ScreenManager(transition=NoTransition())
        self.screens = screens

        home = Screen(name="home")
        home.add_widget(self.build_home())
        # Floats, home layout stays put
        settings = AsciiButton(
            "⚙",
            border=False,
            font_size=dp(48),
            size_hint=(None, None),
            size=(dp(64), dp(64)),
        )
        # Slightly off the corner
        home.bind(size=lambda screen, size: setattr(settings, "pos", (size[0] - dp(72), size[1] - dp(72))))
        settings.bind(on_release=self.show_settings)
        home.add_widget(settings)
        self.screens.add_widget(home)

        qualities = Screen(name="qualities")
        qualities.add_widget(self.build_qualities())
        self.screens.add_widget(qualities)

        downloading = Screen(name="downloading")
        downloading.add_widget(self.build_downloading())
        self.screens.add_widget(downloading)
        return screens

    def fit_system_bars(self, dt):
        insets = activity.getWindow().getDecorView().getRootWindowInsets()
        if insets is None:
            Clock.schedule_once(self.fit_system_bars, 0.5)
            return
        top = insets.getSystemWindowInsetTop()
        bottom = insets.getSystemWindowInsetBottom()
        self.frame.padding = [0, top, 0, bottom]

    def build_home(self):

        root = BoxLayout(
            orientation="vertical",
            padding=[dp(20), dp(20)],
            spacing=dp(20),
        )

        # top space
        root.add_widget(Label(size_hint_y=None, height=dp(120)))

        # logo, shrunk on narrow screens
        logo_cols = max(len(line) for line in LOGO.splitlines())
        logo_font = min(dp(12), dp(12) * (Window.width - dp(40)) / (logo_cols * char_width("▐", dp(12))))
        logo = Label(
            text=LOGO,
            color=(1, 1, 1, 1),
            font_name="DejaVuSansMono",
            font_size=logo_font,
            halign="center",
            valign="top",
            size_hint_y=None,
            height=dp(110) * logo_font / dp(12),
        )
        logo.text_size = (Window.width - dp(40), None)
        root.add_widget(logo)

        # space
        root.add_widget(Label(size_hint_y=None, height=dp(110)))

        # "paste the link:"
        link_label = TextLabel(
            text=t("paste_link"),
            color=(1, 1, 1, 1),
            halign="left",
            valign="middle",
            size_hint=(None, None),
            font_name="DejaVuSansMono",
            font_size=dp(15),
            height=dp(18),
            pos_hint={"center_x": 0.5},
        )
        link_label.bind(size=link_label.setter("text_size"))
        root.add_widget(link_label)

        # input box

        dash_width = char_width("─", dp(12))
        pipe_width = char_width("│", dp(12))

        link_frame = BoxLayout(
            orientation="vertical",
            size_hint=(None, None),
            height=dp(60),
            pos_hint={"center_x": 0.5},
        )

        input_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(28),
            pos_hint={"center_x": 0.5},
        )

        pipe_left = Label(
            text="│",
            color=(1, 1, 1, 1),
            font_name="DejaVuSansMono",
            font_size=dp(12),
            size_hint_x=None,
            width=pipe_width,
        )
        self.pipe_left = pipe_left

        self.link_input = TextInput(
            multiline=False,
            foreground_color=(1, 1, 1, 1),
            background_color=(0, 0, 0, 1),
            cursor_color=(1, 1, 1, 1),
            padding=[dp(12), dp(4)],
            font_name="DejaVuSansMono",
            font_size=dp(15),
        )

        pipe_right = Label(
            text="│",
            color=(1, 1, 1, 1),
            font_name="DejaVuSansMono",
            font_size=dp(12),
            size_hint_x=None,
            width=pipe_width,
        )
        self.pipe_right = pipe_right

        input_row.add_widget(pipe_left)
        input_row.add_widget(self.link_input)
        input_row.add_widget(pipe_right)

        top_border = Label(
            color=(1, 1, 1, 1),
            font_name="DejaVuSansMono",
            font_size=dp(12),
            size_hint=(1, None),
            height=dp(20),
            halign="center",
        )
        self.top_border = top_border

        bottom_border = Label(
            color=(1, 1, 1, 1),
            font_name="DejaVuSansMono",
            font_size=dp(12),
            size_hint=(1, None),
            height=dp(20),
            halign="center",
        )
        self.bottom_border = bottom_border

        def redraw_border(_instance, width):
            dash_count = max(1, int(width / dash_width) - 2)
            top_border.text = "┌" + "─" * dash_count + "┐"
            bottom_border.text = "└" + "─" * dash_count + "┘"

            top_border.texture_update()

            input_row.size_hint_x = None
            input_row.width = top_border.texture_size[0]

        link_frame.bind(width=redraw_border)

        link_frame.add_widget(top_border)
        link_frame.add_widget(input_row)
        link_frame.add_widget(bottom_border)

        root.add_widget(link_frame)

        def fit_link(_instance, width):
            # Box a bit past the label
            link_label.width = (width - dp(40)) * 0.6
            link_frame.width = link_label.width + dp(40)

        root.bind(width=fit_link)

        self.link_input.bind(text=self.on_text_change)

        # space
        root.add_widget(Label())

        self.buttons = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=0,
            opacity=0,
            pos_hint={"center_x": 0.5},
        )

        self.download_button = AsciiButton(
            t("download_button"),
            size_hint=(None, None),
            width=dp(210),
            pos_hint={"center_x": 0.5},
            font_size=dp(18),
            rows=5,
        )

        self.download_button.bind(on_release=self.on_download_press)

        self.checking_label = mono_label(
            "",
            dp(12),
            size_hint_y=None,
            height=dp(20),
        )
        self.checking_event = None

        self.error_label = mono_label(
            "",
            dp(12),
            color=(1, 0.3, 0.3, 1),
            size_hint_y=None,
        )


        root.add_widget(self.buttons)

        # space
        root.add_widget(Label())

        # footer
        footer = Label(
            text=(
            "..-. .-. . . -.. --- --   .- -... --- ...- .   .- .-.. .-..\n"
            "--. --- -..   .. ...   ..-. .-. . . -.. --- --"
            ),
            color=(1, 1, 1, 1),
            halign="center",
            valign="bottom",
            font_name="DejaVuSansMono",
            font_size=dp(8),
            size_hint_y=None,
            height=dp(20),
        )
        root.add_widget(footer)

        # space
        root.add_widget(Label(size_hint_y=None, height=dp(0)))

        return root

    #====================QUALITIES=====================#

    def build_qualities(self):
        lh = line_height(LINE_FONT)

        root = BoxLayout(
            orientation="vertical",
            padding=[dp(20), dp(60), dp(20), dp(20)],
        )

        table = BoxLayout(
            orientation="vertical",
            size_hint_x=0.9,
            pos_hint={"center_x": 0.5},
        )

        header = BoxLayout(size_hint_y=None, height=lh * 5)
        header.add_widget(mono_label(t("audio_header"), dp(24)))
        header.add_widget(line_gap())
        header.add_widget(mono_label(t("video_header"), dp(24)))
        table.add_widget(header)

        divider = Widget(size_hint_y=None, height=lh)
        table.add_widget(divider)

        body = BoxLayout()
        audio_scroll, self.audio_column = quality_column()
        video_scroll, self.video_column = quality_column()
        body.add_widget(audio_scroll)
        body.add_widget(line_gap())
        body.add_widget(video_scroll)
        table.add_widget(body)

        # Drawn, glyph stacks leave gaps
        stroke = max(1, round(dp(0.9)))
        with table.canvas.after:
            Color(1, 1, 1, 1)
            column_line = Rectangle()
            row_line = Rectangle()

        def redraw_lines(*_args):
            column_line.pos = (round(table.center_x - stroke / 2), body.y)
            column_line.size = (stroke, header.top - body.y)
            row_line.pos = (divider.x, round(divider.center_y - stroke / 2))
            row_line.size = (divider.width, stroke)

        for widget in (table, header, divider, body):
            widget.bind(pos=redraw_lines, size=redraw_lines)

        root.add_widget(table)

        self.qualities_status = mono_label(
            "",
            dp(15),
            size_hint_y=None,
            height=dp(30),
        )
        root.add_widget(self.qualities_status)

        return root

    #===================DOWNLOADING====================#

    def build_downloading(self):
        # Narrow screens shrink everything alike
        self.scale = min(1, Window.width / REFERENCE_WIDTH)
        self.art_font = art_font(Window.width * ART_SHARE + 1)
        self.art_cw = char_width("@", self.art_font)
        self.art_lh = line_height(self.art_font)
        # Narrow screens get fewer columns
        self.max_cols = int((Window.width - 2 * PLAYER_PADDING) / self.art_cw)
        self.art_cols = min(ART_COLS, self.max_cols)
        self.art_rows = max(1, round(self.art_cols * self.art_cw / self.art_lh))

        self.downloading_root = BoxLayout(
            orientation="vertical",
            padding=[PLAYER_PADDING, dp(12), PLAYER_PADDING, dp(2)],
        )
        self.downloading_root.add_widget(Label())
        self.player_column = Label()
        self.downloading_root.add_widget(self.player_column)
        self.downloading_root.add_widget(Label())

        self.timer_label = mono_label(
            "00:00",
            dp(10),
            color=GRAY,
            size_hint_y=None,
            height=dp(16),
        )
        self.downloading_root.add_widget(self.timer_label)

        return self.downloading_root

    def swap_player(self, column):
        index = self.downloading_root.children.index(self.player_column)
        self.downloading_root.remove_widget(self.player_column)
        self.downloading_root.add_widget(column, index=index)
        self.player_column = column

    def player_parts(self):
        column = BoxLayout(
            orientation="vertical",
            size_hint=(None, None),
            width=self.art_cols * self.art_cw,
            pos_hint={"center_x": 0.5},
        )
        column.bind(minimum_height=column.setter("height"))

        self.art_label = mono_label(
            "",
            self.art_font,
            markup=True,
            # Bold glyphs look less faded
            bold=True,
            size_hint_y=None,
            height=self.art_rows * self.art_lh,
        )
        self.bar_label = mono_label(
            "",
            LINE_FONT * self.scale,
            markup=True,
            size_hint_y=None,
            height=self.sdp(20),
        )
        return column

    def sdp(self, value):
        return dp(value) * self.scale

    def name_labels(self, title_font, artist_font):
        self.song_label = mono_label(
            "",
            title_font,
            halign="left",
            shorten=True,
            shorten_from="right",
            size_hint_y=None,
            height=title_font + self.sdp(7),
        )
        self.artist_label = mono_label(
            "",
            artist_font,
            halign="left",
            shorten=True,
            shorten_from="right",
            color=GRAY,
            size_hint_y=None,
            height=artist_font + self.sdp(7),
        )
        for label in (self.song_label, self.artist_label):
            label.bind(size=label.setter("text_size"))
        return self.song_label, self.artist_label

    def build_music_column(self):
        column = self.player_parts()
        column.add_widget(self.art_label)
        column.add_widget(Label(size_hint_y=None, height=self.sdp(28)))

        for label in self.name_labels(self.sdp(17), self.sdp(13)):
            column.add_widget(label)
        column.add_widget(Label(size_hint_y=None, height=self.sdp(18)))

        column.add_widget(self.bar_label)
        column.add_widget(Label(size_hint_y=None, height=self.sdp(14)))

        column.add_widget(mono_label(CONTROLS, self.sdp(20), size_hint_y=None, height=self.sdp(32)))
        column.add_widget(Label(size_hint_y=None, height=self.sdp(22)))

        self.counter_label = mono_label("", self.sdp(14), size_hint_y=None, height=self.sdp(20))
        column.add_widget(self.counter_label)
        return column

    def build_video_column(self):
        column = self.player_parts()
        column.add_widget(self.art_label)
        column.add_widget(Label(size_hint_y=None, height=self.sdp(8)))
        column.add_widget(self.bar_label)

        # Controls left, counter right
        controls = BoxLayout(size_hint_y=None, height=self.sdp(30))
        buttons = mono_label(VIDEO_CONTROLS, self.sdp(16), size_hint_x=None)
        buttons.bind(texture_size=lambda label, size: setattr(label, "width", size[0]))
        controls.add_widget(buttons)

        self.counter_label = mono_label("", self.sdp(13), halign="right")
        self.counter_label.bind(size=self.counter_label.setter("text_size"))
        controls.add_widget(self.counter_label)
        column.add_widget(controls)
        column.add_widget(Label(size_hint_y=None, height=self.sdp(18)))

        for label in self.name_labels(self.sdp(15), self.sdp(12)):
            column.add_widget(label)
        return column

if __name__ == "__main__":
    DownloadityApp().run()