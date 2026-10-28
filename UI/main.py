import logging
import math
import os
import threading

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp
from kivy.uix.textinput import TextInput
from kivy.core.text import Label as CoreLabel
from kivy.clock import Clock
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.modalview import ModalView
from kivy.uix.floatlayout import FloatLayout
from kivy.utils import escape_markup, platform

from downloadity.download_queue import DownloadQueue
from downloadity.media import resolve_media
from ascii_art import cover_markup

Window.clearcolor = (0, 0, 0, 1)

# Kivy logs third-party debug otherwise
logging.getLogger().setLevel(logging.WARNING)

version = "v 0.1.0"

LINE_FONT = dp(12)
CHECKING_FRAMES = ("checking ..", "checking. .", "checking.. ", "checking...")

ART_FONT = dp(8)
ART_COLS = 60
GRAY = (0.5, 0.5, 0.5, 1)
CONTROLS = "⇄    ▮◀    ❚❚    ▶▮    ↻"
VIDEO_CONTROLS = "▮◀   ❚❚   ▶▮"
VIDEO_ASPECT = 16 / 9
VIDEO_ASPECTS = (0.5, 2.4)

if platform == "android":
    DOWNLOAD_ROOT = "/storage/emulated/0/downloadity"
else:
    DOWNLOAD_ROOT = os.path.expanduser("~/Downloads/downloadity")

