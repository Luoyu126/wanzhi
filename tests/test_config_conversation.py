from wanzhi.core.config import load_config


def test_conversation_followup_is_enabled() -> None:
    config = load_config()

    assert config.get("conversation.followup_turns") >= 1
    assert config.get("stt.device_name") == config.get("wake.device_name")


def test_conversation_followup_timing_defaults() -> None:
    config = load_config()

    assert config.get("conversation.max_context_messages") >= 4
    assert config.get("conversation.reply_idle_timeout_seconds") > 0
    assert config.get("conversation.post_tts_grace_seconds") >= 0
    assert config.get("conversation.empty_followup_retries") >= 0
    assert config.get("conversation.empty_followup_message")
