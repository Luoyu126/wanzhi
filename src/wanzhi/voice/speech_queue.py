from __future__ import annotations

import queue
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from wanzhi.core.timing import log_timing, now_seconds
from wanzhi.voice.audio_player import AudioPlayer
from wanzhi.voice.tts_manager import TTSManager


SENTENCE_RE = re.compile(r"[^。！？!?；;，,]+[。！？!?；;，,]?")
STREAM_SENTENCE_END = re.compile(r"[。！？!?；;，,]")


def split_sentences(text: str) -> list[str]:
    sentences = [match.group(0).strip() for match in SENTENCE_RE.finditer(text) if match.group(0).strip()]
    return sentences or [text.strip()]


@dataclass(frozen=True)
class SpeechTask:
    text: str
    voice_id: str | None = None
    queued_at: float = 0.0


class SpeechQueue:
    def __init__(self, tts: TTSManager, player: AudioPlayer) -> None:
        self.tts = tts
        self.player = player
        self._queue: queue.Queue[SpeechTask | None] = queue.Queue()
        self._play_lock = threading.Lock()
        self._muted = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._worker = threading.Thread(target=self._run, name="wanzhi-speech-queue", daemon=True)
        self._worker.start()

    def speak(self, text: str, voice_id: str | None = None) -> None:
        sentences = split_sentences(text)
        if not sentences:
            return

        first = sentences[0]
        for sentence in sentences[1:]:
            self.enqueue_sentence(sentence, voice_id=voice_id)

        if self._muted.is_set():
            return
        first_wav = self.tts.synthesize(first, voice_id=voice_id)
        self._play(first_wav)

    def enqueue_sentence(self, text: str, voice_id: str | None = None) -> None:
        cleaned = text.strip()
        if not cleaned or self._muted.is_set():
            return
        self._idle.clear()
        self._queue.put(SpeechTask(cleaned, voice_id, now_seconds()))

    def mute(self) -> None:
        self._muted.set()
        self.clear_pending()

    def unmute(self) -> None:
        self._muted.clear()

    def clear_pending(self) -> None:
        while True:
            try:
                task = self._queue.get_nowait()
            except queue.Empty:
                break
            if task is None:
                self._queue.put(None)
                break
            self._queue.task_done()
        self._mark_idle_if_ready()

    def interrupt(self) -> None:
        """Stop current playback and drop queued speech."""
        self.clear_pending()
        self.player.stop()
        self._mark_idle_if_ready()

    def speak_stream(self, token_iter, voice_id: str | None = None) -> str:
        """Stream LLM tokens into sentence-level TTS chunks."""
        buffer = ""
        full_text = ""
        self.unmute()
        for token in token_iter:
            if self._muted.is_set():
                continue
            buffer += token
            full_text += token
            if STREAM_SENTENCE_END.search(token):
                sentence = buffer.strip()
                if sentence:
                    self.enqueue_sentence(sentence, voice_id=voice_id)
                buffer = ""
        if buffer.strip() and not self._muted.is_set():
            self.enqueue_sentence(buffer.strip(), voice_id=voice_id)
        return full_text.strip()

    def stop(self) -> None:
        self._queue.put(None)

    def is_busy(self) -> bool:
        return self._queue.unfinished_tasks > 0 or self._player_is_playing()

    def wait_until_idle(self, timeout_seconds: float | None = None) -> bool:
        deadline = None if timeout_seconds is None else time.monotonic() + max(0.0, timeout_seconds)
        while self.is_busy():
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return not self.is_busy()
                self._idle.wait(min(remaining, 0.05))
            else:
                self._idle.wait(0.05)
        return True

    def _run(self) -> None:
        while True:
            task = self._queue.get()
            if task is None:
                self._queue.task_done()
                self._mark_idle_if_ready()
                return
            if self._muted.is_set():
                self._queue.task_done()
                continue
            try:
                if task.queued_at:
                    log_timing("speech.queue_wait", task.queued_at, chars=len(task.text))
                wav_path: Path = self.tts.synthesize(task.text, voice_id=task.voice_id)
                self._play(wav_path)
            except Exception as exc:
                log_timing(
                    "speech.task",
                    now_seconds(),
                    success=False,
                    error=exc.__class__.__name__,
                    chars=len(task.text),
                )
                print(f"speech queue task failed: {exc}", flush=True)
            finally:
                self._queue.task_done()
                self._mark_idle_if_ready()

    def _play(self, wav_path: Path) -> None:
        with self._play_lock:
            self.player.play(wav_path)

    def _mark_idle_if_ready(self) -> None:
        if not self.is_busy():
            self._idle.set()

    def _player_is_playing(self) -> bool:
        return bool(getattr(self.player, "is_playing", False))
