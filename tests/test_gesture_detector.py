from wanzhi.vision.gesture_detector import DistressGestureDetector, GestureDetectionConfig
from wanzhi.vision.pose import Landmark


def _standing_landmarks() -> list[Landmark]:
    landmarks = [Landmark(x=0.5, y=0.5, visibility=1.0) for _ in range(17)]
    landmarks[5] = Landmark(x=0.42, y=0.40, visibility=1.0)
    landmarks[6] = Landmark(x=0.58, y=0.40, visibility=1.0)
    landmarks[7] = Landmark(x=0.38, y=0.52, visibility=1.0)
    landmarks[8] = Landmark(x=0.62, y=0.52, visibility=1.0)
    landmarks[9] = Landmark(x=0.35, y=0.64, visibility=1.0)
    landmarks[10] = Landmark(x=0.65, y=0.64, visibility=1.0)
    landmarks[11] = Landmark(x=0.45, y=0.66, visibility=1.0)
    landmarks[12] = Landmark(x=0.55, y=0.66, visibility=1.0)
    return landmarks


def _raised_hand_landmarks() -> list[Landmark]:
    landmarks = _standing_landmarks()
    landmarks[7] = Landmark(x=0.38, y=0.36, visibility=1.0)
    landmarks[9] = Landmark(x=0.36, y=0.28, visibility=1.0)
    return landmarks


def _wave_landmarks(wrist_x: float) -> list[Landmark]:
    landmarks = _standing_landmarks()
    landmarks[7] = Landmark(x=0.39, y=0.43, visibility=1.0)
    landmarks[9] = Landmark(x=wrist_x, y=0.43, visibility=1.0)
    return landmarks


def _struggle_landmarks(offset: float) -> list[Landmark]:
    landmarks = _standing_landmarks()
    for index in (5, 6, 7, 8, 9, 10):
        point = landmarks[index]
        landmarks[index] = Landmark(x=point.x + offset, y=point.y - offset / 2, visibility=1.0)
    return landmarks


def test_gesture_detector_triggers_for_raised_hand_sos() -> None:
    detector = DistressGestureDetector(
        GestureDetectionConfig(required_consecutive_frames=2, cooldown_seconds=0)
    )

    first = detector.update(_raised_hand_landmarks())
    second = detector.update(_raised_hand_landmarks())

    assert first.status == "suspicious"
    assert second.status == "distress"
    assert second.reason == "hand_raise_sos"
    assert second.should_emit is True


def test_gesture_detector_triggers_for_arm_wave_sos() -> None:
    detector = DistressGestureDetector(
        GestureDetectionConfig(
            required_consecutive_frames=1,
            cooldown_seconds=0,
            wave_min_points=4,
            wave_min_horizontal_range=0.12,
            wave_min_direction_changes=2,
        )
    )

    result = None
    for wrist_x in (0.45, 0.62, 0.46, 0.63):
        result = detector.update(_wave_landmarks(wrist_x))

    assert result is not None
    assert result.status == "distress"
    assert result.reason == "arm_wave_sos"
    assert result.should_emit is True


def test_gesture_detector_triggers_for_abnormal_struggle() -> None:
    detector = DistressGestureDetector(
        GestureDetectionConfig(
            required_consecutive_frames=1,
            cooldown_seconds=0,
            wave_min_points=99,
            struggle_window_frames=3,
            struggle_min_frames=3,
            struggle_avg_motion_threshold=0.04,
            struggle_peak_motion_threshold=0.08,
        )
    )

    result = None
    for offset in (0.0, 0.12, -0.12, 0.12):
        result = detector.update(_struggle_landmarks(offset))

    assert result is not None
    assert result.status == "distress"
    assert result.reason == "abnormal_struggle"
    assert result.should_emit is True


def test_gesture_detector_ignores_normal_standing_pose() -> None:
    detector = DistressGestureDetector(
        GestureDetectionConfig(required_consecutive_frames=1, cooldown_seconds=0)
    )

    result = detector.update(_standing_landmarks())

    assert result.status == "normal"
    assert result.should_emit is False


def test_gesture_detector_respects_cooldown() -> None:
    detector = DistressGestureDetector(
        GestureDetectionConfig(required_consecutive_frames=1, cooldown_seconds=60)
    )

    first = detector.update(_raised_hand_landmarks())
    second = detector.update(_raised_hand_landmarks())

    assert first.status == "distress"
    assert first.should_emit is True
    assert second.status == "suspicious"
    assert second.should_emit is False
