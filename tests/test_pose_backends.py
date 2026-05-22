from wanzhi.vision.pose import create_pose_estimator


def test_null_pose_backend_returns_empty_result() -> None:
    estimator = create_pose_estimator("null")

    result = estimator.estimate(object())

    assert result.backend == "null"
    assert result.landmarks == []
