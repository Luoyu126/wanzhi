from pathlib import Path

from wanzhi.core.config import AppConfig
from wanzhi.voice.pipeline import VoicePipeline


def test_wake_greeting_is_configurable(tmp_path) -> None:
    config = AppConfig(
        data={
            "wake": {"greeting": "我在呢，请说。"},
            "stt": {"provider": "vosk", "model_dir": "models/vosk-model"},
            "llm": {},
            "tts": {},
            "voice": {},
            "settings": {"path": str(tmp_path / "settings.json")},
        },
        root=Path("/home/icenter/wanzhi"),
    )

    assert config.get("wake.greeting") == "我在呢，请说。"
