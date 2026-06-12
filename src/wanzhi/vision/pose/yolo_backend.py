from __future__ import annotations

from pathlib import Path
from typing import Any

from wanzhi.vision.fall_detector import FallDetectionConfig
from wanzhi.vision.gesture_detector import GestureDetectionConfig
from wanzhi.vision.pose.base import PoseResult
from wanzhi.vision.pose_analyzer import PoseAnalyzer, PoseAnalyzerConfig


class YoloPoseEstimator:
    name = "yolo"

    def __init__(
        self,
        *,
        model_path: Path,
        min_detection_confidence: float = 0.5,
        fall_config: FallDetectionConfig | None = None,
        gesture_config: GestureDetectionConfig | None = None,
        input_size: int = 640,
    ) -> None:
        self._analyzer = PoseAnalyzer(
            PoseAnalyzerConfig(
                model_path=model_path,
                input_size=input_size,
                min_detection_confidence=min_detection_confidence,
            ),
            fall_config or FallDetectionConfig(),
            gesture_config,
        )

    def estimate(self, frame: Any) -> PoseResult:
        pose, _, _, _ = self._analyzer.analyze(frame)
        return pose

    @property
    def analyzer(self) -> PoseAnalyzer:
        return self._analyzer
