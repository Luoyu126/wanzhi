from __future__ import annotations

from typing import Any, Callable

try:
    from kivy.graphics import Color, RoundedRectangle
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label
    from kivy.uix.screenmanager import Screen
    from kivy.uix.scrollview import ScrollView
except ImportError:  # pragma: no cover
    Screen = object  # type: ignore

from wanzhi.ui.fonts import DEFAULT_UI_FONT_SCALE, scaled, scaled_padding
from wanzhi.ui.widgets.med_card import MedicationCard


def _bind_wrapped_label(label: Label) -> Label:
    label.bind(width=lambda instance, width: setattr(instance, "text_size", (max(width, 1), None)))
    return label


class MedicationScreen(Screen):
    def __init__(
        self,
        items_provider: Callable[[], list[dict[str, Any]]],
        mark_taken: Callable[[int, str], None],
        font_name: str = "Roboto",
        emoji_font_name: str = "Roboto",
        font_scale: float = DEFAULT_UI_FONT_SCALE,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self.items_provider = items_provider
        self.mark_taken = mark_taken
        self.font_name = font_name
        self.emoji_font_name = emoji_font_name
        self.font_scale = font_scale
        layout_scale = min(font_scale, 1.8)
        with self.canvas.before:
            Color(0.94, 0.97, 0.95, 1)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        self.root = BoxLayout(
            orientation="vertical",
            padding=scaled_padding((24, 20), layout_scale),
            spacing=scaled(16, layout_scale),
        )

        header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=scaled(62, layout_scale),
            spacing=scaled(12, layout_scale),
        )
        header.add_widget(
            Label(
                text="药",
                font_size=scaled(38, font_scale),
                bold=True,
                size_hint_x=None,
                width=scaled(48, layout_scale),
                color=(0.20, 0.58, 0.42, 1),
                font_name=self.font_name,
            )
        )
        title = _bind_wrapped_label(
            Label(
                text="今日药物清单",
                font_size=scaled(40, font_scale),
                bold=True,
                color=(0.10, 0.20, 0.28, 1),
                font_name=self.font_name,
                halign="left",
                valign="middle",
                text_size=(1, None),
            )
        )
        header.add_widget(title)
        self.root.add_widget(header)
        self.list_box = BoxLayout(orientation="vertical", spacing=scaled(14, layout_scale), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        scroll = ScrollView(bar_width=scaled(8, layout_scale))
        scroll.add_widget(self.list_box)
        self.root.add_widget(scroll)
        self.add_widget(self.root)
        self.refresh()

    def refresh(self) -> None:
        self.list_box.clear_widgets()
        items = self.items_provider()
        if not items:
            self.list_box.add_widget(
                EmptyMedicationCard(
                    text="今天还没有药物安排",
                    subtext="你可以之后通过语音或管理界面添加药物",
                    font_name=self.font_name,
                    emoji_font_name=self.emoji_font_name,
                    font_scale=self.font_scale,
                )
            )
            return
        for item in items:
            card = MedicationCard(
                item=item,
                on_taken=self._mark_taken,
                font_name=self.font_name,
                emoji_font_name=self.emoji_font_name,
                font_scale=self.font_scale,
            )
            self.list_box.add_widget(card)

    def _mark_taken(self, item: dict[str, Any]) -> None:
        self.mark_taken(int(item["id"]), f'{item["date"]}T{item["time_of_day"]}')
        self.refresh()

    def _update_bg(self, *_args) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size


class EmptyMedicationCard(BoxLayout):
    def __init__(
        self,
        text: str,
        subtext: str,
        font_name: str,
        emoji_font_name: str = "Roboto",
        font_scale: float = DEFAULT_UI_FONT_SCALE,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        layout_scale = min(font_scale, 1.8)
        super().__init__(
            orientation="vertical",
            padding=scaled(24, layout_scale),
            spacing=scaled(10, layout_scale),
            size_hint_y=None,
            height=scaled(180, layout_scale),
            **kwargs,
        )
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self._bg = RoundedRectangle(radius=[scaled(22, layout_scale)], pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)
        top = BoxLayout(orientation="horizontal", spacing=scaled(12, layout_scale))
        top.add_widget(
            Label(
                text="空",
                font_size=scaled(32, font_scale),
                bold=True,
                size_hint_x=None,
                width=scaled(46, layout_scale),
                color=(0.20, 0.58, 0.42, 1),
                font_name=font_name,
            )
        )
        top.add_widget(
            _bind_wrapped_label(
                Label(
                    text=text,
                    font_size=scaled(30, font_scale),
                    bold=True,
                    color=(0.16, 0.22, 0.28, 1),
                    font_name=font_name,
                    halign="left",
                    valign="middle",
                    text_size=(1, None),
                )
            )
        )
        self.add_widget(top)
        self.add_widget(
            _bind_wrapped_label(
                Label(
                    text=subtext,
                    font_size=scaled(20, font_scale),
                    color=(0.44, 0.50, 0.55, 1),
                    font_name=font_name,
                    halign="left",
                    valign="middle",
                    text_size=(1, None),
                )
            )
        )

    def _update_bg(self, *_args) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size
