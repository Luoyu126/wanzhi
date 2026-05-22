from __future__ import annotations

from typing import Any

from wanzhi.vision.pose.base import Landmark, PoseResult


class MediaPipePoseEstimator:
    name = "mediapipe"

    def __init__(self, min_detection_confidence: float = 0.5) -> None:
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError(
                "MediaPipe is not installed for this platform. "
                "Use pose_backend=opencv_bbox/null or install a compatible backend."
            ) from exc

        self.mp = mp
        self.pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=0,
            enable_segmentation=False,
            min_detection_confidence=min_detection_confidence,
        )

    def estimate(self, frame: Any) -> PoseResult:
        import cv2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.pose.process(rgb)
        if not result.pose_landmarks:
            return PoseResult(backend=self.name)
        landmarks = [
            Landmark(x=point.x, y=point.y, visibility=point.visibility)
            for point in result.pose_landmarks.landmark
        ]
        return PoseResult(landmarks=landmarks, backend=self.name, confidence=1.0)
