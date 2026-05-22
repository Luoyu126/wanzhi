from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from wanzhi.voice.audio_player import AudioPlayer
from wanzhi.voice.tts_base import TTSBackend, VoiceProfile


class PiperTTSBackend(TTSBackend):
    def __init__(self, binary: str, project_root: Path) -> None:
        self.binary = binary
        self.project_root = project_root

    def can_synthesize(self, voice: VoiceProfile) -> bool:
        if voice.get("engine", "piper") != "piper":
            return False
        model_path = self._resolve_path(str(voice.get("model_path", "")))
        return model_path.exists() and self._resolve_binary() is not None

    def synthesize(self, text: str, voice: VoiceProfile, output_path: Path) -> Path:
        binary_path = self._resolve_binary()
        model_path = self._resolve_path(str(voice["model_path"]))
        if not binary_path or not model_path.exists():
            raise RuntimeError("Piper binary or model is unavailable")

        command = [binary_path, "--model", str(model_path), "--output_file", str(output_path)]
        config_path = voice.get("config_path")
        if config_path:
            resolved_config = self._resolve_path(str(config_path))
            if resolved_config.exists():
                command.extend(["--config", str(resolved_config)])
        speaker = voice.get("speaker")
        if speaker is not None:
            command.extend(["--speaker", str(speaker)])
        volume = voice.get("volume")
        if volume is not None:
            command.extend(["--volume", str(volume)])
        subprocess.run(
            command,
            input=text.encode("utf-8"),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return output_path

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.project_root / path

    def _resolve_binary(self) -> str | None:
        binary_path = Path(self.binary)
        if binary_path.is_absolute() or len(binary_path.parts) > 1:
            candidate = self._resolve_path(self.binary)
            if candidate.exists():
                return str(candidate)
        return shutil.which(self.binary)


class EspeakFallbackBackend(TTSBackend):
    def can_synthesize(self, voice: VoiceProfile) -> bool:
        return shutil.which("espeak-ng") is not None

    def synthesize(self, text: str, voice: VoiceProfile, output_path: Path) -> Path:
        espeak = shutil.which("espeak-ng")
        if not espeak:
            raise RuntimeError("espeak-ng is unavailable")
        subprocess.run(
            [espeak, "-v", "zh", "-s", str(voice.get("espeak_speed", 150)), "-w", str(output_path), text],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return output_path


class PiperTTS:
    def __init__(
        self,
        binary: str,
        voices_file: Path,
        default_voice: str,
        project_root: Path,
        output_device: str = "",
    ) -> None:
        self.binary = binary
        self.voices_file = voices_file
        self.default_voice = default_voice
        self.project_root = project_root
        self.output_device = output_device
        self._voices = self._load_voices()
        self._backend = PiperTTSBackend(binary=binary, project_root=project_root)
        self._fallback = EspeakFallbackBackend()
        self._player = AudioPlayer(output_device=output_device)

    def _load_voices(self) -> dict[str, dict[str, Any]]:
        if not self.voices_file.exists():
            return {}
        with self.voices_file.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return dict(data.get("voices") or {})

    def speak(self, text: str, voice_id: str | None = None) -> None:
        voice = self._voices.get(voice_id or self.default_voice)
        if not voice:
            self._speak_fallback(text)
            return
        if not self._backend.can_synthesize(voice):
            self._speak_fallback(text)
            return

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as wav:
            self._backend.synthesize(text, voice, Path(wav.name))
            self._play_wav(wav.name)

    def describe_voices(self) -> str:
        labels = {key: value.get("label", key) for key, value in self._voices.items()}
        return json.dumps(labels, ensure_ascii=False)

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.project_root / path

    def _resolve_binary(self) -> str | None:
        binary_path = Path(self.binary)
        if binary_path.is_absolute() or len(binary_path.parts) > 1:
            candidate = self._resolve_path(self.binary)
            if candidate.exists():
                return str(candidate)
        return shutil.which(self.binary)

    def _play_wav(self, wav_path: str) -> None:
        self._player.play(wav_path)

    def _speak_fallback(self, text: str) -> None:
        if not self._fallback.can_synthesize({}):
            print(text)
            return
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as wav:
            self._fallback.synthesize(text, {}, Path(wav.name))
            self._play_wav(wav.name)
