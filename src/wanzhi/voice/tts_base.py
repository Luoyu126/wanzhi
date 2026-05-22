from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


VoiceProfile = dict[str, Any]


class TTSBackend(ABC):
    @abstractmethod
    def can_synthesize(self, voice: VoiceProfile) -> bool:
        raise NotImplementedError

    @abstractmethod
    def synthesize(self, text: str, voice: VoiceProfile, output_path: Path) -> Path:
        raise NotImplementedError
