from wanzhi.vision.fall_detector import FallDetectionConfig, FallDetector
from wanzhi.vision.pose import Landmark


def _falling_landmarks(*, hip_y: float = 0.52) -> list[Landmark]:
    landmarks = [Landmark(x=0.5, y=0.5, visibility=1.0) for _ in range(17)]
    landmarks[5] = Landmark(x=0.3, y=0.5, visibility=1.0)
    landmarks[6] = Landmark(x=0.4, y=0.5, visibility=1.0)
    landmarks[11] = Landmark(x=0.6, y=hip_y, visibility=1.0)
    landmarks[12] = Landmark(x=0.7, y=hip_y, visibility=1.0)
    return landmarks


def test_fall_detector_triggers_for_horizontal_body() -> None:
    detector = FallDetector(
        FallDetectionConfig(
            required_consecutive_frames=1,
            cooldown_seconds=0,
        )
    )
    landmarks = _falling_landmarks()
    metadata = {"bbox": [100, 200, 400, 100], "frame_height": 480.0}

    result = detector.update(landmarks, metadata=metadata)

    assert result.status == "fall"
    assert result.should_emit is True


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
    metadata = {"bbox": [100, 200, 400, 100], "frame_height": 480.0}

    for index in range(14):
        result = detector.update(landmarks, metadata=metadata)
        assert result.status == "suspicious"
        assert result.should_emit is False
        assert (result.keypoints_summary or {}).get("consecutive_frames") == index + 1

    result = detector.update(landmarks, metadata=metadata)
    assert result.status == "fall"
    assert result.should_emit is True
    assert (result.keypoints_summary or {}).get("consecutive_frames") == 15
