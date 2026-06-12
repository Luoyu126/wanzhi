from __future__ import annotations

import time
from datetime import date, datetime

from wanzhi.core.bus import EventBus
from wanzhi.core.events import Event, EventTypes
from wanzhi.services.medication.repository import MedicationRepository


class MedicationScheduler:
    def __init__(self, repo: MedicationRepository, bus: EventBus) -> None:
        self.repo = repo
        self.bus = bus
        self._emitted: set[tuple[str, int]] = set()

    def tick(self) -> None:
        now = datetime.now()
        current_minute = now.strftime("%H:%M")
        for item in self.repo.list_due_on(date.today()):
            key = (now.date().isoformat(), int(item["id"]))
            if item["time_of_day"] == current_minute and key not in self._emitted:
                self.bus.emit(Event(EventTypes.MEDICATION_REMINDER, item, source="medication"))
                self._emitted.add(key)

    def run_forever(self, interval_seconds: int = 20) -> None:
        while True:
            self.tick()
            time.sleep(interval_seconds)
