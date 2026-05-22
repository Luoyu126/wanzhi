from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from wanzhi.voice.voice_matcher import looks_like_voice_change, resolve_voice_id


@dataclass(frozen=True)
class Intent:
    name: str
    slots: dict[str, str] = field(default_factory=dict)


class IntentRouter:
    """Keyword-first router for reliable local commands before falling back to chat."""

    def parse(self, text: str) -> Intent:
        normalized = text.strip()
        if not normalized:
            return Intent("empty")

        if _looks_like_goodbye(normalized):
            return Intent("goodbye", {"text": normalized})
        if any(word in normalized for word in ("药单", "药物清单", "今天吃什么药", "吃什么药")):
            return Intent("show_medication", {"text": normalized})
        if "吃药" in normalized or "服药" in normalized:
            return Intent("medication_reminder", {"text": normalized})
        if any(word in normalized for word in ("报警", "求救", "救命", "紧急")):
            return Intent("emergency", {"reason": normalized})
        voice_id = resolve_voice_id(normalized)
        if voice_id and looks_like_voice_change(normalized):
            return Intent("change_voice", {"text": normalized, "voice_id": voice_id})
        if looks_like_voice_change(normalized):
            return Intent("change_voice", {"text": normalized})

        return Intent("chat", {"text": normalized})


GOODBYE_ALIASES = (
    "再见",
    "拜拜",
    "不用了",
    "先这样",
    "就这样",
    "结束对话",
    "退出",
    "休息吧",
    "没事了",
    "下次再聊",
)


def _looks_like_goodbye(text: str) -> bool:
    compact = text.replace(" ", "")
    if any(alias in compact for alias in GOODBYE_ALIASES):
        return True
    return max(SequenceMatcher(None, compact, alias).ratio() for alias in GOODBYE_ALIASES) >= 0.72
