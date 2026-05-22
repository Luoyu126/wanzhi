from wanzhi.vision.fall_detector import FallDetectionConfig, FallDetector
from wanzhi.vision.pose import Landmark


def test_fall_detector_triggers_for_horizontal_body() -> None:
    detector = FallDetector(
        FallDetectionConfig(
            fall_aspect_ratio=1.3,
            min_fall_seconds=0,
            required_consecutive_frames=1,
            cooldown_seconds=0,
        )
    )
    landmarks = [Landmark(x=i / 32, y=0.5, visibility=1.0) for i in range(33)]

    result = detector.update(landmarks)

    assert result.status == "fall"
    assert result.should_emit is True


def test_fall_detector_ignores_missing_body() -> None:
    detector = FallDetector(FallDetectionConfig())

    result = detector.update([])

    assert result.status == "normal"
    assert result.should_emit is False
