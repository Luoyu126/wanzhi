from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import yaml

from wanzhi.core.bus import JsonlEventBus
from wanzhi.core.config import load_config
from wanzhi.core.events import Event, EventTypes
from wanzhi.services.emergency.notifier import EmergencyNotifier
from wanzhi.vision.alerter import VisionAlerter
from wanzhi.vision.camera import Camera
from wanzhi.vision.fall_detector import FallDetectionConfig, FallDetector
from wanzhi.vision.pose import create_pose_estimator


def main() -> None:
    config = load_config()
    if not config.get("vision.enabled", True):
        print("vision disabled by config")
        return

    fall_config_path = config.path("vision.fall_config", "config/fall_detection.yaml")
    fall_data = yaml.safe_load(fall_config_path.read_text(encoding="utf-8")) or {}
    detector = FallDetector(
        FallDetectionConfig(
            fall_aspect_ratio=float(fall_data.get("fall_aspect_ratio", 1.3)),
            torso_angle_degrees=float(fall_data.get("torso_angle_degrees", 55)),
            hip_shoulder_vertical_ratio=float(fall_data.get("hip_shoulder_vertical_ratio", 0.15)),
            min_fall_seconds=float(fall_data.get("min_fall_seconds", 1.5)),
            required_consecutive_frames=int(fall_data.get("required_consecutive_frames", 6)),
            cooldown_seconds=float(fall_data.get("cooldown_seconds", 30)),
        )
    )
    camera = Camera(
        camera_id=int(config.get("vision.camera_id", 0)),
        device_path=str(config.get("vision.device_path", "") or "") or None,
        width=int(config.get("vision.width", 640)),
        height=int(config.get("vision.height", 480)),
        fps=float(config.get("vision.fps_target", 6)),
    )
    estimator = create_pose_estimator(
        str(config.get("vision.pose_backend", "auto")),
        min_detection_confidence=float(fall_data.get("min_detection_confidence", 0.5)),
    )
    print(f"vision pose backend: {estimator.name}", flush=True)
    bus = JsonlEventBus(config.path("events.log_path", "data/events.jsonl"))
    alerter = VisionAlerter(EmergencyNotifier(bus))
    interval = 1.0 / max(float(config.get("vision.fps_target", 8)), 1.0)
    health_interval = float(config.get("vision.health_interval_seconds", 30))
    snapshot_dir = config.path("vision.snapshot_dir", "data/vision-events")
    emit_snapshots = bool(config.get("vision.emit_snapshots", True))
    preview_frame_path = config.path("vision.preview_frame_path", "data/camera-preview/latest.jpg")
    preview_every = max(int(config.get("vision.preview_update_every_frames", 2)), 1)
    last_health = 0.0
    frames = 0
    failed_frames = 0

    try:
        while True:
            frame = camera.read()
            if frame is not None:
                frames += 1
                pose = estimator.estimate(frame)
                result = detector.update(pose.landmarks, metadata=pose.metadata)
                if frames % preview_every == 0:
                    overlay = _draw_overlay(camera, frame, result, pose.backend)
                    _write_preview_frame(camera, overlay, preview_frame_path)
                if result.status == "suspicious":
                    bus.emit(Event(EventTypes.VISION_FALL_SUSPECTED, _payload(result, pose.backend), source="vision"))
                if result.should_emit:
                    snapshot_path = None
                    if emit_snapshots:
                        snapshot_path = _write_snapshot(camera, snapshot_dir)
                    alerter.fall_detected(result, snapshot_path=snapshot_path)
            else:
                failed_frames += 1
            now = time.monotonic()
            if now - last_health >= health_interval:
                last_health = now
                bus.emit(
                    Event(
                        EventTypes.VISION_HEALTH,
                        {
                            "frames": frames,
                            "failed_frames": failed_frames,
                            "pose_backend": estimator.name,
                        },
                        source="vision",
                    )
                )
                print(f"vision health frames={frames} failed={failed_frames} backend={estimator.name}", flush=True)
            time.sleep(interval)
    finally:
        camera.close()


def _payload(result, backend: str) -> dict:
    return {
        "status": result.status,
        "confidence": result.confidence,
        "reason": result.reason,
        "duration_seconds": result.duration_seconds,
        "keypoints_summary": result.keypoints_summary or {},
        "pose_backend": backend,
    }


def _write_snapshot(camera: Camera, snapshot_dir) -> str | None:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = snapshot_dir / f"fall-{timestamp}.jpg"
    snapshot = camera.capture_snapshot(path)
    return str(snapshot) if snapshot else None


def _write_preview_frame(camera: Camera, frame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp.jpg")
    ok = camera.cv2.imwrite(str(tmp_path), frame)
    if ok:
        tmp_path.replace(path)


def _draw_overlay(camera: Camera, frame, result, backend: str):
    image = frame.copy()
    bbox = (result.keypoints_summary or {}).get("bbox")
    status = result.status.upper()
    reason = result.reason or "monitoring"
    confidence = result.confidence
    color = {
        "normal": (0, 200, 0),
        "suspicious": (0, 180, 255),
        "fall": (0, 0, 255),
    }.get(result.status, (255, 255, 255))

    if bbox:
        x, y, w, h = [int(value) for value in bbox]
        camera.cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)
        label = f"PERSON {status} {confidence:.2f}"
        camera.cv2.putText(
            image,
            label,
            (x, max(24, y - 8)),
            camera.cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
            camera.cv2.LINE_AA,
        )
    else:
        camera.cv2.putText(
            image,
            f"NO PERSON {status}",
            (16, 32),
            camera.cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
            camera.cv2.LINE_AA,
        )

    camera.cv2.putText(
        image,
        f"backend={backend} reason={reason}",
        (16, image.shape[0] - 16),
        camera.cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color,
        1,
        camera.cv2.LINE_AA,
    )
    return image


if __name__ == "__main__":
    main()
