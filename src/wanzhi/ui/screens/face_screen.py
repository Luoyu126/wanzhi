from __future__ import annotations

try:
    from kivy.clock import Clock
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label
    from kivy.uix.screenmanager import Screen
except ImportError:  # pragma: no cover
    Screen = object  # type: ignore


class FaceScreen(Screen):
    def __init__(self, font_name: str = "Roboto", **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self.font_name = font_name
        self.state = "idle"
        self.message = "丸智在这里陪着你"
        layout = BoxLayout(orientation="vertical", padding=32, spacing=16)
        self.face = Label(text="^_^", font_size=96)
        self.label = Label(text=self.message, font_size=28, font_name=self.font_name)
        layout.add_widget(self.face)
        layout.add_widget(self.label)
        self.add_widget(layout)
        Clock.schedule_interval(self._animate_idle, 1.2)

    def set_state(self, state: str, message: str = "") -> None:
        self.state = state
        self.message = message or {
            "idle": "丸智在这里陪着你",
            "listening": "我在听",
            "speaking": "我来回答你",
            "alert": "检测到紧急情况",
        }.get(state, "")
        self.face.text = {
            "idle": "^_^",
            "listening": "o_o",
            "speaking": "^o^",
            "alert": "!_!",
        }.get(state, "^_^")
        self.label.text = self.message

    def _animate_idle(self, _dt: float) -> None:
        if self.state != "idle":
            return
        self.face.text = "-_-" if self.face.text == "^_^" else "^_^"
