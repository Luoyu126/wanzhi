from wanzhi.actions.registry import ActionRegistry
from wanzhi.core.bus import JsonlEventBus
from wanzhi.core.config import AppConfig
from wanzhi.core.events import EventTypes


def test_execute_tool_show_medication(tmp_path) -> None:
    bus = JsonlEventBus(tmp_path / "events.jsonl")
    config = AppConfig(data={"database": {"path": str(tmp_path / "wanzhi.db")}}, root=tmp_path)
    registry = ActionRegistry(config=config, bus=bus)
    result = registry.execute_tool("show_medication_list", {})
    assert "药" in result.observation
    events = list(bus.poll_new())
    assert events[0].type == EventTypes.UI_SHOW_MEDICATION


def test_execute_tool_switch_ui_screen_vision(tmp_path) -> None:
    bus = JsonlEventBus(tmp_path / "events.jsonl")
    config = AppConfig(data={"database": {"path": str(tmp_path / "wanzhi.db")}}, root=tmp_path)
    registry = ActionRegistry(config=config, bus=bus)
    result = registry.execute_tool("switch_ui_screen", {"target_screen": "vision"})
    assert "摄像头" in result.spoken_reply or "摄像头" in result.observation
    events = list(bus.poll_new())
    assert events[0].type == EventTypes.UI_SHOW_CAMERA


def test_execute_tool_end_conversation(tmp_path) -> None:
    bus = JsonlEventBus(tmp_path / "events.jsonl")
    config = AppConfig(data={"database": {"path": str(tmp_path / "wanzhi.db")}}, root=tmp_path)
    registry = ActionRegistry(config=config, bus=bus)
    result = registry.execute_tool("end_conversation", {})
    assert result.end_session is True
