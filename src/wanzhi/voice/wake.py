from __future__ import annotations

import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

from wanzhi.core.timing import log_timing, now_seconds


CONFUSABLES = str.maketrans(
    {
        "妳": "你",
        "您": "你",
        "要": "好",
        "号": "好",
        "丸": "丸",
        "玩": "丸",
        "弯": "丸",
        "湾": "丸",
        "完": "丸",
        "碗": "丸",
        "圆": "丸",
        "园": "丸",
        "元": "丸",
        "仔": "子",
        "纸": "子",
        "紫": "子",
        "字": "子",
    }
)

WAKE_ALIASES = (
    "你好小丸子",
    "您好小丸子",
    "你好小玩子",
    "你好小弯子",
    "你好小圆子",
    "你好小丸纸",
    "你好小丸仔",
    "你要小丸子",
    "你好丸子",
    "小丸子",
)

WAKE_GRAMMAR = (
    "你 好 小 丸 子",
    "您 好 小 丸 子",
    "你 好 小 丸",
    "你 好 丸 子",
    "小 丸 子",
    "小 丸",
    "[unk]",
)


class WakeWordDetector:
    def __init__(
        self,
        keyword: str,
        model_path: Path | None = None,
        vosk_model_dir: Path | None = None,
        sample_rate: int = 16000,
        device_index: int | None = None,
        device_name: str | None = None,
        fuzzy_threshold: float = 0.72,
        chunk_size: int = 4000,
    ) -> None:
        self.keyword = keyword
        self.model_path = model_path
        self.vosk_model_dir = vosk_model_dir
        self.sample_rate = sample_rate
        self.device_index = device_index
        self.device_name = device_name
        self.fuzzy_threshold = fuzzy_threshold
        self.chunk_size = chunk_size
        self._vosk_model = None

    def preload(self) -> bool:
        if not self.vosk_model_dir or not self.vosk_model_dir.exists():
            return False

        from vosk import Model

        if self._vosk_model is None:
            started = now_seconds()
            self._vosk_model = Model(str(self.vosk_model_dir))
            log_timing("wake.vosk.preload", started, model_dir=self.vosk_model_dir)
        return True

    def wait(self) -> None:
        if self.vosk_model_dir and self.vosk_model_dir.exists():
            self._wait_with_vosk()
            return

        # Keep openWakeWord as a future custom-model path when wanzhi.onnx exists.
        if self.model_path and self.model_path.exists():
            print(f"Wake word model ready: {self.model_path}")
        time.sleep(1)

    def matches(self, text: str) -> bool:
        return matches_wake_word(text, self.keyword, threshold=self.fuzzy_threshold)

    def _wait_with_vosk(self) -> None:
        import pyaudio
        from vosk import KaldiRecognizer

        self.preload()

        audio = pyaudio.PyAudio()
        device_index, device_label = self._resolve_input_device(audio)
        recognizer = KaldiRecognizer(
            self._vosk_model,
            self.sample_rate,
            json.dumps(list(WAKE_GRAMMAR), ensure_ascii=False),
        )
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=self.chunk_size,
        )
        print(f"等待唤醒词：{self.keyword} (mic={device_index}, {device_label})", flush=True)
        try:
            while True:
                chunk = stream.read(self.chunk_size, exception_on_overflow=False)
                if recognizer.AcceptWaveform(chunk):
                    text = _extract_text(recognizer.Result())
                else:
                    text = _extract_text(recognizer.PartialResult(), key="partial")
                if text and self.matches(text):
                    print(f"唤醒成功：{text}", flush=True)
                    return
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()

    def _resolve_input_device(self, audio) -> tuple[int | None, str]:
        if self.device_index is not None:
            info = audio.get_device_info_by_index(int(self.device_index))
            return int(self.device_index), str(info.get("name", "configured"))
        if not self.device_name:
            return None, "default"
        for index in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(index)
            name = str(info.get("name", ""))
            if self.device_name in name and int(info.get("maxInputChannels", 0)) > 0:
                return index, name
        return None, f"default (preferred {self.device_name!r} not found)"


def matches_wake_word(text: str, keyword: str = "你好，小丸子", threshold: float = 0.72) -> bool:
    normalized_text = normalize_wake_text(text)
    normalized_keyword = normalize_wake_text(keyword)
    if not normalized_text:
        return False

    aliases = {normalize_wake_text(alias) for alias in WAKE_ALIASES}
    aliases.add(normalized_keyword)
    if any(alias and alias in normalized_text for alias in aliases):
        return True

    has_greeting = any(part in normalized_text for part in ("你好", "你好", "哈喽"))
    has_name = any(part in normalized_text for part in ("小丸子", "小丸", "丸子"))
    if has_greeting and has_name:
        return True

    return _best_similarity(normalized_text, normalized_keyword) >= threshold


def normalize_wake_text(text: str) -> str:
    compact = re.sub(r"[\s,，。.!！?？、：:；;\"'“”‘’\-]+", "", text.strip().lower())
    return compact.translate(CONFUSABLES)


def _best_similarity(text: str, target: str) -> float:
    if not text or not target:
        return 0.0
    if len(text) <= len(target) + 2:
        return SequenceMatcher(None, text, target).ratio()
    best = 0.0
    for size in range(max(2, len(target) - 2), len(target) + 3):
        for start in range(0, max(1, len(text) - size + 1)):
            window = text[start : start + size]
            best = max(best, SequenceMatcher(None, window, target).ratio())
    return best


def _extract_text(result_json: str, key: str = "text") -> str:
    try:
        return str(json.loads(result_json).get(key) or "")
    except json.JSONDecodeError:
        return ""
