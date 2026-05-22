from __future__ import annotations

import queue
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from wanzhi.voice.audio_player import AudioPlayer
from wanzhi.voice.tts_manager import TTSManager


SENTENCE_RE = re.compile(r"[^。！？!?；;，,]+[。！？!?；;，,]?")


def split_sentences(text: str) -> list[str]:
    sentences = [match.group(0).strip() for match in SENTENCE_RE.finditer(text) if match.group(0).strip()]
    return sentences or [text.strip()]


@dataclass(frozen=True)
class SpeechTask:
    text: str
    voice_id: str | None = None


class SpeechQueue:
    def __init__(self, tts: TTSManager, player: AudioPlayer) -> None:
        self.tts = tts
        self.player = player
        self._queue: queue.Queue[SpeechTask | None] = queue.Queue()
        self._play_lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, name="wanzhi-speech-queue", daemon=True)
        self._worker.start()

    def speak(self, text: str, voice_id: str | None = None) -> None:
        sentences = split_sentences(text)
        if not sentences:
            return

        first = sentences[0]
        for sentence in sentences[1:]:
            self._queue.put(SpeechTask(sentence, voice_id))

        first_wav = self.tts.synthesize(first, voice_id=voice_id)
        self._play(first_wav)

    def stop(self) -> None:
        self._queue.put(None)

    def _run(self) -> None:
        while True:
            task = self._queue.get()
            if task is None:
                return
            try:
                wav_path: Path = self.tts.synthesize(task.text, voice_id=task.voice_id)
                self._play(wav_path)
            finally:
                self._queue.task_done()

    def _play(self, wav_path: Path) -> None:
        with self._play_lock:
            self.player.play(wav_path)
