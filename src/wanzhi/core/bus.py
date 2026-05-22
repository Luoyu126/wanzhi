from __future__ import annotations

import json
import queue
from multiprocessing import Queue
from pathlib import Path
from typing import Iterable

from .events import Event


class InMemoryEventBus:
    """Queue-backed bus for development runs where all services share one process."""

    def __init__(self, event_queue: Queue | None = None) -> None:
        self._queue = event_queue or Queue()

    def emit(self, event: Event) -> None:
        self._queue.put(event.to_dict())

    def poll(self, timeout: float = 0.0) -> Event | None:
        try:
            return Event.from_dict(self._queue.get(timeout=timeout))
        except queue.Empty:
            return None


class JsonlEventBus:
    """Append-only event log that separate systemd services can share."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._offset = self.path.stat().st_size

    def emit(self, event: Event) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def poll_new(self) -> Iterable[Event]:
        with self.path.open("r", encoding="utf-8") as fh:
            fh.seek(self._offset)
            for line in fh:
                line = line.strip()
                if line:
                    yield Event.from_dict(json.loads(line))
            self._offset = fh.tell()
