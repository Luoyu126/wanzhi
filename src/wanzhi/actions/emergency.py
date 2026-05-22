from __future__ import annotations

from wanzhi.core.bus import JsonlEventBus
from wanzhi.core.events import Event, EventTypes


class EmergencyActions:
    def __init__(self, bus: JsonlEventBus) -> None:
        self.bus = bus

    def trigger(self, reason: str) -> str:
        self.bus.emit(
            Event(
                EventTypes.EMERGENCY_TRIGGERED,
                {"reason": reason},
                source="voice",
            )
        )
        return "我已经记录紧急情况，并会在屏幕上显示报警提示。请保持安全。"
