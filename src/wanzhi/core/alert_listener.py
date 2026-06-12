from __future__ import annotations

import threading
from typing import Callable

from wanzhi.core.events import Event
from wanzhi.core.vision_alerts import VisionAlertSubscriber


class VisionAlertListener:
    """Background listener that forwards vision fall alerts to a callback."""

    def __init__(
        self,
        endpoint: str,
        on_alert: Callable[[Event], None],
        poll_interval: float = 0.05,
    ) -> None:
        self._subscriber = VisionAlertSubscriber(endpoint)
        self._on_alert = on_alert
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="wanzhi-alert-listener", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            for event in self._subscriber.poll_new():
                self._on_alert(event)
            self._stop.wait(self._poll_interval)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._subscriber.close()
