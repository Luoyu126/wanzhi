from __future__ import annotations

from multiprocessing import Process

from wanzhi.ui.main import main as run_ui
from wanzhi.vision.daemon import main as run_vision
from wanzhi.voice.daemon import main as run_voice


def main() -> None:
    """Start all services in development mode."""

    processes = [
        Process(target=run_voice, name="wanzhi-voice"),
        Process(target=run_vision, name="wanzhi-vision"),
        Process(target=run_ui, name="wanzhi-ui"),
    ]
    for process in processes:
        process.start()
    try:
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        for process in processes:
            process.terminate()


if __name__ == "__main__":
    main()
