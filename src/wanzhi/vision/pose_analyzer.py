from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from wanzhi.vision.fall_detector import FallDetectionConfig, FallDetectionResult, FallDetector
from wanzhi.vision.gesture_detector import (
    DistressGestureDetector,
    GestureDetectionConfig,
    GestureDetectionResult,
)
from wanzhi.vision.pose.base import Landmark, PoseResult

COCO_KEYPOINTS = 17
COCO_SKELETON = (
    (0, 1),
    (0, 2),
    (1, 3),
    (2, 4),
    (5, 6),
    (5, 7),
    (7, 9),
    (6, 8),
    (8, 10),
    (5, 11),
    (6, 12),
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
)


@dataclass(frozen=True)
class PoseAnalyzerConfig:
    model_path: Path
    input_size: int = 640
    min_detection_confidence: float = 0.5
    nms_iou_threshold: float = 0.45


class PoseAnalyzer:
    """YOLO pose ONNX inference, skeleton overlay, and fall detection."""

    name = "yolo"

    def __init__(
        self,
        config: PoseAnalyzerConfig,
        fall_config: FallDetectionConfig,
        gesture_config: GestureDetectionConfig | None = None,
    ) -> None:
        import onnxruntime as ort

        if not config.model_path.exists():
            raise RuntimeError(
                f"YOLO pose model not found: {config.model_path}. "
                "Run scripts/download_models.sh or place yolov8n-pose.onnx there."
            )

        self.config = config
        self.fall_detector = FallDetector(fall_config)
        self.gesture_detector = DistressGestureDetector(gesture_config or GestureDetectionConfig())
        providers = ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(config.model_path), providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        input_shape = self.session.get_inputs()[0].shape
        self.input_height = int(input_shape[2]) if len(input_shape) > 2 and input_shape[2] else config.input_size
        self.input_width = int(input_shape[3]) if len(input_shape) > 3 and input_shape[3] else config.input_size
        self.warmup()

    def warmup(self) -> None:
        """Run one dummy inference so ONNX Runtime allocates buffers at startup."""
        started = time.monotonic()
        dummy = build_warmup_tensor(self.input_height, self.input_width)
        self.session.run(None, {self.input_name: dummy})
        elapsed = time.monotonic() - started
        print(
            f"vision yolo warmup done seconds={elapsed:.3f} "
            f"shape={tuple(dummy.shape)}",
            flush=True,
        )

    def analyze(
        self,
        frame: np.ndarray,
    ) -> tuple[PoseResult, FallDetectionResult, GestureDetectionResult, np.ndarray]:
        detection = self._infer_best_person(frame)
        frame_height = float(frame.shape[0])
        if detection is None:
            empty = PoseResult(backend=self.name)
            fall_result = self.fall_detector.update(
                [],
                metadata={"bbox": None, "frame_height": frame_height},
            )
            gesture_result = self.gesture_detector.update(
                [],
                metadata={"bbox": None, "frame_height": frame_height},
            )
            overlay = self._draw_status(frame.copy(), fall_result, gesture_result, None, {"bbox": None})
            return empty, fall_result, gesture_result, overlay

        landmarks, metadata = detection
        metadata["frame_height"] = frame_height
        pose = PoseResult(
            landmarks=landmarks,
            backend=self.name,
            confidence=float(metadata.get("confidence", 0.0)),
            metadata=metadata,
        )
        fall_result = self.fall_detector.update(landmarks, metadata=metadata)
        gesture_result = self.gesture_detector.update(landmarks, metadata=metadata)
        overlay = self._draw_overlay(frame, fall_result, gesture_result, metadata, landmarks)
        return pose, fall_result, gesture_result, overlay

    def _infer_best_person(self, frame: np.ndarray) -> tuple[list[Landmark], dict[str, Any]] | None:
        height, width = frame.shape[:2]
        blob, ratio, pad = _letterbox(
            frame,
            new_shape=(self.input_height, self.input_width),
        )
        tensor = blob.transpose(2, 0, 1)[None, ...].astype(np.float32) / 255.0
        outputs = self.session.run(None, {self.input_name: tensor})
        candidates = _parse_yolo_pose_outputs(outputs[0], min_conf=self.config.min_detection_confidence)
        if not candidates:
            return None

        boxes = np.array([item["bbox_xyxy"] for item in candidates], dtype=np.float32)
        scores = np.array([item["score"] for item in candidates], dtype=np.float32)
        keep = _nms(boxes, scores, self.config.nms_iou_threshold)
        if len(keep) == 0:
            return None

        best = candidates[int(keep[0])]
        bbox = _scale_bbox(best["bbox_xyxy"], ratio, pad, width, height)
        keypoints = _scale_keypoints(best["keypoints"], ratio, pad, width, height)
        landmarks = _keypoints_to_landmarks(keypoints, width, height)
        x1, y1, x2, y2 = bbox
        metadata = {
            "bbox": [int(x1), int(y1), int(x2 - x1), int(y2 - y1)],
            "bbox_xyxy": [float(x1), float(y1), float(x2), float(y2)],
            "confidence": float(best["score"]),
            "keypoints_px": keypoints.tolist(),
        }
        return landmarks, metadata

    def _draw_overlay(
        self,
        frame: np.ndarray,
        fall_result: FallDetectionResult,
        gesture_result: GestureDetectionResult,
        metadata: dict[str, Any],
        landmarks: list[Landmark],
    ) -> np.ndarray:
        image = frame.copy()
        keypoints_px = np.array(metadata.get("keypoints_px") or [], dtype=np.float32)
        if keypoints_px.size:
            _draw_skeleton(image, keypoints_px)

        status, confidence, reason, color = _display_status(fall_result, gesture_result)

        bbox = metadata.get("bbox")
        if bbox:
            x, y, w, h = [int(value) for value in bbox]
            cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)
            label = f"PERSON {status.upper()} {confidence:.2f}"
            cv2.putText(
                image,
                label,
                (x, max(24, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                image,
                f"reason={reason}",
                (x, min(image.shape[0] - 16, y + h + 24)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
                cv2.LINE_AA,
            )
        else:
            image = self._draw_status(image, fall_result, gesture_result, landmarks, metadata)
        return image

    def _draw_status(
        self,
        image: np.ndarray,
        fall_result: FallDetectionResult,
        gesture_result: GestureDetectionResult,
        landmarks: list[Landmark] | None,
        metadata: dict[str, Any] | None = None,
    ) -> np.ndarray:
        status, _confidence, reason, color = _display_status(fall_result, gesture_result)
        label = "NO PERSON" if not landmarks else "PERSON"
        cv2.putText(
            image,
            f"{label} {status.upper()}",
            (16, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
            cv2.LINE_AA,
        )
        summary = metadata or {}
        visible_kpts = sum(1 for _, _, conf in (summary.get("keypoints_px") or []) if conf >= 0.35)
        cv2.putText(
            image,
            f"backend={self.name} reason={reason} kpts={visible_kpts}/17",
            (16, image.shape[0] - 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )
        return image


def _display_status(
    fall_result: FallDetectionResult,
    gesture_result: GestureDetectionResult,
) -> tuple[str, float, str, tuple[int, int, int]]:
    if gesture_result.status == "distress":
        return "sos", gesture_result.confidence, gesture_result.reason or "distress", (0, 0, 255)
    if fall_result.status == "fall":
        return "fall", fall_result.confidence, fall_result.reason or "fall_detected", (0, 0, 255)
    if gesture_result.status == "suspicious":
        return "sos_suspicious", gesture_result.confidence, gesture_result.reason or "distress", (0, 180, 255)
    if fall_result.status == "suspicious":
        return "suspicious", fall_result.confidence, fall_result.reason or "fall_suspected", (0, 180, 255)
    return "normal", 0.0, "monitoring", (0, 200, 0)


def build_warmup_tensor(input_height: int, input_width: int) -> np.ndarray:
    """Build a zeroed dummy tensor matching YOLO pose input shape."""
    return np.zeros((1, 3, input_height, input_width), dtype=np.float32)


def _letterbox(
    image: np.ndarray,
    new_shape: tuple[int, int],
    color: tuple[int, int, int] = (114, 114, 114),
) -> tuple[np.ndarray, float, tuple[float, float]]:
    shape = image.shape[:2]
    ratio = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    resized = cv2.resize(image, (int(round(shape[1] * ratio)), int(round(shape[0] * ratio))), interpolation=cv2.INTER_LINEAR)
    pad_w = new_shape[1] - resized.shape[1]
    pad_h = new_shape[0] - resized.shape[0]
    top = pad_h / 2
    bottom = pad_h - top
    left = pad_w / 2
    right = pad_w - left
    padded = cv2.copyMakeBorder(
        resized,
        int(round(top)),
        int(round(bottom)),
        int(round(left)),
        int(round(right)),
        cv2.BORDER_CONSTANT,
        value=color,
    )
    return padded, ratio, (left, top)


def _parse_yolo_pose_outputs(output: np.ndarray, *, min_conf: float) -> list[dict[str, Any]]:
    arr = np.asarray(output)
    if arr.ndim == 3:
        arr = arr[0]
    if arr.shape[0] in {56, 57} and arr.shape[0] < arr.shape[1]:
        arr = arr.T
    candidates: list[dict[str, Any]] = []
    for row in arr:
        if row.shape[0] < 56:
            continue
        score = float(row[4])
        if score < min_conf:
            continue
        keypoints = row[5:56].reshape(COCO_KEYPOINTS, 3)
        candidates.append(
            {
                "bbox_xyxy": row[:4].astype(np.float32),
                "score": score,
                "keypoints": keypoints.astype(np.float32),
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    if len(boxes) == 0:
        return []
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        index = int(order[0])
        keep.append(index)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[index], x1[rest])
        yy1 = np.maximum(y1[index], y1[rest])
        xx2 = np.minimum(x2[index], x2[rest])
        yy2 = np.minimum(y2[index], y2[rest])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        union = areas[index] + areas[rest] - inter
        iou = np.where(union > 0, inter / union, 0.0)
        order = rest[iou <= iou_threshold]
    return keep


def _scale_bbox(
    bbox: np.ndarray,
    ratio: float,
    pad: tuple[float, float],
    width: int,
    height: int,
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = bbox
    x1 = (x1 - pad[0]) / ratio
    x2 = (x2 - pad[0]) / ratio
    y1 = (y1 - pad[1]) / ratio
    y2 = (y2 - pad[1]) / ratio
    x1 = float(np.clip(x1, 0, width - 1))
    x2 = float(np.clip(x2, 0, width - 1))
    y1 = float(np.clip(y1, 0, height - 1))
    y2 = float(np.clip(y2, 0, height - 1))
    return x1, y1, x2, y2


def _scale_keypoints(
    keypoints: np.ndarray,
    ratio: float,
    pad: tuple[float, float],
    width: int,
    height: int,
) -> np.ndarray:
    scaled = keypoints.copy()
    scaled[:, 0] = (scaled[:, 0] - pad[0]) / ratio
    scaled[:, 1] = (scaled[:, 1] - pad[1]) / ratio
    scaled[:, 0] = np.clip(scaled[:, 0], 0, width - 1)
    scaled[:, 1] = np.clip(scaled[:, 1], 0, height - 1)
    return scaled


def _keypoints_to_landmarks(keypoints: np.ndarray, width: int, height: int) -> list[Landmark]:
    landmarks: list[Landmark] = []
    for x, y, conf in keypoints:
        landmarks.append(
            Landmark(
                x=float(x / max(width, 1)),
                y=float(y / max(height, 1)),
                visibility=float(conf),
            )
        )
    return landmarks


def _draw_skeleton(image: np.ndarray, keypoints: np.ndarray) -> None:
    for start, end in COCO_SKELETON:
        if start >= len(keypoints) or end >= len(keypoints):
            continue
        x1, y1, c1 = keypoints[start]
        x2, y2, c2 = keypoints[end]
        if c1 < 0.35 or c2 < 0.35:
            continue
        cv2.line(image, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 180), 3, cv2.LINE_AA)
    for index, (x, y, conf) in enumerate(keypoints):
        if conf < 0.35:
            continue
        center = (int(x), int(y))
        cv2.circle(image, center, 5, (255, 200, 0), -1, cv2.LINE_AA)
        cv2.circle(image, center, 5, (0, 0, 0), 1, cv2.LINE_AA)
        cv2.putText(
            image,
            str(index),
            (center[0] + 6, center[1] - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
