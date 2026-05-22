from __future__ import annotations

from pathlib import Path

try:
    from kivy.clock import Clock
    from kivy.graphics.texture import Texture
    from kivy.uix.image import Image
    from kivy.uix.label import Label
    from kivy.uix.screenmanager import Screen
except ImportError:  # pragma: no cover
    Screen = object  # type: ignore


class CameraScreen(Screen):
    def __init__(self, frame_path: Path, fps: float = 24, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self.frame_path = frame_path
        self._last_mtime = 0.0
        self.image = Image(allow_stretch=True, keep_ratio=True)
        self.status = Label(text="", size_hint=(1, None), height=32)
        self.add_widget(self.image)
        Clock.schedule_interval(self._update_frame, 1.0 / max(fps, 1.0))

    def _update_frame(self, _dt: float) -> None:
        if not self.frame_path.exists():
            return
        mtime = self.frame_path.stat().st_mtime
        if mtime <= self._last_mtime:
            return
        self._last_mtime = mtime
        import cv2

        frame = cv2.imread(str(self.frame_path))
        if frame is None:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        flipped = cv2.flip(rgb, 0)
        texture = Texture.create(size=(flipped.shape[1], flipped.shape[0]), colorfmt="rgb")
        texture.blit_buffer(flipped.tobytes(), colorfmt="rgb", bufferfmt="ubyte")
        self.image.texture = texture

    def on_leave(self, *args):  # type: ignore[no-untyped-def]
        return None
