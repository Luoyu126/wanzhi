from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass

from wanzhi.vision.pose.base import Landmark

# COCO 17-keypoint indices
LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_ELBOW = 7
RIGHT_ELBOW = 8
LEFT_WRIST = 9
RIGHT_WRIST = 10

UPPER_BODY_POINTS = (
    LEFT_SHOULDER,
    RIGHT_SHOULDER,
    LEFT_ELBOW,
    RIGHT_ELBOW,
    LEFT_WRIST,
    RIGHT_WRIST,
)


@dataclass(frozen=True)
class GestureDetectionConfig:
    min_keypoint_confidence: float = 0.5
    required_consecutive_frames: int = 6
    cooldown_seconds: float = 30.0
    raised_hand_margin: float = 0.04
    raised_elbow_margin: float = 0.08
    wave_window_frames: int = 10
    wave_min_points: int = 6
    wave_min_horizontal_range: float = 0.16
    wave_min_direction_changes: int = 2
    wave_max_vertical_range: float = 0.18
    struggle_window_frames: int = 8
    struggle_min_frames: int = 5
    struggle_joint_motion_threshold: float = 0.045
    struggle_avg_motion_threshold: float = 0.055
    struggle_peak_motion_threshold: float = 0.11
    struggle_min_active_joints: int = 3


@dataclass(frozen=True)
class GestureDetectionResult:
    status: str
    confidence: float = 0.0
    reason: str = ""
    duration_seconds: float = 0.0
    keypoints_summary: dict | None = None
    should_emit: bool = False


