from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CameraFrame:
    frame: object
    captured_at: float


class Camera:
    def __init__(
        self,
        camera_id: int = 0,
        device_path: str | None = None,
        width: int = 640,
        height: int = 480,
        fps: float | None = None,
        max_failures: int = 10,
    ) -> None:
        import cv2

        self.cv2 = cv2
        self.camera_id = camera_id
        self.device_path = device_path
        self.width = width
        self.height = height
        self.fps = fps
        self.max_failures = max_failures
        self.failures = 0
        self.capture = None
        self.open()

    @property
    def source(self) -> int | str:
        return self.device_path or self.camera_id

    def open(self) -> None:
        self.close()
        self.capture = self.cv2.VideoCapture(self.source)
        self.capture.set(self.cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.capture.set(self.cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if self.fps:
            self.capture.set(self.cv2.CAP_PROP_FPS, self.fps)
        print(
            f"vision camera opened: source={self.source} "
            f"size={self.width}x{self.height} fps={self.fps or 'default'}",
            flush=True,
        )

    def read(self):
        if self.capture is None or not self.capture.isOpened():
            self.open()
        ok, frame = self.capture.read()
        if not ok:
            self.failures += 1
            if self.failures >= self.max_failures:
                print("vision camera read failed repeatedly; reopening", flush=True)
                self.open()
                self.failures = 0
            return None
        self.failures = 0
        return frame

    def capture_snapshot(self, path: str | Path) -> Path | None:
        frame = self.read()
        if frame is None:
            return None
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        ok = self.cv2.imwrite(str(output), frame)
        return output if ok else None

    def close(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None
