from __future__ import annotations


class YoloPoseEstimator:
    name = "yolo"

    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError("YOLO/Hailo pose backend is reserved for the future accelerator path.")
