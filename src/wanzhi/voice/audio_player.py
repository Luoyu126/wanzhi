from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from wanzhi.core.timing import log_timing, now_seconds


class AudioPlayer:
    def __init__(self, output_device: str = "") -> None:
        self.output_device = output_device
        self._process: subprocess.Popen | None = None

    def play(self, wav_path: str | Path) -> None:
        started = now_seconds()
        self.stop()
        player = shutil.which("aplay") if self.output_device else shutil.which("pw-play")
        player = player or shutil.which("pw-play") or shutil.which("aplay")
        if not player:
            log_timing("audio.play", started, success=False, reason="missing_player")
            return
        command = [player, str(wav_path)]
        if Path(player).name == "aplay" and self.output_device:
            command = [player, "-D", self.output_device, str(wav_path)]
        self._process = subprocess.Popen(command)
        log_timing("audio.play_start", started, player=Path(player).name)
        try:
            self._process.wait()
        finally:
            self._process = None
            log_timing("audio.play", started, success=True, player=Path(player).name)

    def stop(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=0.5)
        self._process = None

    @property
    def is_playing(self) -> bool:
        return self._process is not None and self._process.poll() is None
