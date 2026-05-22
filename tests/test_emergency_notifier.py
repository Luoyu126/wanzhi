from wanzhi.core.bus import JsonlEventBus
from wanzhi.core.events import EventTypes
from wanzhi.services.emergency.notifier import EmergencyNotifier


def test_emergency_notifier_emits_signal_only(tmp_path) -> None:
    bus = JsonlEventBus(tmp_path / "events.jsonl")
    notifier = EmergencyNotifier(bus)

    notifier.notify("fall_detected", payload={"confidence": 0.8})

    events = list(bus.poll_new())
    assert len(events) == 1
    assert events[0].type == EventTypes.EMERGENCY_FALL_DETECTED
    assert events[0].payload["reason"] == "fall_detected"
    assert events[0].payload["confidence"] == 0.8
