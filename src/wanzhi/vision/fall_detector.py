from __future__ import annotations

import math
import time
from dataclasses import dataclass

from wanzhi.vision.pose.base import Landmark

# COCO 17-keypoint indices
LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_HIP = 11
RIGHT_HIP = 12


@dataclass(frozen=True)
class FallDetectionConfig:
    fall_aspect_ratio: float = 1.2
    torso_angle_degrees: float = 30.0
    vertical_velocity_threshold: float = 0.08
    min_fall_seconds: float = 0.0
    required_consecutive_frames: int = 15
    cooldown_seconds: float = 30.0
    min_keypoint_confidence: float = 0.4


@dataclass(frozen=True)
class FallDetectionResult:
    status: str
    confidence: float = 0.0
    reason: str = ""
    duration_seconds: float = 0.0
    keypoints_summary: dict | None = None
    should_emit: bool = False


class FallDetector:
    """Heuristic fall detection on COCO 17 pose keypoints with frame debounce."""

    def __init__(self, config: FallDetectionConfig) -> None:
        self.config = config
        self._fall_started_at: float | None = None
        self._consecutive = 0
        self._last_alert_at = 0.0
        self._prev_hip_y: float | None = None

    def update(self, landmarks: list[Landmark], metadata: dict | None = None) -> FallDetectionResult:
        now = time.monotonic()
        frame_height = float((metadata or {}).get("frame_height", 1.0))
        falling, reason, confidence, summary, matched_rules = self._evaluate_pose(landmarks, metadata, frame_height)
        if metadata:
            summary.update(metadata)
        if not falling:
            self._fall_started_at = None
            self._consecutive = 0
            self._prev_hip_y = summary.get("hip_center_y_norm")
            summary["consecutive_frames"] = 0
            summary["matched_rules"] = []
            return FallDetectionResult(status="normal", keypoints_summary=summary)

        self._consecutive += 1
        summary["consecutive_frames"] = self._consecutive
        summary["matched_rules"] = matched_rules
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

    def _evaluate_pose(
        self,
        landmarks: list[Landmark],
        metadata: dict | None,
        frame_height: float,
    ) -> tuple[bool, str, float, dict, list[str]]:
        summary: dict = {"visible_points": 0}
        if len(landmarks) < 17:
            return False, "insufficient_keypoints", 0.0, summary, []

        visible = [point for point in landmarks if point.visibility >= self.config.min_keypoint_confidence]
        summary["visible_points"] = len(visible)
        if len(visible) < 6:
            return False, "insufficient_keypoints", 0.0, summary, []

        matched_rules: list[str] = []

        bbox = (metadata or {}).get("bbox")
        if bbox and len(bbox) == 4:
            _, _, width, height = bbox
            aspect_ratio = float(width) / max(float(height), 1.0)
            summary["bbox_aspect_ratio"] = aspect_ratio
            if aspect_ratio > self.config.fall_aspect_ratio:
                matched_rules.append("wide_body_aspect_ratio")

        shoulder = _midpoint(landmarks, LEFT_SHOULDER, RIGHT_SHOULDER)
        hip = _midpoint(landmarks, LEFT_HIP, RIGHT_HIP)
        if hip is not None:
            summary["hip_center_y_norm"] = hip.y
            if self._prev_hip_y is not None:
                delta_y_norm = hip.y - self._prev_hip_y
                delta_y_px = delta_y_norm * frame_height
                summary["hip_vertical_delta_norm"] = delta_y_norm
                summary["hip_vertical_delta_px"] = delta_y_px
                if delta_y_norm > self.config.vertical_velocity_threshold:
                    matched_rules.append("rapid_vertical_drop")

        if shoulder is not None and hip is not None:
            dx = hip.x - shoulder.x
            dy = hip.y - shoulder.y
            torso_angle = abs(math.degrees(math.atan2(abs(dy), abs(dx) + 1e-6)))
            summary["torso_angle"] = torso_angle
            if torso_angle < self.config.torso_angle_degrees:
                matched_rules.append("low_torso_angle")

        matched_rules = sorted(set(matched_rules))
        if len(matched_rules) < 2:
            return False, "monitoring", 0.0, summary, matched_rules

        confidence = min(1.0, 0.35 * len(matched_rules) + 0.2)
        return True, ",".join(matched_rules), confidence, summary, matched_rules


def _midpoint(landmarks: list[Landmark], left: int, right: int) -> Landmark | None:
    if len(landmarks) <= max(left, right):
        return None
    left_point = landmarks[left]
    right_point = landmarks[right]
    min_conf = 0.4
    if left_point.visibility < min_conf or right_point.visibility < min_conf:
        return None
    return Landmark(
        x=(left_point.x + right_point.x) / 2,
        y=(left_point.y + right_point.y) / 2,
        visibility=min(left_point.visibility, right_point.visibility),
    )
