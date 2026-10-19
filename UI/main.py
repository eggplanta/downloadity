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
from kivy.graphics import Color, Line

from downloadity.extractor import is_downloadable

Window.clearcolor = (0, 0, 0, 1)

version = "v 0.1.0"

LOGO = f"""
▗▄▖             ▝▜            ▐  ▝   ▗      
▐ ▝▖ ▄▖ ▖  ▖▗▗▖  ▐   ▄▖  ▄▖  ▄▟ ▗▄  ▗▟▄ ▗ ▗ 
▐  ▌▐▘▜ ▚▗▗▘▐▘▐  ▐  ▐▘▜ ▝ ▐ ▐▘▜  ▐   ▐  ▝▖▞ 
▐  ▌▐ ▐ ▐▟▟ ▐ ▐  ▐  ▐ ▐ ▗▀▜ ▐ ▐  ▐   ▐   ▙▌ 
▐▄▞ ▝▙▛  ▌▌ ▐ ▐  ▝▄ ▝▙▛ ▝▄▜ ▝▙█ ▗▟▄  ▝▄  ▜  
                                         ▞  
                            {version}  ▝▘
"""

def char_width(char, font_size):
    label = CoreLabel(
        text=char,
        font_name="DejaVuSansMono",
        font_size=font_size,
    )
    label.refresh()
    return label.texture.size[0]

def line_height(font_size):
    label = CoreLabel(
        text="Mg",
        font_name="DejaVuSansMono",
        font_size=font_size,
    )
    label.refresh()
    return label.texture.size[1]

class AsciiButton(Button):
    BORDER_FONT = dp(12)

    def __init__(self, label, font_size=dp(15), border=True, rows=None, **kwargs):
        super().__init__(**kwargs)
        self.label_text = label
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

            self.buttons.height = 0
            self.buttons.opacity = 0
            return

        self.check_event = Clock.schedule_once(
            lambda dt: threading.Thread(
                target=self.check_link,
                args=(value.strip(),),
                daemon=True,
            ).start(),
            0.3,
        )

    def check_link(self, url):
        valid = is_downloadable(url)

        Clock.schedule_once(
            lambda dt: self.show_result(valid)
        )

    def show_result(self, valid):
        color = (0, 1, 0, 1) if valid else (1, 0, 0, 1)

        for widget in (
            self.pipe_left,
            self.pipe_right,
            self.top_border,
            self.bottom_border,
        ):
            widget.color = color

        if valid:
            self.buttons.height = self.download_button.height
            self.buttons.opacity = 1
        else:
            self.buttons.height = 0
            self.buttons.opacity = 0


    #======================BUILD=======================#

    def build(self):

        root = BoxLayout(
            orientation="vertical",
            padding=[dp(20), dp(20)],
            spacing=dp(20),
        )

        # top row: espaço à esquerda + botão de destino à direita
        top_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(120),
        )

        top_row.add_widget(Label())

        right_col = BoxLayout(
            orientation="vertical",
            size_hint=(None, None),
            width=dp(300),
            height=dp(120),
        )

        self.destination_button = AsciiButton(
            "change download destination",
            size_hint=(None, None),
            height=dp(45),
            width=dp(300),
            font_size=dp(15),
            border=False,
        )

        right_col.add_widget(self.destination_button)
        right_col.add_widget(Label())

        top_row.add_widget(right_col)
        root.add_widget(top_row)

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

        self.buttons.add_widget(self.download_button)

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

if __name__ == "__main__":
    DownloadityApp().run()