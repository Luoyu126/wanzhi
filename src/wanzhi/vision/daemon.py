from __future__ import annotations

import os
import time

import yaml

from wanzhi.core.bus import create_event_bus_from_config, wait_for_subscribers
from wanzhi.core.config import load_config
from wanzhi.core.events import Event, EventTypes
from wanzhi.core.vision_alerts import VisionAlertPublisher
from wanzhi.services.emergency.notifier import EmergencyNotifier
from wanzhi.vision.alerter import VisionAlerter
from wanzhi.vision.camera import Camera
from wanzhi.vision.fall_detector import FallDetectionConfig
from wanzhi.vision.gesture_detector import DistressGestureDetector, GestureDetectionConfig
from wanzhi.vision.pose import create_pose_estimator
from wanzhi.vision.pose.yolo_backend import YoloPoseEstimator
from wanzhi.vision.shared_memory import SharedMemoryManager


def main() -> None:
    config = load_config()
    if not config.get("vision.enabled", True):
        print("vision disabled by config")
        return

    nice_level = config.get("vision.nice_level")
    if nice_level is not None:
        try:
            os.nice(int(nice_level))
        except OSError as exc:
            print(f"vision nice adjustment failed: {exc}", flush=True)

    fall_config_path = config.path("vision.fall_config", "config/fall_detection.yaml")
    fall_data = yaml.safe_load(fall_config_path.read_text(encoding="utf-8")) or {}
    fall_config = FallDetectionConfig(
        fall_aspect_ratio=float(fall_data.get("fall_aspect_ratio", 1.2)),
        torso_angle_degrees=float(fall_data.get("torso_angle_degrees", 30)),
        vertical_velocity_threshold=float(fall_data.get("vertical_velocity_threshold", 0.08)),
        min_fall_seconds=float(fall_data.get("min_fall_seconds", 0)),
        required_consecutive_frames=int(fall_data.get("required_consecutive_frames", 15)),
        cooldown_seconds=float(fall_data.get("cooldown_seconds", 30)),
        min_keypoint_confidence=float(fall_data.get("min_detection_confidence", 0.5)),
    )
    gesture_config_path = config.path("vision.gesture_config", "config/gesture_detection.yaml")
    gesture_data = yaml.safe_load(gesture_config_path.read_text(encoding="utf-8")) or {}
    gesture_config = GestureDetectionConfig(
        min_keypoint_confidence=float(gesture_data.get("min_keypoint_confidence", 0.5)),
        required_consecutive_frames=int(gesture_data.get("required_consecutive_frames", 6)),
        cooldown_seconds=float(gesture_data.get("cooldown_seconds", 30)),
        raised_hand_margin=float(gesture_data.get("raised_hand_margin", 0.04)),
        raised_elbow_margin=float(gesture_data.get("raised_elbow_margin", 0.08)),
        wave_window_frames=int(gesture_data.get("wave_window_frames", 10)),
        wave_min_points=int(gesture_data.get("wave_min_points", 6)),
        wave_min_horizontal_range=float(gesture_data.get("wave_min_horizontal_range", 0.16)),
        wave_min_direction_changes=int(gesture_data.get("wave_min_direction_changes", 2)),
        wave_max_vertical_range=float(gesture_data.get("wave_max_vertical_range", 0.18)),
        struggle_window_frames=int(gesture_data.get("struggle_window_frames", 8)),
        struggle_min_frames=int(gesture_data.get("struggle_min_frames", 5)),
        struggle_joint_motion_threshold=float(gesture_data.get("struggle_joint_motion_threshold", 0.045)),
        struggle_avg_motion_threshold=float(gesture_data.get("struggle_avg_motion_threshold", 0.055)),
        struggle_peak_motion_threshold=float(gesture_data.get("struggle_peak_motion_threshold", 0.11)),
        struggle_min_active_joints=int(gesture_data.get("struggle_min_active_joints", 3)),
    )

    width = int(config.get("vision.width", 640))
    height = int(config.get("vision.height", 480))
    camera = Camera(
        camera_id=int(config.get("vision.camera_id", 0)),
        device_path=str(config.get("vision.device_path", "") or "") or None,
        width=width,
        height=height,
        fps=float(config.get("vision.fps_target", 6)),
    )

    model_path = config.path("vision.pose_model_path", "models/yolov8n-pose.onnx")
    estimator = create_pose_estimator(
        str(config.get("vision.pose_backend", "yolo")),
        min_detection_confidence=float(fall_data.get("min_detection_confidence", 0.5)),
        model_path=model_path,
        fall_config=fall_config,
        gesture_config=gesture_config,
        input_size=int(config.get("vision.pose_input_size", 640)),
    )
    print(f"vision pose backend: {estimator.name}", flush=True)

    bus = create_event_bus_from_config(config, role="push")
    wait_for_subscribers(0.1)
    alerter = VisionAlerter(EmergencyNotifier(bus))
    alert_endpoint = str(config.get("alerts.zmq_endpoint", "ipc:///tmp/wanzhi-vision-alerts.sock"))
    alert_publisher = VisionAlertPublisher(alert_endpoint)

    preview_shm = SharedMemoryManager(
        str(config.get("vision.preview_shm_name", "wanzhi_camera_preview")),
        width=width,
        height=height,
        channels=3,
    )
    preview_every = max(int(config.get("vision.preview_update_every_frames", 1)), 1)
    interval = 1.0 / max(float(config.get("vision.fps_target", 6)), 1.0)
    health_interval = float(config.get("vision.health_interval_seconds", 30))

    fallback_detector = None
    fallback_gesture_detector = None
    if not isinstance(estimator, YoloPoseEstimator):
        from wanzhi.vision.fall_detector import FallDetector

        fallback_detector = FallDetector(fall_config)
        fallback_gesture_detector = DistressGestureDetector(gesture_config)

    last_health = 0.0
    frames = 0
    failed_frames = 0

    try:
        while True:
            frame = camera.read()
            if frame is not None:
                frames += 1
                if isinstance(estimator, YoloPoseEstimator):
                    pose, result, gesture_result, overlay = estimator.analyzer.analyze(frame)
                    backend = pose.backend
                else:
                    pose = estimator.estimate(frame)
                    metadata = dict(pose.metadata or {})
                    metadata["frame_height"] = float(height)
                    result = fallback_detector.update(pose.landmarks, metadata=metadata)
                    gesture_result = fallback_gesture_detector.update(pose.landmarks, metadata=metadata)
                    overlay = frame
                    backend = pose.backend

                if frames % preview_every == 0:
                    preview_shm.write(overlay, color_format="bgr")

                if result.status == "suspicious":
                    payload = _payload(result, backend)
                    bus.emit(Event(EventTypes.VISION_FALL_SUSPECTED, payload, source="vision"))

                if result.should_emit:
                    alerter.fall_detected(result)
                    alert_publisher.publish_fall_detected(
                        confidence=result.confidence,
                        extra={
                            "reason": result.reason or "fall_detected",
                            "duration_seconds": result.duration_seconds,
                            "keypoints_summary": result.keypoints_summary or {},
                        },
                    )
                if gesture_result.should_emit:
                    alerter.distress_detected(gesture_result)
                    alert_publisher.publish_fall_detected(
                        confidence=gesture_result.confidence,
                        extra={
                            "reason": gesture_result.reason or "distress_detected",
                            "duration_seconds": gesture_result.duration_seconds,
                            "keypoints_summary": gesture_result.keypoints_summary or {},
                        },
                    )
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
                print(
                    f"vision health frames={frames} failed={failed_frames} backend={estimator.name}",
                    flush=True,
                )
            time.sleep(interval)
    finally:
        camera.close()
        preview_shm.close()
        preview_shm.unlink()
        alert_publisher.close()


def _payload(result, backend: str) -> dict:
    summary = dict(result.keypoints_summary or {})
    return {
        "status": result.status,
        "confidence": result.confidence,
        "reason": result.reason,
        "duration_seconds": result.duration_seconds,
        "keypoints_summary": summary,
        "consecutive_frames": summary.get("consecutive_frames", 0),
        "matched_rules": summary.get("matched_rules", []),
        "pose_backend": backend,
    }


if __name__ == "__main__":
    main()
