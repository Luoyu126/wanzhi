from __future__ import annotations

import json
import queue
import time
from multiprocessing import Queue
from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from .events import Event


@runtime_checkable
class EventBus(Protocol):
    def emit(self, event: Event) -> None: ...

    def poll_new(self) -> Iterable[Event]: ...


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

    def poll_new(self) -> Iterable[Event]:
        while True:
            event = self.poll(timeout=0.0)
            if event is None:
                break
            yield event


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


class ZmqEventBus:
    """ZeroMQ PUSH/PULL event bus over Unix domain sockets (ipc://).

    Emitters (voice, vision) connect PUSH; the UI binds PULL and polls events.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        role: str = "push",
        audit_path: str | Path | None = None,
    ) -> None:
        import zmq

        self.endpoint = endpoint
        self._role = role
        self._audit = JsonlEventBus(audit_path) if audit_path else None
        self._context = zmq.Context.instance()
        if role in {"pull", "bind", "subscriber", "sub"}:
            self._socket = self._context.socket(zmq.PULL)
            path = endpoint.replace("ipc://", "")
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            if Path(path).exists():
                Path(path).unlink(missing_ok=True)
            self._socket.bind(endpoint)
        else:
            self._socket = self._context.socket(zmq.PUSH)
            self._socket.connect(endpoint)

    def emit(self, event: Event) -> None:
        payload = json.dumps(event.to_dict(), ensure_ascii=False)
        self._socket.send_string(payload)
        if self._audit is not None:
            self._audit.emit(event)

    def poll_new(self) -> Iterable[Event]:
        import zmq

        while True:
            try:
                message = self._socket.recv_string(flags=zmq.NOBLOCK)
            except zmq.Again:
                break
            yield Event.from_dict(json.loads(message))

    def close(self) -> None:
        self._socket.close(linger=0)


class CompositeEventBus:
    """Fan-out bus used during migration (e.g. ZMQ + JSONL audit)."""

    def __init__(self, *buses: EventBus) -> None:
        self._buses = buses

    def emit(self, event: Event) -> None:
        for bus in self._buses:
            bus.emit(event)

    def poll_new(self) -> Iterable[Event]:
        primary = self._buses[0]
        yield from primary.poll_new()


def create_event_bus(
    *,
    backend: str = "jsonl",
    log_path: str | Path = "data/events.jsonl",
    zmq_endpoint: str = "ipc:///tmp/wanzhi-events.sock",
    zmq_role: str = "auto",
    audit_jsonl: bool = False,
) -> EventBus:
    backend = backend.lower()
    if backend == "zmq":
        audit = log_path if audit_jsonl else None
        return ZmqEventBus(zmq_endpoint, role=zmq_role, audit_path=audit)
    if backend == "composite":
        return CompositeEventBus(
            ZmqEventBus(zmq_endpoint, role=zmq_role),
            JsonlEventBus(log_path),
        )
    return JsonlEventBus(log_path)


def create_event_bus_from_config(config, *, role: str = "push") -> EventBus:
    backend = str(config.get("events.backend", "zmq"))
    return create_event_bus(
        backend=backend,
        log_path=config.path("events.log_path", "data/events.jsonl"),
        zmq_endpoint=str(config.get("events.zmq_endpoint", "ipc:///tmp/wanzhi-events.sock")),
        zmq_role=role,
        audit_jsonl=bool(config.get("events.audit_jsonl", True)),
    )


def wait_for_subscribers(seconds: float = 0.2) -> None:
    """Give ZeroMQ subscribers time to connect before the first publish."""
    time.sleep(max(seconds, 0.0))
