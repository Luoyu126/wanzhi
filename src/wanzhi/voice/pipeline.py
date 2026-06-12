from __future__ import annotations

import threading
import time
from pathlib import Path

from wanzhi.actions.registry import ActionRegistry
from wanzhi.core.bus import EventBus
from wanzhi.core.config import AppConfig
from wanzhi.core.events import Event, EventTypes
from wanzhi.core.timing import log_timing, now_seconds
from wanzhi.voice.agent import VoiceAgent
from wanzhi.voice.audio_player import AudioPlayer
from wanzhi.voice.llm_llamacpp import LlamaCppClient
from wanzhi.voice.llm_ollama import OllamaClient
from wanzhi.voice.router import IntentRouter
from wanzhi.voice.session import VoiceSession
from wanzhi.voice.speech_queue import SpeechQueue
from wanzhi.voice.stt_sherpa import SherpaSTT
from wanzhi.voice.stt_vosk import VoskSTT
from wanzhi.voice.tts_manager import TTSManager
from wanzhi.voice.vad import SpeechRecorder
from wanzhi.voice.wake import WakeWordDetector


class VoicePipeline:
    def __init__(self, config: AppConfig, bus: EventBus) -> None:
        self.config = config
        self.bus = bus
        self.router = IntentRouter()
        self.session = VoiceSession(max_messages=int(config.get("conversation.max_context_messages", 24)))
        self._empty_followup_count = 0
        self._empty_followup_retries = int(config.get("conversation.empty_followup_retries", 1))
        self._reply_idle_timeout_seconds = float(config.get("conversation.reply_idle_timeout_seconds", 30))
        self._post_tts_grace_seconds = float(config.get("conversation.post_tts_grace_seconds", 0.25))
        self._empty_followup_message = str(
            config.get("conversation.empty_followup_message", "我没听清，可以再说一遍吗？")
        )
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
        self._prewarm_stt()
        self.llm_provider = str(config.get("llm.provider", "llama-cpp"))
        self.llm = self._build_llm()
        self.llm_ready = self._ensure_llm_ready()
        self.tts = TTSManager(config)
        self.speech = SpeechQueue(
            tts=self.tts,
            player=AudioPlayer(str(config.get("tts.output_device", ""))),
        )
        self.actions = ActionRegistry(config=config, bus=bus, tts=self.tts)
        self.agent = VoiceAgent(
            llm=self.llm,
            tool_executor=self.actions.execute_tool,
            max_steps=int(config.get("llm.max_react_steps", 4)),
        ) if isinstance(self.llm, LlamaCppClient) else None
        self._emergency_message = str(
            config.get("alerts.voice_message", "检测到跌倒，正在为您呼叫紧急联系人。")
        )
        self._llm_unavailable_message = str(
            config.get(
                "llm.unavailable_message",
                "系统核心正在启动中，请稍后。",
            )
        )
        self._start_background_prewarm()

    def _ensure_llm_ready(self) -> bool:
        if not isinstance(self.llm, LlamaCppClient):
            return True
        wait_started = now_seconds()
        self.bus.emit(
            Event(
                EventTypes.LLM_LOADING,
                {"text": "本地对话核心正在准备中，请稍后。", "ready": False},
                source="voice",
            )
        )
        ready = self.llm.wait_for_ready()
        log_timing("llm.wait_ready", wait_started, ready=ready, socket=self.llm.socket_path)
        if ready:
            print(f"LLM daemon ready socket={self.llm.socket_path}", flush=True)
            self.bus.emit(
                Event(
                    EventTypes.LLM_READY,
                    {"text": "本地对话核心已准备好。", "ready": True},
                    source="voice",
                )
            )
        else:
            print(
                f"LLM daemon not ready after startup wait socket={self.llm.socket_path}",
                flush=True,
            )
        return ready

    def _prewarm_stt(self) -> None:
        if not bool(self.config.get("voice.prewarm", True)):
            return
        preload = getattr(self.stt, "preload", None)
        if not callable(preload):
            return
        started = now_seconds()
        try:
            loaded = bool(preload())
            log_timing("voice.prewarm.stt", started, success=loaded)
        except Exception as exc:
            log_timing("voice.prewarm.stt", started, success=False, error=exc.__class__.__name__)

    def _start_background_prewarm(self) -> None:
        if not bool(self.config.get("voice.prewarm", True)):
            return
        thread = threading.Thread(target=self._prewarm_background, name="wanzhi-voice-prewarm", daemon=True)
        thread.start()

    def _prewarm_background(self) -> None:
        started = now_seconds()
        try:
            self.tts.prewarm()
            log_timing("voice.prewarm.background", started, success=True)
        except Exception as exc:
            log_timing("voice.prewarm.background", started, success=False, error=exc.__class__.__name__)

    def handle_emergency_alert(self, event: Event) -> None:
        self.speech.interrupt()
        self.speech.unmute()
        self.bus.emit(event)
        self.bus.emit(
            Event(
                EventTypes.VOICE_SPEAKING,
                {"text": self._emergency_message, "emoji": ""},
                source="voice",
            )
        )
        self.speech.speak(self._emergency_message)
        print(f"vision emergency alert handled: {event.payload}", flush=True)

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

    def _build_llm(self) -> LlamaCppClient | OllamaClient:
        if self.llm_provider == "ollama":
            return OllamaClient(
                host=str(self.config.get("llm.host", "http://127.0.0.1:11434")),
                model=str(self.config.get("llm.model", "qwen2.5:1.5b-instruct")),
                timeout_seconds=int(self.config.get("llm.timeout_seconds", 30)),
            )
        return LlamaCppClient(
            model_path=self.config.path("llm.model_path", "models/llm/qwen2.5-3b-instruct-q4_k_m.gguf"),
            socket_path=str(self.config.get("llm.socket_path", "/run/wanzhi-llm/llm.sock")),
            n_ctx=int(self.config.get("llm.n_ctx", 4096)),
            n_threads=int(self.config.get("llm.n_threads", 4)),
            n_gpu_layers=int(self.config.get("llm.n_gpu_layers", 0)),
            use_mlock=bool(self.config.get("llm.use_mlock", True)),
            temperature=float(self.config.get("llm.temperature", 0.4)),
            max_tokens=int(self.config.get("llm.max_tokens", 160)),
            timeout_seconds=int(self.config.get("llm.timeout_seconds", 30)),
            startup_wait_seconds=float(self.config.get("llm.startup_wait_seconds", 5)),
        )

    def run_once(self) -> None:
        wait_started = now_seconds()
        self.wake.wait()
        log_timing("voice.wake_wait", wait_started)
        self.session.reset()
        self._empty_followup_count = 0
        greeting = str(self.config.get("wake.greeting", "我在呢，请说。")).strip()
        if greeting:
            self.bus.emit(Event(EventTypes.VOICE_AWAKE, {"text": greeting}, source="voice"))
            self.speech.speak(greeting)
        if not self._listen_and_reply(allow_empty_feedback=True):
            self._wait_for_reply_idle()
            return

        followup_turns = int(self.config.get("conversation.followup_turns", 3))
        for _ in range(followup_turns):
            if not self._wait_for_reply_idle():
                break
            if not self._listen_and_reply(allow_empty_feedback=False):
                break

    def _wait_for_reply_idle(self) -> bool:
        started = now_seconds()
        idle = self.speech.wait_until_idle(timeout_seconds=self._reply_idle_timeout_seconds)
        log_timing("voice.wait_speech_idle", started, success=idle)
        if idle and self._post_tts_grace_seconds > 0:
            time.sleep(self._post_tts_grace_seconds)
        return idle

    def _listen_and_reply(self, allow_empty_feedback: bool) -> bool:
        turn_started = now_seconds()
        self.bus.emit(Event(EventTypes.VOICE_LISTENING, source="voice"))
        record_started = now_seconds()
        wav_path = self.recorder.record_once()
        log_timing("voice.record", record_started)
        stt_started = now_seconds()
        try:
            text = self.stt.transcribe_file(Path(wav_path))
        finally:
            Path(wav_path).unlink(missing_ok=True)
        log_timing("voice.stt", stt_started, chars=len(text))

        print(f"识别文本：{text or '<empty>'}", flush=True)
        if text.strip():
            self._empty_followup_count = 0
            self.bus.emit(Event(EventTypes.VOICE_TRANSCRIBED, {"text": text}, source="voice"))
        elif allow_empty_feedback:
            reply_started = now_seconds()
            result = self._legacy_reply(text)
            log_timing("voice.reply", reply_started, mode="legacy_empty", continue_session=result)
            log_timing("voice.turn", turn_started, outcome="legacy_empty", continue_session=result)
            return result
        if not text.strip() and not allow_empty_feedback:
            print("连续对话：没有听到新内容，回到待机。", flush=True)
            result = self._handle_empty_followup()
            log_timing("voice.turn", turn_started, outcome="empty_followup", continue_session=result)
            return result

        local_intent = self.router.parse(text)
        if local_intent.name == "change_voice":
            reply_started = now_seconds()
            result = self._legacy_reply(text)
            log_timing("voice.reply", reply_started, mode="local_change_voice", continue_session=result)
            log_timing("voice.turn", turn_started, outcome="local_change_voice", continue_session=result)
            return result

        reply_started = now_seconds()
        if self.agent is not None:
            result = self._agent_reply(text, self.session)
            log_timing("voice.reply", reply_started, mode="agent", continue_session=result)
        else:
            result = self._legacy_reply(text)
            log_timing("voice.reply", reply_started, mode="legacy", continue_session=result)
        log_timing("voice.turn", turn_started, outcome="replied", continue_session=result)
        return result

    def _reply_llm_unavailable(self) -> bool:
        reply = self._llm_unavailable_message
        print(f"回复文本：{reply}", flush=True)
        self.speech.unmute()
        self.bus.emit(
            Event(
                EventTypes.VOICE_SPEAKING,
                {"text": reply, "emoji": ""},
                source="voice",
            )
        )
        self.speech.speak(reply)
        return True

    def _handle_empty_followup(self) -> bool:
        if self._empty_followup_count >= self._empty_followup_retries:
            return False
        self._empty_followup_count += 1
        reply = self._empty_followup_message
        print(f"回复文本：{reply}", flush=True)
        self.speech.unmute()
        self.bus.emit(
            Event(
                EventTypes.VOICE_SPEAKING,
                {"text": reply, "emoji": ""},
                source="voice",
            )
        )
        self.speech.speak(reply)
        return True

    def _legacy_reply(self, text: str) -> bool:
        intent = self.router.parse(text)
        print(f"识别意图：{intent.name} {intent.slots}", flush=True)
        reply = self.actions.handle(intent)
        if reply is None:
            reply = self._chat_reply(text)

        print(f"回复文本：{reply}", flush=True)
        self.speech.unmute()
        self.bus.emit(
            Event(
                EventTypes.VOICE_SPEAKING,
                {"text": reply, "emoji": self._fallback_emoji(reply)},
                source="voice",
            )
        )
        self.speech.speak(reply)
        return intent.name != "goodbye"

    def _on_agent_sentence(self, spoken_parts: list[str], sentence: str) -> None:
        spoken_parts.append(sentence)
        self.speech.unmute()
        self.speech.enqueue_sentence(sentence)

    def _agent_reply(self, text: str, session: VoiceSession) -> bool:
        if isinstance(self.llm, LlamaCppClient) and not self.llm_ready:
            health_started = now_seconds()
            healthy = self.llm.check_health()
            log_timing("llm.recheck_ready", health_started, ready=healthy)
            if not healthy:
                return self._reply_llm_unavailable()
        self.speech.unmute()
        spoken_parts: list[str] = []
        agent_started = now_seconds()
        try:
            turn = self.agent.run_turn_streaming(
                text,
                history=session.snapshot(),
                on_sentence=lambda sentence: self._on_agent_sentence(spoken_parts, sentence),
                mute_on_tool=self.speech.mute,
            )
        except (ConnectionError, RuntimeError, OSError) as exc:
            print(f"LLM daemon unavailable，回退提示：{exc}", flush=True)
            self.llm_ready = False
            return self._reply_llm_unavailable()
        except FileNotFoundError as exc:
            print(f"本地 llama.cpp 模型不可用，回退到基础语音指令：{exc}", flush=True)
            return self._legacy_reply(text)
        log_timing("voice.agent", agent_started, spoken_sentences=len(spoken_parts), end_session=turn.end_session)
        self.llm_ready = True
        session.update_from_turn(turn)
        reply = turn.final_reply or "".join(spoken_parts) or "我在呢，你可以再说具体一点。"
        print(f"回复文本：{reply}", flush=True)
        self.bus.emit(
            Event(
                EventTypes.VOICE_SPEAKING,
                {"text": reply, "emoji": turn.suggested_emoji},
                source="voice",
            )
        )
        if not spoken_parts:
            self.speech.speak(reply)
        return not turn.end_session

    def _chat_reply(self, text: str) -> str:
        if not text:
            return "我在呢，你可以再说一遍。"
        if isinstance(self.llm, LlamaCppClient) and not self.llm_ready and not self.llm.check_health():
            return self._llm_unavailable_message
        try:
            if isinstance(self.llm, OllamaClient):
                reply = self.llm.generate(f"你是养老陪护助手丸智，请用温柔、简短的中文回答：{text}")
            else:
                reply = self.llm.generate(f"你是养老陪护助手丸智，请用温柔、简短的中文回答：{text}")
            if isinstance(self.llm, LlamaCppClient):
                self.llm_ready = True
            return reply or "我听到了，不过还没想好怎么回答。你可以再说具体一点。"
        except Exception:
            if isinstance(self.llm, LlamaCppClient):
                self.llm_ready = False
            return f"我听到了，你刚才说的是：{text}。本地对话模型暂时不可用，但基础语音指令还可以继续使用。"

    def _fallback_emoji(self, text: str) -> str:
        return ""
