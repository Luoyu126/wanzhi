from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import yaml

from wanzhi.core.config import AppConfig
from wanzhi.core.settings import SettingsStore
from wanzhi.core.timing import log_timing, now_seconds
from wanzhi.voice.audio_player import AudioPlayer
from wanzhi.voice.tts_aliyun import AliyunTTSBackend
from wanzhi.voice.tts_base import TTSBackend, VoiceProfile
from wanzhi.voice.tts_piper import EspeakFallbackBackend, PiperTTSBackend
from wanzhi.voice.tts_sherpa import SherpaTTSBackend
from wanzhi.voice.voice_matcher import resolve_voice_id


class TTSManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.voices_file = config.path("voice.profiles_file", "config/voices.yaml")
        self.voices = self._load_voices()
        self.default_voice = str(config.get("voice.default", "default_soft"))
        self.settings = SettingsStore(config.path("settings.path", "data/settings.json"))
        self.cache_dir = config.path("tts.cache_dir", "data/tts-cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.player = AudioPlayer(str(config.get("tts.output_device", "")))
        self.backends: list[TTSBackend] = [
            AliyunTTSBackend(config),
            SherpaTTSBackend(
                binary=str(config.get("tts.sherpa_binary", "sherpa-onnx-offline-tts")),
                models=dict(config.get("tts.sherpa_models", {}) or {}),
                project_root=config.root,
                num_threads=int(config.get("tts.num_threads", 2)),
            ),
            PiperTTSBackend(
                binary=str(config.get("tts.binary", "piper")),
                project_root=config.root,
            ),
            EspeakFallbackBackend(),
        ]

    def current_voice_id(self) -> str:
        return str(self.settings.get("voice_id", self.default_voice))

    def set_voice(self, voice_id: str) -> None:
        if voice_id not in self.voices:
            raise KeyError(f"Unknown voice_id: {voice_id}")
        self.settings.set("voice_id", voice_id)

    def describe_voice(self, voice_id: str) -> str:
        voice = dict(self.voices.get(voice_id) or {})
        label = str(voice.get("label") or voice_id)
        aliyun_voice = voice.get("aliyun_voice")
        if str(self.config.get("tts.provider", "")).lower() == "aliyun" and aliyun_voice:
            return f"{label}（阿里云角色 {aliyun_voice}）"
        return label

    def resolve_requested_voice(self, text: str) -> str | None:
        return resolve_voice_id(text, available_voice_ids=set(self.voices))

    def speak(self, text: str, voice_id: str | None = None) -> None:
        wav_path = self.synthesize(text, voice_id)
        self.player.play(wav_path)

    def prewarm(self) -> None:
        for backend in self.backends:
            prewarm = getattr(backend, "prewarm", None)
            if not callable(prewarm):
                continue
            started = now_seconds()
            try:
                prewarm()
                log_timing("tts.prewarm", started, backend=backend.__class__.__name__, success=True)
            except Exception as exc:
                log_timing(
                    "tts.prewarm",
                    started,
                    backend=backend.__class__.__name__,
                    success=False,
                    error=exc.__class__.__name__,
                )

    def synthesize(self, text: str, voice_id: str | None = None, use_cache: bool = True) -> Path:
        synth_started = now_seconds()
        selected_voice_id = voice_id or self.current_voice_id()
        voice = dict(self.voices.get(selected_voice_id) or self.voices.get(self.default_voice) or {})
        if not voice:
            voice = {"engine": "espeak"}
        cache_path = self._cache_path(text, selected_voice_id, voice)
        if use_cache and cache_path.exists():
            log_timing(
                "tts.synthesize",
                synth_started,
                voice_id=selected_voice_id,
                cache_hit=True,
                chars=len(text),
            )
            return cache_path

        for backend in self.backends:
            if not backend.can_synthesize(voice):
                continue
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                backend_started = now_seconds()
                backend.synthesize(text, voice, tmp_path)
                log_timing(
                    "tts.backend",
                    backend_started,
                    backend=backend.__class__.__name__,
                    success=True,
                    chars=len(text),
                )
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path.replace(cache_path)
                log_timing(
                    "tts.synthesize",
                    synth_started,
                    voice_id=selected_voice_id,
                    cache_hit=False,
                    backend=backend.__class__.__name__,
                    chars=len(text),
                )
                return cache_path
            except Exception as exc:
                log_timing(
                    "tts.backend",
                    backend_started,
                    backend=backend.__class__.__name__,
                    success=False,
                    error=exc.__class__.__name__,
                    chars=len(text),
                )
                print(f"TTS backend {backend.__class__.__name__} failed: {exc}", flush=True)
                tmp_path.unlink(missing_ok=True)
                continue
        raise RuntimeError("No TTS backend could synthesize speech")

    def describe_voices(self) -> str:
        labels = {key: value.get("label", key) for key, value in self.voices.items()}
        return json.dumps(labels, ensure_ascii=False)

    def _load_voices(self) -> dict[str, VoiceProfile]:
        if not self.voices_file.exists():
            return {}
        with self.voices_file.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return dict(data.get("voices") or {})

    def _cache_path(self, text: str, voice_id: str, voice: dict[str, Any]) -> Path:
        key_data = {
            "text": text,
            "voice_id": voice_id,
            "provider": self.config.get("tts.provider", ""),
            "engine": voice.get("engine"),
            "model": voice.get("model") or voice.get("model_path"),
            "aliyun_voice": voice.get("aliyun_voice") or self.config.get("tts.aliyun.voice", ""),
            "speaker": voice.get("speaker"),
            "speed": voice.get("speed"),
            "length_scale": voice.get("length_scale"),
        }
        digest = hashlib.sha256(json.dumps(key_data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return self.cache_dir / f"{voice_id}-{digest[:16]}.wav"