class DistressGestureDetector:
    """Heuristic distress gesture detection on COCO 17 pose keypoints."""

    def __init__(self, config: GestureDetectionConfig) -> None:
        self.config = config
        self._wrist_history: dict[str, deque[tuple[float, float]]] = {
            "left": deque(maxlen=config.wave_window_frames),
            "right": deque(maxlen=config.wave_window_frames),
        }
        self._motion_history: deque[dict[str, float]] = deque(maxlen=config.struggle_window_frames)
        self._previous_landmarks: list[Landmark] | None = None
        self._active_reason = ""
        self._gesture_started_at: float | None = None
        self._consecutive = 0
        self._last_alert_at = 0.0

    def update(self, landmarks: list[Landmark], metadata: dict | None = None) -> GestureDetectionResult:
        now = time.monotonic()
        detected, reason, confidence, summary, matched_rules = self._evaluate_pose(landmarks)
        if metadata:
            summary.update(metadata)

        if not detected:
            self._active_reason = ""
            self._gesture_started_at = None
            self._consecutive = 0
            summary["consecutive_frames"] = 0
            summary["matched_rules"] = []
            return GestureDetectionResult(status="normal", keypoints_summary=summary)

        if reason != self._active_reason:
            self._active_reason = reason
            self._gesture_started_at = None
            self._consecutive = 0

        self._consecutive += 1
        self._gesture_started_at = self._gesture_started_at or now
        duration = now - self._gesture_started_at
        summary["consecutive_frames"] = self._consecutive
        summary["matched_rules"] = matched_rules

        enough_frames = self._consecutive >= self.config.required_consecutive_frames
        cooled_down = now - self._last_alert_at >= self.config.cooldown_seconds
        if enough_frames and cooled_down:
            self._last_alert_at = now
            return GestureDetectionResult(
                status="distress",
                confidence=confidence,
                reason=reason,
                duration_seconds=duration,
                keypoints_summary=summary,
                should_emit=True,
            )

        return GestureDetectionResult(
            status="suspicious",
            confidence=confidence,
            reason=reason,
            duration_seconds=duration,
            keypoints_summary=summary,
        )

    def _evaluate_pose(
        self,
        landmarks: list[Landmark],
    ) -> tuple[bool, str, float, dict, list[str]]:
        summary: dict = {"visible_points": 0}
        if len(landmarks) < 17:
            self._reset_motion_state()
            return False, "insufficient_keypoints", 0.0, summary, []

        visible = [point for point in landmarks if point.visibility >= self.config.min_keypoint_confidence]
        summary["visible_points"] = len(visible)
        if len(visible) < 6:
            self._reset_motion_state()
            return False, "insufficient_keypoints", 0.0, summary, []

        self._update_histories(landmarks, summary)

        raised_side = self._raised_hand_side(landmarks)
        if raised_side:
            summary["raised_hand_side"] = raised_side
            return True, "hand_raise_sos", 0.82, summary, ["raised_hand"]

        wave_side, wave_summary = self._wave_side(landmarks)
        summary.update(wave_summary)
        if wave_side:
            summary["wave_side"] = wave_side
            return True, "arm_wave_sos", 0.78, summary, ["arm_wave"]

        struggle_summary = self._struggle_summary()
        summary.update(struggle_summary)
        if struggle_summary.get("is_struggling"):
            return True, "abnormal_struggle", 0.74, summary, ["upper_body_struggle"]

        return False, "monitoring", 0.0, summary, []

    def _update_histories(self, landmarks: list[Landmark], summary: dict) -> None:
        for side, wrist_index in (("left", LEFT_WRIST), ("right", RIGHT_WRIST)):
            wrist = _visible_point(landmarks, wrist_index, self.config.min_keypoint_confidence)
            if wrist is not None:
                self._wrist_history[side].append((wrist.x, wrist.y))

        if self._previous_landmarks is not None:
            motions: list[float] = []
            active_joints = 0
            for index in UPPER_BODY_POINTS:
                current = _visible_point(landmarks, index, self.config.min_keypoint_confidence)
                previous = _visible_point(self._previous_landmarks, index, self.config.min_keypoint_confidence)
                if current is None or previous is None:
                    continue
                distance = math.hypot(current.x - previous.x, current.y - previous.y)
                motions.append(distance)
                if distance >= self.config.struggle_joint_motion_threshold:
                    active_joints += 1
            if motions:
                frame_motion = max(motions)
                avg_motion = sum(motions) / len(motions)
                self._motion_history.append(
                    {
                        "frame_motion": frame_motion,
                        "avg_motion": avg_motion,
                        "active_joints": float(active_joints),
                    }
                )
                summary["latest_upper_body_motion"] = avg_motion
                summary["latest_active_joints"] = active_joints
        self._previous_landmarks = list(landmarks)

    def _raised_hand_side(self, landmarks: list[Landmark]) -> str:
        for side, shoulder_index, elbow_index, wrist_index in (
            ("left", LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST),
            ("right", RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST),
        ):
            shoulder = _visible_point(landmarks, shoulder_index, self.config.min_keypoint_confidence)
            elbow = _visible_point(landmarks, elbow_index, self.config.min_keypoint_confidence)
            wrist = _visible_point(landmarks, wrist_index, self.config.min_keypoint_confidence)
            if shoulder is None or elbow is None or wrist is None:
                continue
            wrist_above_shoulder = wrist.y + self.config.raised_hand_margin < shoulder.y
            elbow_lifted = elbow.y <= shoulder.y + self.config.raised_elbow_margin
            if wrist_above_shoulder and elbow_lifted:
                return side
        return ""

    def _wave_side(self, landmarks: list[Landmark]) -> tuple[str, dict]:
        summary: dict = {}
        for side, points in self._wrist_history.items():
            if len(points) < self.config.wave_min_points:
                continue
            if not self._wave_arm_lifted(landmarks, side):
                continue
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            horizontal_range = max(xs) - min(xs)
            vertical_range = max(ys) - min(ys)
            direction_changes = _direction_changes(xs)
            summary[f"{side}_wrist_horizontal_range"] = horizontal_range
            summary[f"{side}_wrist_vertical_range"] = vertical_range
            summary[f"{side}_wrist_direction_changes"] = direction_changes
            if (
                horizontal_range >= self.config.wave_min_horizontal_range
                and vertical_range <= self.config.wave_max_vertical_range
                and direction_changes >= self.config.wave_min_direction_changes
            ):
                return side, summary
        return "", summary

    def _wave_arm_lifted(self, landmarks: list[Landmark], side: str) -> bool:
        shoulder_index = LEFT_SHOULDER if side == "left" else RIGHT_SHOULDER
        wrist_index = LEFT_WRIST if side == "left" else RIGHT_WRIST
        shoulder = _visible_point(landmarks, shoulder_index, self.config.min_keypoint_confidence)
        wrist = _visible_point(landmarks, wrist_index, self.config.min_keypoint_confidence)
        if shoulder is None or wrist is None:
            return False
        return wrist.y <= shoulder.y + self.config.raised_elbow_margin

    def _struggle_summary(self) -> dict:
        if len(self._motion_history) < self.config.struggle_min_frames:
            return {"is_struggling": False}

        recent = list(self._motion_history)
        avg_motion = sum(item["avg_motion"] for item in recent) / len(recent)
        peak_motion = max(item["frame_motion"] for item in recent)
        active_frames = sum(
            1
            for item in recent
            if item["active_joints"] >= self.config.struggle_min_active_joints
        )
        is_struggling = (
            avg_motion >= self.config.struggle_avg_motion_threshold
            and peak_motion >= self.config.struggle_peak_motion_threshold
            and active_frames >= self.config.struggle_min_frames
        )
        return {
            "is_struggling": is_struggling,
            "upper_body_avg_motion": avg_motion,
            "upper_body_peak_motion": peak_motion,
            "upper_body_active_frames": active_frames,
        }

    def _reset_motion_state(self) -> None:
        for history in self._wrist_history.values():
            history.clear()
        self._motion_history.clear()
        self._previous_landmarks = None


def _visible_point(landmarks: list[Landmark], index: int, min_confidence: float) -> Landmark | None:
    if len(landmarks) <= index:
        return None
    point = landmarks[index]
    if point.visibility < min_confidence:
        return None
    return point


def _direction_changes(values: list[float]) -> int:
    changes = 0
    previous_direction = 0
    for before, after in zip(values, values[1:]):
        delta = after - before
        if abs(delta) < 0.01:
            continue
        direction = 1 if delta > 0 else -1
        if previous_direction and direction != previous_direction:
            changes += 1
        previous_direction = direction
    return changes
