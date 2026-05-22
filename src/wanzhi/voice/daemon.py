from __future__ import annotations

import time

from wanzhi.core.bus import JsonlEventBus
from wanzhi.core.config import load_config
from wanzhi.voice.pipeline import VoicePipeline


def main() -> None:
    config = load_config()
    bus = JsonlEventBus(config.path("events.log_path", "data/events.jsonl"))
    pipeline = VoicePipeline(config=config, bus=bus)

    while True:
        try:
            pipeline.run_once()
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"voice daemon error: {exc}")
            time.sleep(2)


if __name__ == "__main__":
    main()
