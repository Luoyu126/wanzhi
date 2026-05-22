#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wanzhi.core.bus import JsonlEventBus  # noqa: E402
from wanzhi.core.config import load_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch Wanzhi JSONL events.")
    parser.add_argument("--type", default="emergency.fall_detected")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    config = load_config()
    bus = JsonlEventBus(config.path("events.log_path", "data/events.jsonl"))
    while True:
        for event in bus.poll_new():
            if args.type == "*" or event.type == args.type:
                print(json.dumps(event.to_dict(), ensure_ascii=False), flush=True)
                if args.once:
                    return
        time.sleep(0.5)


if __name__ == "__main__":
    main()
