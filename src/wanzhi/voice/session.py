from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from wanzhi.voice.tools import AgentTurn, SYSTEM_PROMPT


@dataclass
class VoiceSession:
    system_prompt: str = SYSTEM_PROMPT
    max_messages: int = 24
    messages: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.messages:
            self.reset()

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def snapshot(self) -> list[dict[str, Any]]:
        return [dict(message) for message in self.messages]

    def update_from_turn(self, turn: AgentTurn) -> None:
        if not turn.messages:
            return
        self.messages = self._trim([dict(message) for message in turn.messages])

    def _trim(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        system_messages = [message for message in messages if message.get("role") == "system"]
        system = system_messages[:1] or [{"role": "system", "content": self.system_prompt}]
        non_system = [message for message in messages if message.get("role") != "system"]
        keep = max(1, self.max_messages - len(system))
        return system + non_system[-keep:]
