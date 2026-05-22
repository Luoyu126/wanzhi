from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class AudioPlayer:
    def __init__(self, output_device: str = "") -> None:
        self.output_device = output_device

    def play(self, wav_path: str | Path) -> None:
        player = shutil.which("pw-play") or shutil.which("aplay")
        if not player:
            return
        command = [player, str(wav_path)]
        if Path(player).name == "aplay" and self.output_device:
            command = [player, "-D", self.output_device, str(wav_path)]
        subprocess.run(command, check=False)
