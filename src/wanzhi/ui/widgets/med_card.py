from __future__ import annotations

from typing import Any, Callable

try:
    from kivy.graphics import Color, RoundedRectangle
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
except ImportError:  # pragma: no cover
    BoxLayout = object  # type: ignore

from wanzhi.ui.fonts import DEFAULT_UI_FONT_SCALE, scaled


def _bind_wrapped_label(label: Label) -> Label:
    label.bind(width=lambda instance, width: setattr(instance, "text_size", (max(width, 1), None)))
    return label


class MedicationCard(BoxLayout):
    def __init__(
        self,
        item: dict[str, Any],
        on_taken: Callable[[dict[str, Any]], None],
        font_name: str = "Roboto",
        emoji_font_name: str = "Roboto",
        font_scale: float = DEFAULT_UI_FONT_SCALE,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        layout_scale = min(font_scale, 1.8)
        super().__init__(
            orientation="horizontal",
            padding=(scaled(16, layout_scale), scaled(12, layout_scale)),
            spacing=scaled(14, layout_scale),
            size_hint_y=None,
            height=scaled(126, layout_scale),
            **kwargs,
        )
        self.item = item
        with self.canvas.before:
            Color(1.0, 1.0, 1.0, 1)
            self._bg = RoundedRectangle(radius=[scaled(18, layout_scale)], pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        name = item["name"]
        dosage = item.get("dosage") or ""
        time_of_day = item["time_of_day"]

        icon_box = BoxLayout(orientation="vertical", size_hint_x=None, width=scaled(46, layout_scale))
        icon_box.add_widget(
            Label(
                text="时",
                font_size=scaled(30, font_scale),
                bold=True,
                color=(0.20, 0.58, 0.42, 1),
                font_name=font_name,
            )
        )
        self.add_widget(icon_box)

        time_box = BoxLayout(orientation="vertical", size_hint_x=None, width=scaled(108, layout_scale))
        time_box.add_widget(
            Label(
                text=time_of_day,
                font_size=scaled(32, font_scale),
                bold=True,
                color=(0.12, 0.25, 0.38, 1),
                font_name=font_name,
            )
        )
        time_box.add_widget(
            Label(
                text="服药时间",
                font_size=scaled(16, font_scale),
                color=(0.45, 0.52, 0.58, 1),
                font_name=font_name,
            )
        )
        self.add_widget(time_box)

        info_box = BoxLayout(orientation="vertical", spacing=scaled(2, layout_scale))
        name_label = _bind_wrapped_label(
            Label(
                text=f"药品：{name}",
                font_size=scaled(28, font_scale),
                bold=True,
                color=(0.10, 0.12, 0.16, 1),
                font_name=font_name,
                halign="left",
                valign="middle",
                text_size=(1, None),
            )
        )
        dosage_label = _bind_wrapped_label(
            Label(
                text=f"剂量：{dosage or '请按医嘱服用'}",
                font_size=scaled(20, font_scale),
                color=(0.35, 0.39, 0.44, 1),
                font_name=font_name,
                halign="left",
                valign="middle",
                text_size=(1, None),
            )
        )
        info_box.add_widget(name_label)
        info_box.add_widget(dosage_label)
        self.add_widget(info_box)

        button = Button(
            text="已服用",
            size_hint_x=None,
            width=scaled(132, layout_scale),
            font_size=scaled(22, font_scale),
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
