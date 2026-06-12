from __future__ import annotations

from typing import Literal

import numpy as np

from wanzhi.core.frame_shm import SharedMemoryFrameWriter


class SharedMemoryManager:
    """Manage POSIX shared memory for zero-disk camera preview frames."""

    def __init__(
        self,
        name: str,
        width: int,
        height: int,
        channels: int = 3,
        *,
        create: bool = True,
    ) -> None:
        self.name = name
        self.width = width
        self.height = height
        self.channels = channels
        self._writer = SharedMemoryFrameWriter(
            name,
            width=width,
            height=height,
            channels=channels,
            create=create,
        )
        self._owner = create

    @property
    def buffer_size(self) -> int:
        return self.width * self.height * self.channels

    def write(
        self,
        frame: np.ndarray,
        *,
        color_format: Literal["rgb", "bgr"] = "rgb",
    ) -> int:
        if color_format == "bgr":
            import cv2

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return self._writer.write(frame, color_format="rgb")

    def close(self) -> None:
        self._writer.close()

    def unlink(self) -> None:
        if self._owner:
            self._writer.unlink()
