from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Medication:
    id: int
    name: str
    dosage: str
    time_of_day: str
