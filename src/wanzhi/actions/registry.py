from __future__ import annotations

from wanzhi.actions.emergency import EmergencyActions
from wanzhi.actions.medication import MedicationActions
from wanzhi.core.bus import JsonlEventBus
from wanzhi.core.config import AppConfig
from wanzhi.voice.tts_manager import TTSManager
from wanzhi.voice.router import Intent


class ActionRegistry:
    def __init__(self, config: AppConfig, bus: JsonlEventBus, tts: TTSManager | None = None) -> None:
        self.medication = MedicationActions(config=config, bus=bus)
        self.emergency = EmergencyActions(bus=bus)
        self.tts = tts

    def handle(self, intent: Intent) -> str | None:
        if intent.name == "show_medication":
            return self.medication.show_today()
        if intent.name == "medication_reminder":
            return self.medication.schedule_from_text(intent.slots.get("text", ""))
        if intent.name == "emergency":
            return self.emergency.trigger(intent.slots.get("reason", "语音求救"))
        if intent.name == "goodbye":
            return "好的，我先退下了。有需要再叫我。"
        if intent.name == "change_voice":
            if self.tts is None:
                return "好的，之后我会切换声音。"
            voice_id = intent.slots.get("voice_id") or self.tts.resolve_requested_voice(
                intent.slots.get("text", "")
            )
            if voice_id is None:
                return "我还不确定要换成哪种声音，可以说老年男声、老年女声、小男孩声音或小女孩声音。"
            self.tts.set_voice(voice_id)
            return f"好的，已经切换成{self.tts.voices[voice_id].get('label', voice_id)}。"
        if intent.name == "empty":
            return "我没有听清楚，可以再说一遍吗？"
        return None
