import numpy as np
import pytest

from wanzhi.core.vision_alerts import VisionAlertPublisher, VisionAlertSubscriber, alert_message_to_event
from wanzhi.core.events import EventTypes
from wanzhi.vision.fall_detector import FallDetectionConfig, FallDetector
from wanzhi.vision.pose import Landmark
from wanzhi.vision.pose_analyzer import _parse_yolo_pose_outputs, build_warmup_tensor
from wanzhi.vision.shared_memory import SharedMemoryManager


def _falling_landmarks(*, hip_y: float = 0.52) -> list[Landmark]:
    landmarks = [Landmark(x=0.5, y=0.5, visibility=1.0) for _ in range(17)]
    landmarks[5] = Landmark(x=0.3, y=0.5, visibility=1.0)
    landmarks[6] = Landmark(x=0.4, y=0.5, visibility=1.0)
    landmarks[11] = Landmark(x=0.6, y=hip_y, visibility=1.0)
    landmarks[12] = Landmark(x=0.7, y=hip_y, visibility=1.0)
    return landmarks


def _falling_metadata(*, frame_height: float = 480.0) -> dict:
    return {
        "bbox": [100, 200, 400, 100],
        "frame_height": frame_height,
    }


def test_fall_detector_triggers_when_two_rules_match() -> None:
    detector = FallDetector(
        FallDetectionConfig(
            required_consecutive_frames=1,
            cooldown_seconds=0,
        )
    )
    landmarks = _falling_landmarks()
    metadata = _falling_metadata()

    result = detector.update(landmarks, metadata=metadata)

    assert result.status == "fall"
    assert result.should_emit is True
    assert "wide_body_aspect_ratio" in (result.keypoints_summary or {}).get("matched_rules", [])


def test_fall_detector_ignores_missing_body() -> None:
    detector = FallDetector(FallDetectionConfig())

    result = detector.update([])

    assert result.status == "normal"
    assert result.should_emit is False


def test_fall_detector_requires_fifteen_consecutive_frames() -> None:
    detector = FallDetector(
        FallDetectionConfig(
            required_consecutive_frames=15,
            cooldown_seconds=0,
        )
    )
    landmarks = _falling_landmarks()
    metadata = _falling_metadata()

    for index in range(14):
        result = detector.update(landmarks, metadata=metadata)
        assert result.status == "suspicious"
        assert result.should_emit is False
        assert (result.keypoints_summary or {}).get("consecutive_frames") == index + 1

    result = detector.update(landmarks, metadata=metadata)
    assert result.status == "fall"
    assert result.should_emit is True
    assert (result.keypoints_summary or {}).get("consecutive_frames") == 15


def test_fall_detector_detects_vertical_velocity() -> None:
    detector = FallDetector(
        FallDetectionConfig(
            required_consecutive_frames=1,
            cooldown_seconds=0,
            vertical_velocity_threshold=0.05,
        )
    )
    metadata = {"bbox": [100, 200, 400, 100], "frame_height": 480.0}
    first = _falling_landmarks(hip_y=0.3)
    second = _falling_landmarks(hip_y=0.5)

    detector.update(first, metadata=metadata)
    result = detector.update(second, metadata=metadata)

    assert result.status == "fall"
    assert "rapid_vertical_drop" in (result.keypoints_summary or {}).get("matched_rules", [])


def test_shared_memory_manager_roundtrip() -> None:
    name = "wanzhi_test_preview_manager"
    manager = SharedMemoryManager(name, width=4, height=2, channels=3)
    from wanzhi.core.frame_shm import SharedMemoryFrameReader

    reader = SharedMemoryFrameReader(name)
    frame = np.arange(4 * 2 * 3, dtype=np.uint8).reshape(2, 4, 3)
    sequence = manager.write(frame)
    read_frame, header = reader.read_if_updated()
    assert sequence == 1
    assert header is not None
    assert read_frame is not None
    assert np.array_equal(read_frame, frame)
    manager.close()
    manager.unlink()
    reader.close()


def test_build_warmup_tensor_matches_yolo_input() -> None:
    tensor = build_warmup_tensor(640, 640)
    assert tensor.shape == (1, 3, 640, 640)
    assert tensor.dtype == np.float32


def test_parse_yolo_pose_outputs_supports_transposed_shape() -> None:
    row = np.zeros(56, dtype=np.float32)
    row[:4] = [10, 20, 110, 120]
    row[4] = 0.9
    row[5:8] = [50, 60, 0.95]
    output = row.reshape(1, 1, 56)
    candidates = _parse_yolo_pose_outputs(output, min_conf=0.5)
    assert len(candidates) == 1
    assert candidates[0]["score"] == pytest.approx(0.9)


def test_vision_alert_pub_sub(tmp_path) -> None:
    endpoint = f"ipc://{tmp_path}/wanzhi-alerts.sock"
    publisher = VisionAlertPublisher(endpoint)
    subscriber = VisionAlertSubscriber(endpoint)
    import time

    time.sleep(0.3)
    publisher.publish_fall_detected(confidence=0.89, extra={"reason": "fall_detected"})
    time.sleep(0.2)
    events = list(subscriber.poll_new())
    assert len(events) == 1
    assert events[0].type == EventTypes.EMERGENCY_FALL_DETECTED
    assert events[0].payload["confidence"] == 0.89
    assert events[0].payload["reason"] == "fall_detected"
    publisher.close()
    subscriber.close()


def test_alert_message_to_event() -> None:
    event = alert_message_to_event(
        {
            "event": EventTypes.EMERGENCY_FALL_DETECTED,
            "timestamp": 1717581600,
            "data": {"confidence": 0.89, "reason": "fall_detected"},
        }
    )
    assert event is not None
    assert event.payload["confidence"] == 0.89


def test_alert_message_to_event_preserves_distress_reason() -> None:
    event = alert_message_to_event(
        {
            "event": EventTypes.EMERGENCY_FALL_DETECTED,
            "timestamp": 1717581600,
            "data": {"confidence": 0.77, "reason": "hand_raise_sos"},
        }
    )
    assert event is not None
    assert event.payload["reason"] == "hand_raise_sos"
    assert event.payload["confidence"] == 0.77
