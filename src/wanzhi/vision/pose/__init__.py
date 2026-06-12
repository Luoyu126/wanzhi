from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from wanzhi.vision.pose.base import Landmark, PoseEstimator, PoseResult
from wanzhi.vision.pose.null_backend import NullPoseEstimator
from wanzhi.vision.pose.opencv_bbox_backend import OpenCVBboxPoseEstimator

if TYPE_CHECKING:
    from wanzhi.vision.fall_detector import FallDetectionConfig
    from wanzhi.vision.gesture_detector import GestureDetectionConfig


def create_pose_estimator(
    backend: str,
    *,
    min_detection_confidence: float = 0.5,
    model_path: Path | None = None,
    fall_config: FallDetectionConfig | None = None,
    gesture_config: GestureDetectionConfig | None = None,
    input_size: int = 640,
):
    selected = backend.lower()
    if selected in {"auto", "yolo"}:
        try:
            from wanzhi.vision.pose.yolo_backend import YoloPoseEstimator

            resolved = model_path or Path("models/yolov8n-pose.onnx")
            return YoloPoseEstimator(
                model_path=resolved,
                min_detection_confidence=min_detection_confidence,
                fall_config=fall_config,
                gesture_config=gesture_config,
                input_size=input_size,
            )
        except RuntimeError as exc:
            if selected == "yolo":
                raise
            print(f"vision yolo backend unavailable: {exc}; using opencv_bbox", flush=True)

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
