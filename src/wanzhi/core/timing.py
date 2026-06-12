from __future__ import annotations

import time
from typing import Any


def now_seconds() -> float:
    return time.monotonic()


def log_timing(stage: str, started_at: float, **fields: Any) -> None:
    parts = [
        "timing",
        f"stage={_format_value(stage)}",
        f"seconds={now_seconds() - started_at:.3f}",
    ]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={_format_value(value)}")
    print(" ".join(parts), flush=True)


def _format_value(value: Any) -> str:
    text = str(value)
    return "_".join(text.split())
