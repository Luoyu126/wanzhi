from __future__ import annotations

from pathlib import Path

from wanzhi.actions.registry import ActionRegistry
from wanzhi.core.bus import JsonlEventBus
from wanzhi.core.config import AppConfig
from wanzhi.core.events import Event, EventTypes
from wanzhi.voice.llm_ollama import OllamaClient
from wanzhi.voice.router import IntentRouter
from wanzhi.voice.audio_player import AudioPlayer
from wanzhi.voice.speech_queue import SpeechQueue
from wanzhi.voice.stt_sherpa import SherpaSTT
from wanzhi.voice.stt_vosk import VoskSTT
from wanzhi.voice.tts_manager import TTSManager
from wanzhi.voice.vad import SpeechRecorder
from wanzhi.voice.wake import WakeWordDetector


class VoicePipeline:
    def __init__(self, config: AppConfig, bus: JsonlEventBus) -> None:
        self.config = config
        self.bus = bus
        self.router = IntentRouter()
        self.wake = WakeWordDetector(
            keyword=str(config.get("wake_word", "你好，小丸子")),
            model_path=config.root / "models" / "wakeword" / "wanzhi.onnx",
            vosk_model_dir=config.path("wake.vosk_model_dir", "models/vosk-model"),
            sample_rate=int(config.get("wake.sample_rate", config.get("stt.sample_rate", 16000))),
            device_index=config.get("wake.device_index"),
            device_name=config.get("wake.device_name"),
            fuzzy_threshold=float(config.get("wake.fuzzy_threshold", 0.72)),
        )
        self.recorder = SpeechRecorder(
            sample_rate=int(config.get("stt.sample_rate", 16000)),
            device_index=config.get("stt.device_index"),
            device_name=config.get("stt.device_name", config.get("wake.device_name")),
        )
        self.stt = self._build_stt()
        self.llm = OllamaClient(
            host=str(config.get("llm.host", "http://127.0.0.1:11434")),
            model=str(config.get("llm.model", "qwen2.5:1.5b-instruct")),
            timeout_seconds=int(config.get("llm.timeout_seconds", 30)),
        )
        self.tts = TTSManager(config)
        self.speech = SpeechQueue(
            tts=self.tts,
            player=AudioPlayer(str(config.get("tts.output_device", ""))),
        )
        self.actions = ActionRegistry(config=config, bus=bus, tts=self.tts)

    def _build_stt(self) -> SherpaSTT | VoskSTT:
        provider = str(self.config.get("stt.provider", "sherpa-onnx"))
        fallback_text = str(self.config.get("stt.fallback_text", ""))
        if provider == "vosk":
            return VoskSTT(
                model_dir=self.config.path("stt.model_dir", "models/vosk-model"),
                fallback_text=fallback_text,
            )
        return SherpaSTT(
            model_dir=self.config.path("stt.model_dir"),
            fallback_text=fallback_text,
        )

    def run_once(self) -> None:
        self.wake.wait()
        greeting = str(self.config.get("wake.greeting", "我在呢，请说。")).strip()
        if greeting:
            self.bus.emit(Event(EventTypes.VOICE_AWAKE, {"text": greeting}, source="voice"))
            self.speech.speak(greeting)
        self._listen_and_reply(allow_empty_feedback=True)

        followup_turns = int(self.config.get("conversation.followup_turns", 3))
        for _ in range(followup_turns):
            if not self._listen_and_reply(allow_empty_feedback=False):
                break

    def _listen_and_reply(self, allow_empty_feedback: bool) -> bool:
        self.bus.emit(Event(EventTypes.VOICE_LISTENING, source="voice"))
        wav_path = self.recorder.record_once()
        try:
            text = self.stt.transcribe_file(Path(wav_path))
        finally:
            Path(wav_path).unlink(missing_ok=True)

        print(f"识别文本：{text or '<empty>'}", flush=True)
        if not text.strip() and not allow_empty_feedback:
            print("连续对话：没有听到新内容，回到待机。", flush=True)
            return False
        intent = self.router.parse(text)
        print(f"识别意图：{intent.name} {intent.slots}", flush=True)
        reply = self.actions.handle(intent)
        if reply is None:
            reply = self._chat_reply(text)

        print(f"回复文本：{reply}", flush=True)
        self.bus.emit(Event(EventTypes.VOICE_SPEAKING, {"text": reply}, source="voice"))
        self.speech.speak(reply)
        return intent.name != "goodbye"

    def _chat_reply(self, text: str) -> str:
        if not text:
            return "我在呢，你可以再说一遍。"
        try:
            reply = self.llm.generate(f"你是养老陪护助手丸智，请用温柔、简短的中文回答：{text}")
            return reply or "我听到了，不过还没想好怎么回答。你可以再说具体一点。"
        except Exception:
            return f"我听到了，你刚才说的是：{text}。本地对话模型暂时不可用，但基础语音指令还可以继续使用。"
