from __future__ import annotations

import time

from wanzhi.core.alert_listener import VisionAlertListener
from wanzhi.core.bus import create_event_bus_from_config, wait_for_subscribers
from wanzhi.core.config import load_config
from wanzhi.voice.pipeline import VoicePipeline


def main() -> None:
    config = load_config()
    bus = create_event_bus_from_config(config, role="push")
    wait_for_subscribers(0.1)
    pipeline = VoicePipeline(config=config, bus=bus)
    alert_endpoint = str(config.get("alerts.zmq_endpoint", "ipc:///tmp/wanzhi-vision-alerts.sock"))
    alert_listener = VisionAlertListener(alert_endpoint, pipeline.handle_emergency_alert)

    try:
        while True:
            try:
                pipeline.run_once()
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(f"voice daemon error: {exc}")
                time.sleep(2)
    finally:
        alert_listener.close()


if __name__ == "__main__":
    main()
