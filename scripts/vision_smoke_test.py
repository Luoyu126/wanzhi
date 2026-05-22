#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wanzhi.core.config import load_config  # noqa: E402
from wanzhi.vision.camera import Camera  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test the configured vision camera.")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--output", default=str(ROOT / "data" / "test-captures" / "vision-smoke.jpg"))
    args = parser.parse_args()

    config = load_config()
    camera = Camera(
        camera_id=int(config.get("vision.camera_id", 0)),
        device_path=str(config.get("vision.device_path", "") or "") or None,
        width=int(config.get("vision.width", 640)),
        height=int(config.get("vision.height", 480)),
        fps=float(config.get("vision.fps_target", 6)),
    )
    frames = 0
    failed = 0
    deadline = time.monotonic() + args.seconds
    last_frame = None
    try:
        while time.monotonic() < deadline:
            frame = camera.read()
            if frame is None:
                failed += 1
            else:
                frames += 1
                last_frame = frame
        snapshot = None
        if last_frame is not None:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            ok = camera.cv2.imwrite(str(output), last_frame)
            snapshot = str(output) if ok else None
        fps = frames / max(args.seconds, 0.001)
        print(f"vision_smoke frames={frames} failed={failed} fps={fps:.2f} snapshot={snapshot}")
        if frames == 0:
            raise SystemExit(1)
    finally:
        camera.close()


if __name__ == "__main__":
    main()