LOGO = f"""
▗▄▖             ▝▜            ▐  ▝   ▗      
▐ ▝▖ ▄▖ ▖  ▖▗▗▖  ▐   ▄▖  ▄▖  ▄▟ ▗▄  ▗▟▄ ▗ ▗ 
▐  ▌▐▘▜ ▚▗▗▘▐▘▐  ▐  ▐▘▜ ▝ ▐ ▐▘▜  ▐   ▐  ▝▖▞ 
▐  ▌▐ ▐ ▐▟▟ ▐ ▐  ▐  ▐ ▐ ▗▀▜ ▐ ▐  ▐   ▐   ▙▌ 
▐▄▞ ▝▙▛  ▌▌ ▐ ▐  ▝▄ ▝▙▛ ▝▄▜ ▝▙█ ▗▟▄  ▝▄  ▜  
                                         ▞  
                            {version}  ▝▘
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

def line_height(font_size):
    label = CoreLabel(
        text="Mg",
        font_name="DejaVuSansMono",
        font_size=font_size,
    )
    label.refresh()
    return label.texture.size[1]

def mono_label(text, font_size, **kwargs):
    kwargs.setdefault("halign", "center")
    kwargs.setdefault("valign", "middle")
    kwargs.setdefault("color", (1, 1, 1, 1))
    return Label(
        text=text,
        font_name="DejaVuSansMono",
        font_size=font_size,
        **kwargs,
    )

def vertical_line():
    lh = line_height(LINE_FONT)
    label = mono_label(
        "",
        LINE_FONT,
        size_hint_x=None,
        width=char_width("│", LINE_FONT),
        valign="top",
    )

    def redraw(_instance, size):
        label.text_size = size
        label.text = "\n".join(["│"] * max(1, int(size[1] / lh)))

    label.bind(size=redraw)
    return label

def quality_column():
    column = BoxLayout(
        orientation="vertical",
        size_hint_y=None,
        padding=[0, dp(24), 0, 0],
        spacing=dp(28),
    )
    column.bind(minimum_height=column.setter("height"))

    scroll = ScrollView(do_scroll_x=False)
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

        self.text_label = Label(
            text=label,
            font_name="DejaVuSansMono",
            font_size=font_size,
            halign="center",
            valign="middle",
            markup=True,
        )

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

        lines = [" " + "_" + "─" * (inner-4) + "_" + " "]
        lines += ["┌" + " " * (inner - 1) + "┐"]
        lines += ["|" + " " * inner + "|"] * (rows - 4)
        lines += ["└" + " " * (inner - 1) + "┘"]
        lines += ["‾" + "─" * (inner-4) + "‾" + " "]
        self.border_label.text = "\n".join(lines)

    def update_color(self, *args):
        c = (0.6, 0.6, 0.6, 1) if self.state == "down" else (1, 1, 1, 1)
        self.border_label.color = c
        self.text_label.color = c

class AsciiPopup(ModalView):
    def __init__(self, message, buttons, items=None, **kwargs):
        super().__init__(
            size_hint=(None, None),
            size=(dp(320), dp(420) if items else dp(230)),
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
            padding=[dp(40), dp(28), dp(40), dp(18)],
            spacing=dp(8),
            pos_hint={"x": 0, "y": 0},
        )

        text = mono_label(message, dp(15), markup=True)
        text.bind(size=text.setter("text_size"))
        if items:
            text.size_hint_y = None
            text.height = dp(40)
        content.add_widget(text)

        if items:
            content.add_widget(self.item_list(items))

        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(16))
        for label, callback in buttons:
            button = AsciiButton(escape_markup(f"[ {label} ]"), border=False, font_size=dp(15))
            button.bind(on_release=lambda _b, cb=callback: self.choose(cb))
            row.add_widget(button)
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
        try:
            media = resolve_media(url)
        except Exception:
            media = None

        Clock.schedule_once(
            lambda dt: self.show_result(url, media)
        )

    def show_result(self, url, media):
        if url != self.link_input.text.strip():
            return

        self.media = media
        valid = media is not None
        color = (0, 1, 0, 1) if valid else (1, 0, 0, 1)

        for widget in (
            self.pipe_left,
            self.pipe_right,
            self.top_border,
            self.bottom_border,
        ):
            widget.color = color

        self.show_in_result_area(self.download_button if valid else None)

    def start_checking(self):
        if self.checking_event:
            return

        self.checking_frame = 0
        self.checking_label.text = CHECKING_FRAMES[0]
        self.show_in_result_area(self.checking_label)
        self.checking_event = Clock.schedule_interval(self.animate_checking, 0.3)

    def animate_checking(self, dt):
        self.checking_frame = (self.checking_frame + 1) % len(CHECKING_FRAMES)
        self.checking_label.text = CHECKING_FRAMES[self.checking_frame]

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
        options = self.media.options

        has_options = options.audio or options.video
        self.qualities_status.text = "" if has_options else "no options found"
        self.fill_quality_column(self.audio_column, "audio", options.audio)
        self.fill_quality_column(self.video_column, "video", options.video)

        self.screens.current = "qualities"

    def fill_quality_column(self, column, kind, qualities):
        column.clear_widgets()

        for quality in sorted(qualities, key=lambda q: q.value, reverse=True):
            text = quality.label
            if quality.filesize_label:
                text += f"\n[size={int(dp(14))}]({quality.filesize_label})[/size]"

            button = AsciiButton(
                text,
                border=False,
                size_hint_y=None,
                height=dp(64),
                font_size=dp(20),
            )
            button.bind(
                on_release=lambda _b, q=quality: self.on_quality_select(kind, q)
            )
            column.add_widget(button)

    def on_quality_select(self, kind, quality):
        message = f"download in {quality.label}?"
        size = quality.filesize_label
        if size:
            usage = f"~{size}" if self.media.is_playlist else size
            message += f"\n\nthis will use {usage}\nof your storage"

        AsciiPopup(
            message,
            [
                ("cancel", lambda: None),
                ("confirm", lambda: self.confirm_invalid(kind, quality)),
            ],
        ).open()

    def confirm_invalid(self, kind, quality):
        if not self.media.invalid:
            self.start_download(kind, quality)
            return

        AsciiPopup(
            "these items are invalid\nand won't be downloaded:",
            [("OK", lambda: self.start_download(kind, quality))],
            items=[e.title or "unknown title" for e in self.media.invalid],
        ).open()

    #====================DOWNLOAD======================#

    def start_download(self, kind, quality):
        self.kind = kind
        self.total_items = len(self.media.entries)
        self.swap_player(self.build_video_column() if kind == "video" else self.build_music_column())
        self.show_item_placeholder()
        self.screens.current = "downloading"

        self.elapsed = 0
        self.timer_label.text = "00:00"
        self.timer_event = Clock.schedule_interval(self.tick_timer, 1)

        queue = DownloadQueue(
            self.media,
            kind,
            quality.value,
            DOWNLOAD_ROOT,
            listener=self,
            prepare_extra=self.make_art,
        )
        threading.Thread(target=self.run_queue, args=(queue,), daemon=True).start()

    def run_queue(self, queue):
        try:
            queue.run()
        except Exception as e:
            error = str(e)
            Clock.schedule_once(lambda dt: self.show_finished(0, [], queue.output_dir, error))

    def make_art(self, entry):
        info = entry.info["ytdlp_info"]
        cols, rows = self.art_dims(info)
        aspect = cols * self.art_cw / (rows * self.art_lh)
        return cover_markup(info, cols, rows, aspect), cols, rows

    def art_dims(self, info):
        if self.kind != "video":
            return ART_COLS, self.art_rows

        # Playlists keep a fixed 16:9 frame
        width, height = (info or {}).get("width"), (info or {}).get("height")
        aspect = VIDEO_ASPECT
        if width and height and not self.media.is_playlist:
            aspect = min(VIDEO_ASPECTS[1], max(VIDEO_ASPECTS[0], width / height))
        area = ART_COLS * self.art_cw * self.art_rows * self.art_lh
        cols = round(math.sqrt(area * aspect) / self.art_cw)
        rows = round(math.sqrt(area / aspect) / self.art_lh)
        return cols, rows

    # Queue listener (worker thread)

    def on_item_start(self, item):
        Clock.schedule_once(lambda dt: self.show_item(item))

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
        self.bar_cols = int(width / char_width("━", LINE_FONT))

    def draw_bar(self, fraction):
        played = int(fraction * (self.bar_cols - 1))
        rest = self.bar_cols - 1 - played
        self.bar_label.text = (
            f"[color=#ffffff]{'━' * played}●[/color]"
            f"[color=#555555]{'─' * rest}[/color]"
        )

    def tick_timer(self, dt):
        self.elapsed += 1
        minutes, seconds = divmod(self.elapsed, 60)
        self.timer_label.text = f"{minutes:02d}:{seconds:02d}"

    def show_finished(self, done, failed, folder, error=None):
        self.timer_event.cancel()
        self.draw_bar(1)

        if error:
            message = f"download failed\n\n{error}"
        else:
            message = f"download finished!\n\nyour files are in:\n{folder}"

        after = lambda: self.show_failed(failed) if failed else self.reset_home()
        AsciiPopup(escape_markup(message), [("OK", after)]).open()

    def show_failed(self, failed):
        AsciiPopup(
            f"{len(failed)} item(s) failed:",
            [("OK", self.reset_home)],
            items=failed,
        ).open()

    def reset_home(self):
        self.media = None
        self.link_input.text = ""
        self.screens.current = "home"


    #======================BUILD=======================#

    def build(self):
        self.screens = ScreenManager(transition=NoTransition())

        home = Screen(name="home")
        home.add_widget(self.build_home())
        self.screens.add_widget(home)

        qualities = Screen(name="qualities")
        qualities.add_widget(self.build_qualities())
        self.screens.add_widget(qualities)

        downloading = Screen(name="downloading")
        downloading.add_widget(self.build_downloading())
        self.screens.add_widget(downloading)

        return self.screens

    def build_home(self):

        root = BoxLayout(
            orientation="vertical",
            padding=[dp(20), dp(20)],
            spacing=dp(20),
        )

        # top space
        root.add_widget(Label(size_hint_y=None, height=dp(120)))

        # logo
        logo = Label(
            text=LOGO,
            color=(1, 1, 1, 1),
            font_name="DejaVuSansMono",
            font_size=dp(12),
            halign="center",
            valign="top",
            size_hint_y=None,
            height=dp(110),
        )
        logo.text_size = (Window.width - dp(40), None)
        root.add_widget(logo)

        # space
        root.add_widget(Label(size_hint_y=None, height=dp(110)))

        # "paste the link:"
        link_label = Label(
            text="paste the link:",
            color=(1, 1, 1, 1),
            halign="left",
            valign="middle",
            size_hint=(0.6, None),
            font_name="DejaVuSansMono",
            font_size=dp(15),
            height=dp(18),
            pos_hint={"center_x": 0.5},
        )
        link_label.bind(size=link_label.setter("text_size"))
        root.add_widget(link_label)

        # input box

        dash_width = char_width("─", 12)

        link_frame = BoxLayout(
            orientation="vertical",
            size_hint=(0.8, None),
            height=dp(60),
            pos_hint={"center_x": 0.5},
        )

        input_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(28),
            padding=[dp(-4.5), 0],
            pos_hint={"center_x": 0.5},
        )

        pipe_left = Label(
            text="│",
            color=(1, 1, 1, 1),
            font_name="DejaVuSansMono",
            font_size=dp(12),
            size_hint_x=None,
            width=dp(16),
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
            width=dp(16),
        )
        self.pipe_right = pipe_right

        input_row.add_widget(pipe_left)
        input_row.add_widget(self.link_input)
        input_row.add_widget(pipe_right)

        top_border = Label(
            color=(1, 1, 1, 1),
            font_name="DejaVuSansMono",
            font_size=12,
            size_hint=(1, None),
            height=dp(20),
            halign="center",
        )
        self.top_border = top_border

        bottom_border = Label(
            color=(1, 1, 1, 1),
            font_name="DejaVuSansMono",
            font_size=12,
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
            "DOWNLOAD",
            size_hint=(None, None),
            width=dp(280),
            pos_hint={"center_x": 0.5},
            font_size=dp(18),
            rows=7,
        )

        self.download_button.bind(on_release=self.on_download_press)

        self.checking_label = mono_label(
            "",
            dp(12),
            size_hint_y=None,
            height=dp(20),
        )
        self.checking_event = None

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
            font_size=dp(12),
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

        header = BoxLayout(size_hint_y=None, height=lh * 3)
        header.add_widget(mono_label("AUDIO", dp(24)))
        header.add_widget(vertical_line())
        header.add_widget(mono_label("VIDEO", dp(24)))
        root.add_widget(header)

        dash_width = char_width("─", LINE_FONT)
        divider = mono_label("", LINE_FONT, size_hint_y=None, height=lh)

        def redraw_divider(_instance, width):
            side = max(1, int((width - dash_width) / 2 / dash_width))
            divider.text = "─" * side + "┼" + "─" * side

        divider.bind(width=redraw_divider)
        root.add_widget(divider)

        body = BoxLayout()
        audio_scroll, self.audio_column = quality_column()
        video_scroll, self.video_column = quality_column()
        body.add_widget(audio_scroll)
        body.add_widget(vertical_line())
        body.add_widget(video_scroll)
        root.add_widget(body)

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
        self.art_cw = char_width("@", ART_FONT)
        self.art_lh = line_height(ART_FONT)
        self.art_rows = max(1, round(ART_COLS * self.art_cw / self.art_lh))

        self.downloading_root = BoxLayout(
            orientation="vertical",
            padding=[dp(20), dp(12), dp(20), dp(12)],
        )
        self.downloading_root.add_widget(Label())
        self.player_column = Label()
        self.downloading_root.add_widget(self.player_column)
        self.downloading_root.add_widget(Label())

        self.timer_label = mono_label(
            "00:00",
            dp(11),
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
            width=ART_COLS * self.art_cw,
            pos_hint={"center_x": 0.5},
        )
        column.bind(minimum_height=column.setter("height"))

        self.art_label = mono_label(
            "",
            ART_FONT,
            markup=True,
            size_hint_y=None,
            height=self.art_rows * self.art_lh,
        )
        self.bar_label = mono_label(
            "",
            LINE_FONT,
            markup=True,
            size_hint_y=None,
            height=dp(20),
        )
        return column

    def name_labels(self, title_font, artist_font):
        self.song_label = mono_label(
            "",
            title_font,
            halign="left",
            shorten=True,
            shorten_from="right",
            size_hint_y=None,
            height=title_font + dp(7),
        )
        self.artist_label = mono_label(
            "",
            artist_font,
            halign="left",
            shorten=True,
            shorten_from="right",
            color=GRAY,
            size_hint_y=None,
            height=artist_font + dp(7),
        )
        for label in (self.song_label, self.artist_label):
            label.bind(size=label.setter("text_size"))
        return self.song_label, self.artist_label

    def build_music_column(self):
        column = self.player_parts()
        column.add_widget(self.art_label)
        column.add_widget(Label(size_hint_y=None, height=dp(28)))

        for label in self.name_labels(dp(17), dp(13)):
            column.add_widget(label)
        column.add_widget(Label(size_hint_y=None, height=dp(18)))

        column.add_widget(self.bar_label)
        column.add_widget(Label(size_hint_y=None, height=dp(14)))

        column.add_widget(mono_label(CONTROLS, dp(20), size_hint_y=None, height=dp(32)))
        column.add_widget(Label(size_hint_y=None, height=dp(22)))

        self.counter_label = mono_label("", dp(14), size_hint_y=None, height=dp(20))
        column.add_widget(self.counter_label)
        return column

    def build_video_column(self):
        column = self.player_parts()
        column.add_widget(self.art_label)
        column.add_widget(Label(size_hint_y=None, height=dp(8)))
        column.add_widget(self.bar_label)

        # Controls left, counter right
        controls = BoxLayout(size_hint_y=None, height=dp(30))
        buttons = mono_label(VIDEO_CONTROLS, dp(16), size_hint_x=None)
        buttons.bind(texture_size=lambda label, size: setattr(label, "width", size[0]))
        controls.add_widget(buttons)

        self.counter_label = mono_label("", dp(13), halign="right")
        self.counter_label.bind(size=self.counter_label.setter("text_size"))
        controls.add_widget(self.counter_label)
        column.add_widget(controls)
        column.add_widget(Label(size_hint_y=None, height=dp(18)))

        for label in self.name_labels(dp(15), dp(12)):
            column.add_widget(label)
        return column

if __name__ == "__main__":
    DownloadityApp().run()