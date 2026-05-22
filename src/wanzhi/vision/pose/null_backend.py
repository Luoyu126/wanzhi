from __future__ import annotations

from typing import Any

from wanzhi.vision.pose.base import PoseResult


class NullPoseEstimator:
    name = "null"

    def estimate(self, frame: Any) -> PoseResult:
        return PoseResult(backend=self.name, metadata={"reason": "pose backend unavailable"})
