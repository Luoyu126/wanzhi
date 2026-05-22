from __future__ import annotations

import math
import time
from dataclasses import dataclass

from wanzhi.vision.pose import Landmark


@dataclass(frozen=True)
class FallDetectionConfig:
    fall_aspect_ratio: float = 1.3
    torso_angle_degrees: float = 55
    hip_shoulder_vertical_ratio: float = 0.15
    min_fall_seconds: float = 1.5
    required_consecutive_frames: int = 6
    cooldown_seconds: float = 30


@dataclass(frozen=True)
class FallDetectionResult:
    status: str
    confidence: float = 0.0
    reason: str = ""
    duration_seconds: float = 0.0
    keypoints_summary: dict | None = None
    should_emit: bool = False


class FallDetector:
    def __init__(self, config: FallDetectionConfig) -> None:
        self.config = config
        self._fall_started_at: float | None = None
        self._consecutive = 0
        self._last_alert_at = 0.0

    def update(self, landmarks: list[Landmark], metadata: dict | None = None) -> FallDetectionResult:
        now = time.monotonic()
        falling, reason, confidence, summary = self._looks_fallen(landmarks)
        if metadata:
            summary.update(metadata)
        if not falling:
            self._fall_started_at = None
            self._consecutive = 0
            return FallDetectionResult(status="normal", keypoints_summary=summary)

        self._consecutive += 1
        self._fall_started_at = self._fall_started_at or now
        duration = now - self._fall_started_at
        old_enough = duration >= self.config.min_fall_seconds
        enough_frames = self._consecutive >= self.config.required_consecutive_frames
        cooled_down = now - self._last_alert_at >= self.config.cooldown_seconds
        if old_enough and enough_frames and cooled_down:
            self._last_alert_at = now
            return FallDetectionResult(
                status="fall",
                confidence=confidence,
                reason=reason,
                duration_seconds=duration,
                keypoints_summary=summary,
                should_emit=True,
            )
        return FallDetectionResult(
            status="suspicious",
            confidence=confidence,
            reason=reason,
            duration_seconds=duration,
            keypoints_summary=summary,
        )

    def _looks_fallen(self, landmarks: list[Landmark]) -> tuple[bool, str, float, dict]:
        visible = [p for p in landmarks if p.visibility >= 0.4]
        summary = {"visible_points": len(visible)}
        if len(visible) < 8:
            return False, "insufficient_keypoints", 0.0, summary

        width = max(point.x for point in visible) - min(point.x for point in visible)
        height = max(point.y for point in visible) - min(point.y for point in visible)
        aspect_fallen = height > 0 and width / height > self.config.fall_aspect_ratio
        aspect_ratio = width / height if height > 0 else 0.0
        summary.update({"width": width, "height": height, "aspect_ratio": aspect_ratio})

        shoulder = _midpoint(landmarks, 11, 12)
        hip = _midpoint(landmarks, 23, 24)
        knee = _midpoint(landmarks, 25, 26)
        if not shoulder or not hip or not knee:
            confidence = min(1.0, aspect_ratio / max(self.config.fall_aspect_ratio, 0.01))
            return aspect_fallen, "wide_body_aspect_ratio", confidence, summary

        torso_angle = abs(math.degrees(math.atan2(hip.y - shoulder.y, hip.x - shoulder.x)))
        vertical_gap = abs(hip.y - shoulder.y)
        compact_torso = vertical_gap < self.config.hip_shoulder_vertical_ratio
        bent_low = torso_angle < self.config.torso_angle_degrees
        summary.update({"torso_angle": torso_angle, "hip_shoulder_vertical_gap": vertical_gap})
        reasons: list[str] = []
        if aspect_fallen:
            reasons.append("wide_body_aspect_ratio")
        if compact_torso and bent_low:
            reasons.extend(["compact_torso", "low_torso_angle"])
        confidence = min(1.0, 0.45 * len(reasons))
        return bool(reasons), ",".join(reasons), confidence, summary


def _midpoint(landmarks: list[Landmark], left: int, right: int) -> Landmark | None:
    if len(landmarks) <= max(left, right):
        return None
    l_point = landmarks[left]
    r_point = landmarks[right]
    if l_point.visibility < 0.4 or r_point.visibility < 0.4:
        return None
    return Landmark(
        x=(l_point.x + r_point.x) / 2,
        y=(l_point.y + r_point.y) / 2,
        visibility=min(l_point.visibility, r_point.visibility),
    )
