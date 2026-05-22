from wanzhi.core.config import load_config
from wanzhi.voice.tts_manager import TTSManager


def test_tts_manager_resolves_voice_keywords() -> None:
    manager = TTSManager(load_config())

    assert manager.resolve_requested_voice("换成老爷爷声音") == "elder_male"
    assert manager.resolve_requested_voice("换成小女孩声音") == "child_female"


def test_tts_manager_lists_required_profiles() -> None:
    manager = TTSManager(load_config())

    for voice_id in ["elder_male", "elder_female", "child_male", "child_female", "default_soft"]:
        assert voice_id in manager.voices
