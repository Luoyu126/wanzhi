from __future__ import annotations

from wanzhi.services.emergency.notifier import EmergencyNotifier
from wanzhi.vision.fall_detector import FallDetectionResult


class VisionAlerter:
    def __init__(self, notifier: EmergencyNotifier) -> None:
        self.notifier = notifier

    def fall_detected(self, result: FallDetectionResult, snapshot_path: str | None = None) -> None:
        payload = {
            "status": result.status,
            "confidence": result.confidence,
            "duration_seconds": result.duration_seconds,
            "keypoints_summary": result.keypoints_summary or {},
        }
        if snapshot_path:
            payload["snapshot_path"] = snapshot_path
        self.notifier.notify(result.reason or "fall_detected", source="vision", payload=payload)
