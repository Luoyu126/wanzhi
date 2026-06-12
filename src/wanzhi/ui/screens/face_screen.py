from __future__ import annotations

import re

try:
    from kivy.clock import Clock
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label
    from kivy.uix.screenmanager import Screen
    from kivy.uix.scrollview import ScrollView
except ImportError:  # pragma: no cover
    Screen = object  # type: ignore

from wanzhi.ui.fonts import DEFAULT_UI_FONT_SCALE, scaled, scaled_padding


class FaceScreen(Screen):
    CJK_RANGE = "\u3400-\u9fff\uf900-\ufaff"
    EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]\ufe0f?")
    DEFAULT_FACE = "👀"
    DEFAULT_FACE_SIZE = 104
    DEFAULT_COLOR = (1, 1, 1, 1)
    ALERT_COLOR = (1, 0.12, 0.12, 1)

    def __init__(
        self,
        font_name: str = "Roboto",
        emoji_font_name: str = "Roboto",
        font_scale: float = DEFAULT_UI_FONT_SCALE,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self.font_name = font_name
        self.emoji_font_name = emoji_font_name
        self.font_scale = font_scale
        layout_scale = min(font_scale, 1.25)
        self.state = "idle"
        self.message = "丸智在这里陪着你"
        self._status_text = self.message
        self._utterance_text = ""
        layout = BoxLayout(
            orientation="vertical",
            padding=scaled_padding((28, 24, 28, 24), layout_scale),
            spacing=scaled(14, layout_scale),
        )
        self.face = Label(
            text=type(self).DEFAULT_FACE,
            font_size=scaled(type(self).DEFAULT_FACE_SIZE, min(font_scale, 1.45)),
            font_name=self.emoji_font_name,
            size_hint_y=None,
            height=scaled(136, min(font_scale, 1.35)),
            color=(1, 1, 1, 1),
        )
        self.label = Label(
            text=self.message,
            font_size=scaled(28, font_scale),
            font_name=self.font_name,
            size_hint_y=None,
            halign="center",
            valign="middle",
        )
        self.label.bind(
            width=self._update_status_text_size,
            texture_size=self._update_status_height,
        )
        self.utterance_scroll = ScrollView(
            size_hint=(1, 1),
            do_scroll_x=False,
            bar_width=scaled(8, layout_scale),
        )
        self.utterance_label = Label(
            text="",
            font_size=scaled(24, font_scale),
            font_name=self.font_name,
            size_hint=(None, None),
            text_size=(0, None),
            halign="center",
            valign="top",
        )
        self.label.split_str = ""
        self.utterance_label.split_str = ""
        self.utterance_scroll.bind(
            width=self._update_utterance_width,
            height=self._update_utterance_height,
        )
        self.utterance_label.bind(
            width=self._update_utterance_text_size,
            texture_size=self._update_utterance_height,
        )
        self.utterance_scroll.add_widget(self.utterance_label)
        layout.add_widget(self.face)
        layout.add_widget(self.label)
        layout.add_widget(self.utterance_scroll)
        self.add_widget(layout)
        Clock.schedule_once(lambda _dt: self._update_text_layout(), 0)

    def set_state(self, state: str, message: str = "") -> None:
        self.state = state
        self.message = message or {
            "idle": "丸智在这里陪着你",
            "listening": "",
            "speaking": "",
            "alert": "检测到紧急情况",
        }.get(state, "")
        self._status_text = self.message
        if state == "alert":
            self._set_sos_face()
        else:
            self._reset_face()
        self._update_status_text_size()

    def set_user_text(self, text: str) -> None:
        self._utterance_text = text or ""
        self._update_utterance_text_size()

    def set_reply_text(self, text: str) -> None:
        self._utterance_text = text or ""
        self._update_utterance_text_size()

    def set_suggested_emoji(self, emoji: str) -> None:
        match = type(self).EMOJI_RE.search(emoji or "")
        if match is None:
            return
        self.face.text = match.group(0)
        self.face.font_name = self.emoji_font_name
        self.face.font_size = scaled(106, min(self.font_scale, 1.45))
        self.face.opacity = 1.0
        self.face.color = self.DEFAULT_COLOR

    def _update_text_layout(self) -> None:
        self._update_status_text_size()
        self._update_utterance_width()
        self._update_utterance_text_size()

    def _update_status_text_size(self, *_args) -> None:
        self.label.text_size = (max(self.label.width, 1), None)
        self.label.text = self._normalize_display_text(self._status_text)

    def _update_status_height(self, *_args) -> None:
        self.label.height = self.label.texture_size[1]

    def _update_utterance_width(self, *_args) -> None:
        self.utterance_label.width = max(self.utterance_scroll.width - self.utterance_scroll.bar_width, 1)
        self._update_utterance_text_size()

    def _update_utterance_text_size(self, *_args) -> None:
        self.utterance_label.text_size = (max(self.utterance_label.width, 1), None)
        self.utterance_label.text = self._normalize_display_text(self._utterance_text)

    def _update_utterance_height(self, *_args) -> None:
        self.utterance_label.height = max(
            self.utterance_label.texture_size[1],
            self.utterance_scroll.height,
        )

    def _normalize_display_text(self, text: str) -> str:
        normalized = " ".join((text or "").split())
        cjk = type(self).CJK_RANGE
        while True:
            compacted = re.sub(rf"([{cjk}])\s+([{cjk}])", r"\1\2", normalized)
            if compacted == normalized:
                break
            normalized = compacted
        normalized = re.sub(rf"([{cjk}])\s+([，。！？；：、,.!?;:])", r"\1\2", normalized)
        normalized = re.sub(rf"([，。！？；：、,.!?;:])\s+([{cjk}])", r"\1\2", normalized)
        return normalized

    def _reset_face(self) -> None:
        self.face.text = type(self).DEFAULT_FACE
        self.face.font_name = self.emoji_font_name
        self.face.font_size = scaled(type(self).DEFAULT_FACE_SIZE, min(self.font_scale, 1.45))
        self.face.opacity = 1.0
        self.face.color = type(self).DEFAULT_COLOR
        self.label.color = type(self).DEFAULT_COLOR

    def _set_sos_face(self) -> None:
        self.face.text = "SOS"
        self.face.font_name = self.font_name
        self.face.font_size = scaled(118, min(self.font_scale, 1.45))
        self.face.opacity = 1.0
        self.face.color = type(self).ALERT_COLOR
        self.label.color = type(self).ALERT_COLOR
