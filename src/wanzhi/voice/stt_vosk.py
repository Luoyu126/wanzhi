from __future__ import annotations

import json
import wave
from pathlib import Path

from wanzhi.core.timing import log_timing, now_seconds


class VoskSTT:
    def __init__(self, model_dir: Path, fallback_text: str = "") -> None:
        self.model_dir = model_dir
        self.fallback_text = fallback_text
        self._model = None

    def preload(self) -> bool:
        try:
            from vosk import Model
        except ImportError:
            return False

        if not self.model_dir.exists():
            return False

        if self._model is None:
            started = now_seconds()
            self._model = Model(str(self.model_dir))
            log_timing("stt.vosk.preload", started, model_dir=self.model_dir)
        return True

    def transcribe_file(self, wav_path: Path) -> str:
        try:
            from vosk import KaldiRecognizer, Model
        except ImportError:
            return self.fallback_text

        if not self.model_dir.exists():
            return self.fallback_text

        if self._model is None:
            started = now_seconds()
            self._model = Model(str(self.model_dir))
            log_timing("stt.vosk.preload", started, model_dir=self.model_dir)

        started = now_seconds()
        with wave.open(str(wav_path), "rb") as wave_file:
            recognizer = KaldiRecognizer(self._model, wave_file.getframerate())
            while True:
                data = wave_file.readframes(4000)
                if not data:
                    break
                recognizer.AcceptWaveform(data)
            result = json.loads(recognizer.FinalResult())
            text = str(result.get("text") or self.fallback_text).strip()
        log_timing("stt.vosk.transcribe", started, chars=len(text))
        return text
