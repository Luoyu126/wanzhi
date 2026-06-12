from wanzhi.ui.app import emergency_display_message, voice_speaking_should_take_focus


def test_emergency_display_message_maps_distress_reasons() -> None:
    assert emergency_display_message({"reason": "hand_raise_sos"}) == "检测到举手呼救"
    assert emergency_display_message({"reason": "arm_wave_sos"}) == "检测到挥手求救"
    assert emergency_display_message({"reason": "abnormal_struggle"}) == "检测到异常挣扎"


def test_emergency_display_message_preserves_voice_reason() -> None:
    assert emergency_display_message({"reason": "救命"}) == "救命"


def test_voice_speaking_does_not_steal_tool_screen_focus() -> None:
    assert voice_speaking_should_take_focus("medication") is False
    assert voice_speaking_should_take_focus("camera") is False
    assert voice_speaking_should_take_focus("face") is True
