from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

from wanzhi.core.config import AppConfig


class MediaActions:
    """Non-blocking local media playback for music and story streams."""

    def __init__(self, config: AppConfig) -> None:
        self.enabled = bool(config.get("media.enabled", True))
        self.player = str(config.get("media.player", "mpv"))
        self.fallback_player = str(config.get("media.fallback_player", "ffplay"))
        self.start_delay_seconds = float(config.get("media.start_delay_seconds", 1.5))
        self._process: subprocess.Popen | None = None
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def play_after_delay(self, url: str, *, title: str = "", kind: str = "music") -> bool:
        if not self.enabled:
            return False
        if not url.strip():
            return False

        self._cancel_timer()

        def _start() -> None:
            self.play_url(url, title=title, kind=kind)

        timer = threading.Timer(self.start_delay_seconds, _start)
        timer.daemon = True
        with self._lock:
            self._timer = timer
        timer.start()
        return True

    def play_url(self, url: str, *, title: str = "", kind: str = "music") -> bool:
        del title, kind
        if not self.enabled:
            return False
        if not url.strip():
            return False

        player = self._resolve_player()
        if not player:
            return False

        self.stop()
        command = self._build_command(player, url)
        with self._lock:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return True

    def stop(self) -> bool:
        self._cancel_timer()
        with self._lock:
            process = self._process
            self._process = None

        if process is None:
            return False

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.5)
        return True

    def is_playing(self) -> bool:
        with self._lock:
            process = self._process
        return process is not None and process.poll() is None

    def _cancel_timer(self) -> None:
        with self._lock:
            timer = self._timer
            self._timer = None
        if timer is not None:
            timer.cancel()

    def _resolve_player(self) -> str | None:
        for candidate in (self.player, self.fallback_player):
            if not candidate:
                continue
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        return None

    @staticmethod
    def _build_command(player: str, url: str) -> list[str]:
        player_name = Path(player).name
        if player_name == "mpv":
            return [player, "--no-video", "--really-quiet", url]
        if player_name == "ffplay":
            return [player, "-nodisp", "-autoexit", "-loglevel", "quiet", url]
        return [player, url]
