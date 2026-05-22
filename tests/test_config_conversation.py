from wanzhi.core.config import load_config


def test_conversation_followup_is_enabled() -> None:
    config = load_config()

    assert config.get("conversation.followup_turns") >= 1
    assert config.get("stt.device_name") == config.get("wake.device_name")
