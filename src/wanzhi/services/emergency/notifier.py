from __future__ import annotations

from wanzhi.core.bus import JsonlEventBus
from wanzhi.core.events import Event, EventTypes


class EmergencyNotifier:
    def __init__(self, bus: JsonlEventBus) -> None:
        self.bus = bus

    def notify(self, reason: str, source: str = "vision", payload: dict | None = None) -> None:
        event_payload = {"reason": reason}
        if payload:
            event_payload.update(payload)
        self.bus.emit(
            Event(EventTypes.EMERGENCY_FALL_DETECTED, event_payload, source=source)
        )
