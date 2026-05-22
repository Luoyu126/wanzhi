from __future__ import annotations

from typing import Any, Callable

try:
    from kivy.graphics import Color, RoundedRectangle
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
except ImportError:  # pragma: no cover
    BoxLayout = object  # type: ignore


class MedicationCard(BoxLayout):
    def __init__(
        self,
        item: dict[str, Any],
        on_taken: Callable[[dict[str, Any]], None],
        font_name: str = "Roboto",
        emoji_font_name: str = "Roboto",
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        super().__init__(orientation="horizontal", padding=(18, 14), spacing=16, size_hint_y=None, height=112, **kwargs)
        self.item = item
        with self.canvas.before:
            Color(1.0, 1.0, 1.0, 1)
            self._bg = RoundedRectangle(radius=[18], pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        name = item["name"]
        dosage = item.get("dosage") or ""
        time_of_day = item["time_of_day"]

        icon_box = BoxLayout(orientation="vertical", size_hint_x=None, width=56)
        icon_box.add_widget(Label(text="⏰", font_size=32, font_name=emoji_font_name))
        self.add_widget(icon_box)

        time_box = BoxLayout(orientation="vertical", size_hint_x=None, width=108)
        time_box.add_widget(
            Label(
                text=time_of_day,
                font_size=32,
                bold=True,
                color=(0.12, 0.25, 0.38, 1),
                font_name=font_name,
            )
        )
        time_box.add_widget(
            Label(
                text="服药时间",
                font_size=16,
                color=(0.45, 0.52, 0.58, 1),
                font_name=font_name,
            )
        )
        self.add_widget(time_box)

        info_box = BoxLayout(orientation="vertical", spacing=2)
        info_box.add_widget(
            Label(
                text=f"💊 {name}",
                font_size=28,
                bold=True,
                color=(0.10, 0.12, 0.16, 1),
                font_name=font_name,
                halign="left",
                valign="middle",
                text_size=(420, None),
            )
        )
        info_box.add_widget(
            Label(
                text=f"📋 {dosage or '请按医嘱服用'}",
                font_size=20,
                color=(0.35, 0.39, 0.44, 1),
                font_name=font_name,
                halign="left",
                valign="middle",
                text_size=(420, None),
            )
        )
        self.add_widget(info_box)

        button = Button(
            text="✅ 已服用",
            size_hint_x=None,
            width=132,
            font_size=22,
            font_name=font_name,
            background_normal="",
            background_color=(0.20, 0.58, 0.42, 1),
            color=(1, 1, 1, 1),
        )
        button.bind(on_press=lambda *_args: on_taken(self.item))
        self.add_widget(button)

    def _update_bg(self, *_args) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size
