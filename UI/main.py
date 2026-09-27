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

from downloadity.extractor import resolve

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

def _check_link(self, url):
    try:
        info = resolve(url)
    except Exception as e:
        info = {"type": "error", "message": str(e)}

    Clock.schedule_once(lambda _dt: self.on_link_checked(info))

def on_link_checked(self, info):
    self.checking = False

    if hasattr(self, "spinner_event"):
        self.spinner_event.cancel()

    if info.get("type") == "error":
        self.show_invalid()
    else:
        self.show_valid()

class DownloadityApp(App):

    def build(self):

        root = BoxLayout(
            orientation="vertical",
            padding=[dp(20), dp(20)],
            spacing=dp(20),
        )

        # space
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
        def char_width(char, font_size):
            label = CoreLabel(
                text=char,
                font_name="DejaVuSansMono",
                font_size=font_size,
            )
            label.refresh()
            return label.texture.size[0]

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

        link_input = TextInput(
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

        input_row.add_widget(pipe_left)
        input_row.add_widget(link_input)
        input_row.add_widget(pipe_right)

        top_border = Label(
            color=(1, 1, 1, 1),
            font_name="DejaVuSansMono",
            font_size=12,
            size_hint=(1, None),
            height=dp(20),
            halign="center",
        )
        bottom_border = Label(
            color=(1, 1, 1, 1),
            font_name="DejaVuSansMono",
            font_size=12,
            size_hint=(1, None),
            height=dp(20),
            halign="center",
        )

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
            height=dp(30),
        )
        root.add_widget(footer)

        # space
        root.add_widget(Label(size_hint_y=None, height=dp(1)))

        return root


if __name__ == "__main__":
    DownloadityApp().run()