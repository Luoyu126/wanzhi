from __future__ import annotations

from wanzhi.vision.pose.base import Landmark, PoseEstimator, PoseResult
from wanzhi.vision.pose.null_backend import NullPoseEstimator
from wanzhi.vision.pose.opencv_bbox_backend import OpenCVBboxPoseEstimator


def create_pose_estimator(backend: str, min_detection_confidence: float = 0.5):
    selected = backend.lower()
    if selected in {"auto", "mediapipe"}:
        try:
            from wanzhi.vision.pose.mediapipe_backend import MediaPipePoseEstimator

            return MediaPipePoseEstimator(min_detection_confidence=min_detection_confidence)
        except RuntimeError as exc:
            if selected == "mediapipe":
                raise
            print(f"vision pose backend unavailable: {exc}; using opencv_bbox", flush=True)

    if selected in {"auto", "opencv_bbox", "opencv"}:
        try:
            return OpenCVBboxPoseEstimator()
        except Exception as exc:
            if selected in {"opencv_bbox", "opencv"}:
                raise
            print(f"vision opencv_bbox backend unavailable: {exc}; using null", flush=True)

    return NullPoseEstimator()


__all__ = [
    "Landmark",
    "PoseEstimator",
    "PoseResult",
    "create_pose_estimator",
]
