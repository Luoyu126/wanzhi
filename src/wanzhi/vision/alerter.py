from __future__ import annotations

from wanzhi.services.emergency.notifier import EmergencyNotifier
from wanzhi.vision.fall_detector import FallDetectionResult
from wanzhi.vision.gesture_detector import GestureDetectionResult


class VisionAlerter:
    def __init__(self, notifier: EmergencyNotifier) -> None:
        self.notifier = notifier

    def fall_detected(self, result: FallDetectionResult) -> None:
        payload = {
            "status": result.status,
            "confidence": result.confidence,
            "duration_seconds": result.duration_seconds,
            "keypoints_summary": result.keypoints_summary or {},
        }
        self.notifier.notify(result.reason or "fall_detected", source="vision", payload=payload)

    def distress_detected(self, result: GestureDetectionResult) -> None:
        payload = {
            "status": result.status,
            "confidence": result.confidence,
            "duration_seconds": result.duration_seconds,
            "keypoints_summary": result.keypoints_summary or {},
        }
        self.notifier.notify(result.reason or "distress_detected", source="vision", payload=payload)
