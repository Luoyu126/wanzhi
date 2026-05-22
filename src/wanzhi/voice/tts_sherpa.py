from __future__ import annotations

import shutil
import os
import subprocess
from pathlib import Path

from wanzhi.voice.tts_base import TTSBackend, VoiceProfile


class SherpaTTSBackend(TTSBackend):
    def __init__(
        self,
        binary: str,
        models: dict[str, dict],
        project_root: Path,
        num_threads: int = 2,
    ) -> None:
        self.binary = binary
        self.models = models
        self.project_root = project_root
        self.num_threads = num_threads

    def can_synthesize(self, voice: VoiceProfile) -> bool:
        if voice.get("engine") != "sherpa":
            return False
        model = self.models.get(str(voice.get("model", "")))
        if not model:
            return False
        self._ensure_onnxruntime_library()
        return self._required_paths_exist(model)

    def synthesize(self, text: str, voice: VoiceProfile, output_path: Path) -> Path:
        model = self.models.get(str(voice.get("model", "")))
        if not model:
            raise RuntimeError(f"Unknown Sherpa TTS model: {voice.get('model', '')}")
        speaker = voice.get("speaker")
        speed = float(voice.get("speed", 1.0))
        subprocess.run(
            self._python_command(model, text, int(speaker or 0), speed, output_path),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=self._subprocess_env(),
        )
        return output_path

    def _python_command(self, model: dict, text: str, speaker: int, speed: float, output_path: Path) -> list[str]:
        python = self.project_root / ".venv" / "bin" / "python"
        model_type = str(model.get("type", "vits"))
        command = [
            str(python if python.exists() else shutil.which("python3") or "python3"),
            "-m",
            "wanzhi.voice.sherpa_synth",
            "--model-type",
            model_type,
            "--model",
            str(self._path(model["model_path"])),
            "--tokens",
            str(self._path(model["tokens_path"])),
            "--output",
            str(output_path),
            "--text",
            text,
            "--sid",
            str(speaker),
            "--speed",
            str(speed),
            "--num-threads",
            str(self.num_threads),
            "--rule-fsts",
            self._rule_fsts(model),
        ]
        if model_type == "kokoro":
            command.extend(["--voices", str(self._path(model["voices_path"]))])
            command.extend(["--data-dir", str(self._path(model["data_dir"]))])
            command.extend(
                [
                    "--lexicon",
                    ",".join(str(self._path(path)) for path in model.get("lexicon_paths", [])),
                ]
            )
        else:
            if model.get("lexicon_path"):
                command.extend(["--lexicon", str(self._path(model["lexicon_path"]))])
            if model.get("data_dir"):
                command.extend(["--data-dir", str(self._path(model["data_dir"]))])
        return command

    def _rule_fsts(self, model: dict) -> str:
        return ",".join(str(self._path(path)) for path in model.get("rule_fsts", []) if self._path(path).exists())

    def _required_paths_exist(self, model: dict) -> bool:
        required = ["model_path", "tokens_path"]
        if model.get("type") == "kokoro":
            required.extend(["voices_path", "data_dir"])
        return all(self._path(str(model[key])).exists() for key in required if key in model)

    def _path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.project_root / path

    def _resolve_binary(self) -> str | None:
        binary_path = Path(self.binary)
        if binary_path.is_absolute() or len(binary_path.parts) > 1:
            candidate = self._path(self.binary)
            if candidate.exists():
                return str(candidate)
        return shutil.which(self.binary)

    def _subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ)
        src = self.project_root / "src"
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{src}:{existing_pythonpath}" if existing_pythonpath else str(src)
        capi = self._onnxruntime_capi_dir()
        if capi:
            existing = env.get("LD_LIBRARY_PATH", "")
            env["LD_LIBRARY_PATH"] = f"{capi}:{existing}" if existing else str(capi)
        return env

    def _ensure_onnxruntime_library(self) -> None:
        capi = self._onnxruntime_capi_dir()
        if not capi:
            return
        link = capi / "libonnxruntime.so"
        if link.exists() or link.is_symlink():
            return
        targets = sorted(capi.glob("libonnxruntime.so.*"))
        if targets:
            link.symlink_to(targets[-1].name)

    def _onnxruntime_capi_dir(self) -> Path | None:
        venv = self.project_root / ".venv"
        for path in venv.glob("lib/python*/site-packages/onnxruntime/capi"):
            if path.exists():
                return path
        return None
