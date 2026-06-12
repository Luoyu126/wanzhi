from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from wanzhi.core.events import Event, EventTypes


FALL_DETECTED_EVENT = EventTypes.EMERGENCY_FALL_DETECTED


def build_fall_alert_message(*, confidence: float, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"confidence": confidence}
    if extra:
        payload.update(extra)
    return {
        "event": FALL_DETECTED_EVENT,
        "timestamp": int(time.time()),
        "data": payload,
    }


class VisionAlertPublisher:
    """Async ZeroMQ PUB publisher for vision emergency alerts."""

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(target=self._run, name="wanzhi-vision-alerts", daemon=True)
        self._started = threading.Event()
        self._thread.start()
        self._started.wait(timeout=5.0)

    def publish_fall_detected(
        self,
        *,
        confidence: float,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._queue.put(build_fall_alert_message(confidence=confidence, extra=extra))

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=2.0)

    def _run(self) -> None:
        asyncio.run(self._async_main())

    async def _async_main(self) -> None:
        import zmq.asyncio

        context = zmq.asyncio.Context.instance()
        socket = context.socket(zmq.PUB)
        path = self.endpoint.replace("ipc://", "")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if Path(path).exists():
            Path(path).unlink(missing_ok=True)
        socket.bind(self.endpoint)
        await asyncio.sleep(0.2)
        self._started.set()

        while True:
            message = await asyncio.to_thread(self._queue.get)
            if message is None:
                break
            await socket.send_string(json.dumps(message, ensure_ascii=False))
        socket.close(linger=0)


class VisionAlertSubscriber:
    """ZeroMQ SUB subscriber that exposes fall alerts as Event objects."""

    def __init__(self, endpoint: str) -> None:
        import zmq

        self.endpoint = endpoint
        self._context = zmq.Context.instance()
        self._socket = self._context.socket(zmq.SUB)
        self._socket.setsockopt_string(zmq.SUBSCRIBE, "")
        self._socket.connect(endpoint)

    def poll_new(self) -> Iterable[Event]:
        import zmq

        while True:
            try:
                raw = self._socket.recv_string(flags=zmq.NOBLOCK)
            except zmq.Again:
                break
            event = alert_message_to_event(json.loads(raw))
            if event is not None:
                yield event

    def close(self) -> None:
        self._socket.close(linger=0)


def alert_message_to_event(message: dict[str, Any]) -> Event | None:
    event_type = str(message.get("event", ""))
    if event_type != FALL_DETECTED_EVENT:
        return None
    data = dict(message.get("data") or {})
    reason = str(data.pop("reason", "fall_detected"))
    payload = {"reason": reason, **data}
    return Event(event_type, payload, source="vision")
