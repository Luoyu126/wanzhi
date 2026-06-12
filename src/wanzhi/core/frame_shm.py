from __future__ import annotations

import struct
from dataclasses import dataclass
from multiprocessing import resource_tracker, shared_memory
from typing import Literal

import numpy as np

HEADER_MAGIC = b"WZFH"
HEADER_FORMAT = "<4sQIII4x"  # magic, sequence, width, height, channels
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


@dataclass(frozen=True)
class FrameHeader:
    sequence: int
    width: int
    height: int
    channels: int


def frame_buffer_size(width: int, height: int, channels: int = 3) -> int:
    return HEADER_SIZE + width * height * channels


class SharedMemoryFrameWriter:
    """Write raw RGB frames into a POSIX shared memory segment."""

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
        self._size = frame_buffer_size(width, height, channels)
        self._sequence = 0
        try:
            if create:
                self._shm = shared_memory.SharedMemory(name=name, create=True, size=self._size)
            else:
                self._shm = shared_memory.SharedMemory(name=name, create=False)
        except FileExistsError:
            shared_memory.SharedMemory(name=name).unlink()
            self._shm = shared_memory.SharedMemory(name=name, create=True, size=self._size)

    def write(self, frame: np.ndarray, *, color_format: Literal["rgb", "bgr"] = "rgb") -> int:
        if frame.ndim != 3 or frame.shape[2] != self.channels:
            raise ValueError(f"Expected frame shape (H, W, {self.channels}), got {frame.shape}")
        if frame.shape[0] != self.height or frame.shape[1] != self.width:
            resized = _resize_frame(frame, self.width, self.height)
        else:
            resized = frame

        payload = np.ascontiguousarray(resized, dtype=np.uint8)
        byte_count = self.width * self.height * self.channels
        self._shm.buf[HEADER_SIZE : HEADER_SIZE + byte_count] = payload.tobytes()
        self._sequence += 1
        struct.pack_into(
            HEADER_FORMAT,
            self._shm.buf,
            0,
            HEADER_MAGIC,
            self._sequence,
            self.width,
            self.height,
            self.channels,
        )
        return self._sequence

    def close(self) -> None:
        self._shm.close()

    def unlink(self) -> None:
        tracked_name = getattr(self._shm, "_name", self.name)
        self._shm.unlink()
        resource_tracker.unregister(tracked_name, "shared_memory")


class SharedMemoryFrameReader:
    """Read the latest frame from a shared memory segment."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._last_sequence = 0
        self._shm: shared_memory.SharedMemory | None = None
        self._attach()

    def _attach(self) -> None:
        self._shm = shared_memory.SharedMemory(name=self.name, create=False)
        # Prevent reader processes from unlinking the writer-owned segment on exit.
        tracked_name = getattr(self._shm, "_name", self.name)
        resource_tracker.unregister(tracked_name, "shared_memory")

    def read_if_updated(self) -> tuple[np.ndarray | None, FrameHeader | None]:
        if self._shm is None:
            try:
                self._attach()
            except FileNotFoundError:
                return None, None

        header_bytes = bytes(self._shm.buf[:HEADER_SIZE])
        magic, sequence, width, height, channels = struct.unpack(HEADER_FORMAT, header_bytes)
        if magic != HEADER_MAGIC or sequence == 0:
            return None, None
        if sequence <= self._last_sequence:
            return None, None

        byte_count = width * height * channels
        frame_bytes = bytes(self._shm.buf[HEADER_SIZE : HEADER_SIZE + byte_count])
        frame = np.frombuffer(frame_bytes, dtype=np.uint8).reshape((height, width, channels))
        self._last_sequence = sequence
        return frame.copy(), FrameHeader(sequence=sequence, width=width, height=height, channels=channels)

    def close(self) -> None:
        if self._shm is not None:
            self._shm.close()
            self._shm = None


def _resize_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    import cv2

    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
