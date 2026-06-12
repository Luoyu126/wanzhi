from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class Event:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "wanzhi"
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        return cls(
            type=str(data["type"]),
            payload=dict(data.get("payload") or {}),
            source=str(data.get("source") or "wanzhi"),
            id=str(data.get("id") or uuid4().hex),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
        )


class EventTypes:
    VOICE_AWAKE = "voice.awake"
    VOICE_LISTENING = "voice.listening"
    VOICE_TRANSCRIBED = "voice.transcribed"
    VOICE_SPEAKING = "voice.speaking"
    LLM_LOADING = "llm.loading"
    LLM_READY = "llm.ready"
    UI_SHOW_FACE = "ui.show_face"
    UI_SHOW_CAMERA = "ui.show_camera"
    UI_SHOW_MEDICATION = "ui.show_medication"
    MEDICATION_REMINDER = "medication.reminder"
    MEDICATION_TAKEN = "medication.taken"
    VISION_HEALTH = "vision.health"
    VISION_FALL_SUSPECTED = "vision.fall_suspected"
    EMERGENCY_FALL_DETECTED = "emergency.fall_detected"
    EMERGENCY_TRIGGERED = "emergency.triggered"
