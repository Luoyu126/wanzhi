from __future__ import annotations

from datetime import date

from wanzhi.core.bus import JsonlEventBus
from wanzhi.core.config import AppConfig
from wanzhi.core.events import Event, EventTypes
from wanzhi.services.medication.repository import MedicationRepository


class MedicationActions:
    def __init__(self, config: AppConfig, bus: JsonlEventBus) -> None:
        self.bus = bus
        self.repo = MedicationRepository(config.path("database.path", "data/wanzhi.db"))

    def show_today(self) -> str:
        items = self.repo.list_due_on(date.today())
        self.bus.emit(Event(EventTypes.UI_SHOW_MEDICATION, source="voice"))
        if not items:
            return "今天暂时没有记录要吃的药。"
        names = "，".join(item["name"] for item in items)
        return f"今天需要吃这些药：{names}。我已经帮你打开药物清单。"

    def schedule_from_text(self, text: str) -> str:
        self.bus.emit(Event(EventTypes.UI_SHOW_MEDICATION, {"query": text}, source="voice"))
        return "我先打开药物清单，你可以在屏幕上确认或添加具体药物和时间。"
