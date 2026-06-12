from __future__ import annotations

from wanzhi.voice.pipeline import VoicePipeline


class FakeConfig:
    def get(self, key: str, default=None):  # type: ignore[no-untyped-def]
        values = {
            "wake.greeting": "",
            "conversation.followup_turns": 1,
        }
        return values.get(key, default)


class FakeWake:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def wait(self) -> None:
        self.events.append("wake")


class FakeSession:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def reset(self) -> None:
        self.events.append("session_reset")


class FakeSpeech:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.spoken: list[str] = []
        self.unmuted = False

    def wait_until_idle(self, timeout_seconds=None):  # type: ignore[no-untyped-def]
        self.events.append("wait_idle")
        return True

    def speak(self, text: str) -> None:
        self.events.append(f"speak:{text}")
        self.spoken.append(text)

    def unmute(self) -> None:
        self.unmuted = True


class FakeBus:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event) -> None:  # type: ignore[no-untyped-def]
        self.events.append(event)


def test_pipeline_waits_for_speech_idle_before_followup_recording() -> None:
    events: list[str] = []
    pipeline = VoicePipeline.__new__(VoicePipeline)
    pipeline.config = FakeConfig()
    pipeline.wake = FakeWake(events)
    pipeline.session = FakeSession(events)
    pipeline.speech = FakeSpeech(events)
    pipeline._reply_idle_timeout_seconds = 5
    pipeline._post_tts_grace_seconds = 0

    calls = iter([True, False])

    def listen(allow_empty_feedback: bool) -> bool:
        events.append(f"listen:{allow_empty_feedback}")
        return next(calls)

    pipeline._listen_and_reply = listen  # type: ignore[method-assign]

    pipeline.run_once()

    assert events == ["wake", "session_reset", "listen:True", "wait_idle", "listen:False"]


def test_empty_followup_speaks_retry_prompt_once() -> None:
    events: list[str] = []
    pipeline = VoicePipeline.__new__(VoicePipeline)
    pipeline._empty_followup_count = 0
    pipeline._empty_followup_retries = 1
    pipeline._empty_followup_message = "我没听清，可以再说一遍吗？"
    pipeline.speech = FakeSpeech(events)
    pipeline.bus = FakeBus()

    assert pipeline._handle_empty_followup() is True
    assert pipeline.speech.unmuted is True
    assert pipeline.speech.spoken == ["我没听清，可以再说一遍吗？"]
    assert pipeline._handle_empty_followup() is False
