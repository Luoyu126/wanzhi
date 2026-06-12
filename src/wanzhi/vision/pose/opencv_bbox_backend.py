from __future__ import annotations

from typing import Any

from wanzhi.vision.pose.base import Landmark, PoseResult


class OpenCVBboxPoseEstimator:
    """Very lightweight fallback: infer a body-like box from foreground motion."""

    name = "opencv_bbox"

    def __init__(self, min_area_ratio: float = 0.03) -> None:
        import cv2

        self.cv2 = cv2
        self.min_area_ratio = min_area_ratio
        self.subtractor = cv2.createBackgroundSubtractorMOG2(
            history=120,
            varThreshold=32,
            detectShadows=True,
        )

    def estimate(self, frame: Any) -> PoseResult:
        height, width = frame.shape[:2]
        mask = self.subtractor.apply(frame)
        mask = self.cv2.medianBlur(mask, 5)
        contours, _ = self.cv2.findContours(mask, self.cv2.RETR_EXTERNAL, self.cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return PoseResult(backend=self.name)

        contour = max(contours, key=self.cv2.contourArea)
        area = float(self.cv2.contourArea(contour))
        if area < width * height * self.min_area_ratio:
            return PoseResult(backend=self.name)

        x, y, w, h = self.cv2.boundingRect(contour)
        landmarks = _bbox_landmarks(x / width, y / height, w / width, h / height)
        confidence = min(1.0, area / (width * height * 0.25))
        return PoseResult(
            landmarks=landmarks,
            backend=self.name,
            confidence=confidence,
            metadata={"bbox": [x, y, w, h], "area": area, "frame_height": float(height)},
        )


def _bbox_landmarks(x: float, y: float, w: float, h: float) -> list[Landmark]:
    points = [Landmark(x=x + w / 2, y=y + h / 2, visibility=0.9) for _ in range(17)]
    points[5] = Landmark(x=x + w * 0.3, y=y + h * 0.25, visibility=0.9)
    points[6] = Landmark(x=x + w * 0.7, y=y + h * 0.25, visibility=0.9)
    points[11] = Landmark(x=x + w * 0.35, y=y + h * 0.55, visibility=0.9)
    points[12] = Landmark(x=x + w * 0.65, y=y + h * 0.55, visibility=0.9)
    return points
