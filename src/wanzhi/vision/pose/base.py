from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Landmark:
    x: float
    y: float
    visibility: float = 1.0


@dataclass(frozen=True)
class PoseResult:
    landmarks: list[Landmark] = field(default_factory=list)
    backend: str = "none"
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class PoseEstimator(Protocol):
    name: str

    def estimate(self, frame: Any) -> PoseResult:
        raise NotImplementedError
