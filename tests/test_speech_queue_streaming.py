import threading

from wanzhi.voice.speech_queue import SpeechQueue, split_sentences


class DummyTTS:
    def synthesize(self, text: str, voice_id=None, use_cache=True):
        from pathlib import Path

        path = Path("/tmp/wanzhi-test.wav")
        path.write_bytes(b"RIFF")
        return path


class FailingOnceTTS:
    def __init__(self) -> None:
        self.calls = 0

    def synthesize(self, text: str, voice_id=None, use_cache=True):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("boom")
        return DummyTTS().synthesize(text, voice_id=voice_id, use_cache=use_cache)


class DummyPlayer:
    def play(self, wav_path) -> None:
        return None

    @property
    def is_playing(self) -> bool:
        return False


class BlockingPlayer:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self._is_playing = False

    def play(self, wav_path) -> None:
        self._is_playing = True
        self.started.set()
        self.release.wait(timeout=1)
        self._is_playing = False

    def stop(self) -> None:
        self.release.set()
        self._is_playing = False

    @property
    def is_playing(self) -> bool:
        return self._is_playing


def test_split_sentences_handles_chinese_punctuation() -> None:
    parts = split_sentences("今天天气很好。记得吃药，别忘记。")
    assert len(parts) == 3
    assert parts[0].endswith("。")
    assert parts[-1].endswith("。")


def test_speech_queue_mute_skips_enqueue() -> None:
    queue = SpeechQueue(tts=DummyTTS(), player=DummyPlayer())
    queue.mute()
    queue.enqueue_sentence("这句不应该播放。")
    assert queue._queue.empty()


def test_speech_queue_wait_until_idle_blocks_until_playback_finishes() -> None:
    player = BlockingPlayer()
    queue = SpeechQueue(tts=DummyTTS(), player=player)

    queue.enqueue_sentence("请稍等一下。")
    assert player.started.wait(timeout=1)
    assert queue.is_busy()

    player.release.set()

    assert queue.wait_until_idle(timeout_seconds=1) is True
    assert not queue.is_busy()
    queue.stop()


def test_speech_queue_survives_tts_failure() -> None:
    tts = FailingOnceTTS()
    queue = SpeechQueue(tts=tts, player=DummyPlayer())

    queue.enqueue_sentence("第一句会失败。")
    assert queue.wait_until_idle(timeout_seconds=1)
    queue.enqueue_sentence("第二句还能播放。")

    assert queue.wait_until_idle(timeout_seconds=1)
    assert tts.calls == 2
    queue.stop()
