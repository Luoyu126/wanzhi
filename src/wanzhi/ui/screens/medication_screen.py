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

from wanzhi.ui.widgets.med_card import MedicationCard


class MedicationScreen(Screen):
    def __init__(
        self,
        items_provider: Callable[[], list[dict[str, Any]]],
        mark_taken: Callable[[int, str], None],
        font_name: str = "Roboto",
        emoji_font_name: str = "Roboto",
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self.items_provider = items_provider
        self.mark_taken = mark_taken
        self.font_name = font_name
        self.emoji_font_name = emoji_font_name
        with self.canvas.before:
            Color(0.94, 0.97, 0.95, 1)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        self.root = BoxLayout(orientation="vertical", padding=(28, 24), spacing=18)

        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=62, spacing=14)
        header.add_widget(
            Label(text="💊", font_size=42, size_hint_x=None, width=58, font_name=self.emoji_font_name)
        )
        header.add_widget(
            Label(
                text="今日药物清单",
                font_size=40,
                bold=True,
                size_hint_y=None,
                height=54,
                color=(0.10, 0.20, 0.28, 1),
                font_name=self.font_name,
                halign="left",
                text_size=(520, None),
            )
        )
        self.root.add_widget(header)
        self.root.add_widget(
            Label(
                text="⏰ 请按时服药，服用后点击“已服用”",
                font_size=22,
                size_hint_y=None,
                height=34,
                color=(0.35, 0.43, 0.48, 1),
                font_name=self.font_name,
            )
        )
        self.list_box = BoxLayout(orientation="vertical", spacing=16, size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        scroll = ScrollView(bar_width=8)
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
                    subtext="🌿 你可以之后通过语音或管理界面添加药物",
                    font_name=self.font_name,
                    emoji_font_name=self.emoji_font_name,
                )
            )
            return
        for item in items:
            card = MedicationCard(
                item=item,
                on_taken=self._mark_taken,
                font_name=self.font_name,
                emoji_font_name=self.emoji_font_name,
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
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        super().__init__(orientation="vertical", padding=28, spacing=10, size_hint_y=None, height=180, **kwargs)
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self._bg = RoundedRectangle(radius=[22], pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)
        top = BoxLayout(orientation="horizontal", spacing=12)
        top.add_widget(Label(text="🧺", font_size=36, size_hint_x=None, width=52, font_name=emoji_font_name))
        top.add_widget(Label(text=text, font_size=30, bold=True, color=(0.16, 0.22, 0.28, 1), font_name=font_name))
        self.add_widget(top)
        self.add_widget(
            Label(text=subtext, font_size=20, color=(0.44, 0.50, 0.55, 1), font_name=font_name)
        )

    def _update_bg(self, *_args) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size
