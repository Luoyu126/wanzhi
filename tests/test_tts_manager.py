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


def test_tts_manager_profiles_define_aliyun_roles() -> None:
    manager = TTSManager(load_config())

    expected_roles = {
        "default_soft": "ailun",
        "elder_male": "xiaogang",
        "elder_female": "aijia",
        "child_male": "aitong",
        "child_female": "aiying",
    }
    for voice_id, aliyun_voice in expected_roles.items():
        assert manager.voices[voice_id]["engine"] == "aliyun"
        assert manager.voices[voice_id]["aliyun_voice"] == aliyun_voice
