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

from wanzhi.ui.fonts import DEFAULT_UI_FONT_SCALE, scaled


class CameraScreen(Screen):
    def __init__(
        self,
        *,
        shm_name: str = "wanzhi_camera_preview",
        fps: float = 24,
        font_name: str = "Roboto",
        font_scale: float = DEFAULT_UI_FONT_SCALE,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self.shm_name = shm_name
        self.font_name = font_name
        self.font_scale = font_scale
        self._reader = None
        self._waiting_for_shm = True
        self.image = Image(allow_stretch=True, keep_ratio=True)
        self.image.texture = _solid_texture((2, 2), color=(0, 0, 0))
        self.status = Label(
            text="等待摄像头预览…",
            size_hint=(1, None),
            height=scaled(32, font_scale),
            font_size=scaled(22, font_scale),
            font_name=self.font_name,
            color=(1, 1, 1, 1),
        )
        self.add_widget(self.image)
        self.add_widget(self.status)
        Clock.schedule_interval(self._update_frame, 1.0 / max(fps, 1.0))

    def _ensure_reader(self) -> bool:
        if self._reader is not None:
            return True
        try:
            from wanzhi.core.frame_shm import SharedMemoryFrameReader

            self._reader = SharedMemoryFrameReader(self.shm_name)
            self._waiting_for_shm = False
            self.status.text = ""
            return True
        except FileNotFoundError:
            if not self._waiting_for_shm:
                self.status.text = "等待摄像头预览…"
                self._waiting_for_shm = True
            return False

    def _update_frame(self, _dt: float) -> None:
        if not self._ensure_reader() or self._reader is None:
            return

        frame, header = self._reader.read_if_updated()
        if frame is None or header is None:
            return

        flipped = frame[::-1, :, :]
        texture = Texture.create(size=(header.width, header.height), colorfmt="rgb")
        texture.blit_buffer(flipped.tobytes(), colorfmt="rgb", bufferfmt="ubyte")
        self.image.texture = texture

    def on_leave(self, *args):  # type: ignore[no-untyped-def]
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        return None


def _solid_texture(size: tuple[int, int], *, color: tuple[int, int, int]):
    texture = Texture.create(size=size, colorfmt="rgb")
    width, height = size
    payload = bytes(color) * width * height
    texture.blit_buffer(payload, colorfmt="rgb", bufferfmt="ubyte")
    return texture
