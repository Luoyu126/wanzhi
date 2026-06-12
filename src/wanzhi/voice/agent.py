from __future__ import annotations

import json
import re
from typing import Any, Callable, Iterator

from wanzhi.core.timing import log_timing, now_seconds
from wanzhi.voice.llm_llamacpp import LlamaCppClient, parse_tool_call_text
from wanzhi.voice.tools import SYSTEM_PROMPT, TOOL_SCHEMAS, AgentTurn, ToolResult

EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]\ufe0f?")


class VoiceAgent:
    """ReAct-style local agent that executes native tools then speaks a confirmation."""

    def __init__(
        self,
        llm: LlamaCppClient,
        tool_executor: Callable[[str, dict[str, Any]], ToolResult],
        *,
        max_steps: int = 4,
    ) -> None:
        self.llm = llm
        self.tool_executor = tool_executor
        self.max_steps = max_steps

    def run_turn(
        self,
        user_text: str,
        *,
        history: list[dict[str, Any]] | None = None,
        on_sentence: Callable[[str], None] | None = None,
    ) -> AgentTurn:
        turn = AgentTurn(user_text=user_text)
        messages = _messages_for_turn(user_text, history)

        for step in range(1, self.max_steps + 1):
            step_started = now_seconds()
            response = self.llm.chat(messages, tools=TOOL_SCHEMAS, stream=False)
            if not isinstance(response, dict):
                log_timing("agent.step", step_started, step=step, outcome="invalid_response")
                break
            message = (response.get("choices") or [{}])[0].get("message") or {}
            tool_calls = message.get("tool_calls") or []
            content = str(message.get("content") or "").strip()

            if tool_calls:
                messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
                for call in tool_calls:
                    function = call.get("function") or {}
                    name = str(function.get("name") or "")
                    arguments = _parse_tool_arguments(function.get("arguments"))
                    tool_started = now_seconds()
                    result = self.tool_executor(name, arguments)
                    log_timing("agent.tool", tool_started, name=name, end_session=result.end_session)
                    if result.end_session:
                        turn.end_session = True
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id") or name,
                            "content": result.observation,
                        }
                    )
                    if result.spoken_reply and not content:
                        turn.final_reply = result.spoken_reply
                if turn.end_session and turn.final_reply:
                    messages.append({"role": "assistant", "content": turn.final_reply})
                    turn.messages = [dict(message) for message in messages]
                    log_timing("agent.step", step_started, step=step, outcome="end_session")
                    return turn
                log_timing("agent.step", step_started, step=step, outcome="tool_calls", tools=len(tool_calls))
                continue

            if content:
                messages.append({"role": "assistant", "content": content})
                turn.final_reply, turn.suggested_emoji = _parse_reply_payload(content)
                if on_sentence:
                    self._stream_sentences(turn.final_reply, on_sentence)
                turn.messages = [dict(message) for message in messages]
                log_timing("agent.step", step_started, step=step, outcome="final", chars=len(turn.final_reply))
                return turn

        fallback = turn.final_reply or "我在呢，你可以再说具体一点。"
        turn.final_reply = fallback
        turn.suggested_emoji = _fallback_emoji(fallback)
        messages.append({"role": "assistant", "content": fallback})
        turn.messages = [dict(message) for message in messages]
        if on_sentence:
            self._stream_sentences(fallback, on_sentence)
        return turn

    def run_turn_streaming(
        self,
        user_text: str,
        *,
        history: list[dict[str, Any]] | None = None,
        on_sentence: Callable[[str], None] | None = None,
        mute_on_tool: Callable[[], None] | None = None,
    ) -> AgentTurn:
        turn = AgentTurn(user_text=user_text)
        messages = _messages_for_turn(user_text, history)

        for step in range(1, self.max_steps + 1):
            step_started = now_seconds()
            stream = self.llm.chat(messages, tools=TOOL_SCHEMAS, stream=True)
            if not isinstance(stream, Iterator):
                log_timing("agent.step", step_started, step=step, outcome="invalid_stream")
                break

            collected = ""
            pending_tool: dict[str, Any] | None = None
            for chunk in stream:
                if chunk.tool_call:
                    if mute_on_tool:
                        mute_on_tool()
                    pending_tool = chunk.tool_call
                    continue
                if chunk.text:
                    collected += chunk.text
                if chunk.done:
                    break

            parsed_tool = parse_tool_call_text(collected)
            if parsed_tool:
                pending_tool = parsed_tool
                collected = ""

            if pending_tool:
                name = str(pending_tool.get("name") or "")
                arguments = dict(pending_tool.get("arguments") or {})
                if mute_on_tool:
                    mute_on_tool()
                tool_started = now_seconds()
                result = self.tool_executor(name, arguments)
                log_timing("agent.tool", tool_started, name=name, end_session=result.end_session)
                if result.end_session:
                    turn.end_session = True
                tool_call_id = f"call_{name}"
                messages.extend(
                    [
                        {
                            "role": "assistant",
                            "content": collected,
                            "tool_calls": [
                                {
                                    "id": tool_call_id,
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": json.dumps(arguments, ensure_ascii=False),
                                    },
                                }
                            ],
                        },
                        {"role": "tool", "tool_call_id": tool_call_id, "content": result.observation},
                    ]
                )
                if turn.end_session:
                    reply = result.spoken_reply or result.observation
                    turn.final_reply = reply
                    turn.suggested_emoji = _fallback_emoji(reply)
                    messages.append({"role": "assistant", "content": reply})
                    turn.messages = [dict(message) for message in messages]
                    if on_sentence:
                        self._stream_sentences(reply, on_sentence)
                    log_timing("agent.step", step_started, step=step, outcome="end_session")
                    return turn
                log_timing("agent.step", step_started, step=step, outcome="tool_call", tool=name)
                continue

            if collected.strip():
                messages.append({"role": "assistant", "content": collected})
                turn.final_reply, turn.suggested_emoji = _parse_reply_payload(collected)
                if on_sentence:
                    self._stream_sentences(turn.final_reply, on_sentence)
                turn.messages = [dict(message) for message in messages]
                log_timing("agent.step", step_started, step=step, outcome="final", chars=len(turn.final_reply))
                return turn

        fallback = turn.final_reply or "我在呢，你可以再说具体一点。"
        turn.final_reply = fallback
        turn.suggested_emoji = _fallback_emoji(fallback)
        messages.append({"role": "assistant", "content": fallback})
        turn.messages = [dict(message) for message in messages]
        if on_sentence:
            self._stream_sentences(fallback, on_sentence)
        return turn

    def _stream_sentences(self, text: str, on_sentence: Callable[[str], None]) -> None:
        from wanzhi.voice.speech_queue import split_sentences

        for sentence in split_sentences(text):
            on_sentence(sentence)

    def _feed_streaming_text(self, token: str, on_sentence: Callable[[str], None]) -> str:
        if not hasattr(self, "_sentence_buffer"):
            self._sentence_buffer = ""
        self._sentence_buffer += token
        if any(p in token for p in "，。！？!?；;"):
            sentence = self._sentence_buffer.strip()
            if sentence:
                on_sentence(sentence)
            self._sentence_buffer = ""
        return self._sentence_buffer


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _messages_for_turn(user_text: str, history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    user_message = {"role": "user", "content": user_text or "用户没有说话。"}
    if not history:
        return [{"role": "system", "content": SYSTEM_PROMPT}, user_message]

    messages = [dict(message) for message in history]
    if not any(message.get("role") == "system" for message in messages):
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    messages.append(user_message)
    return messages


def _parse_reply_payload(raw: str) -> tuple[str, str]:
    text = raw.strip()
    for candidate in _json_candidates(text):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        reply = str(payload.get("reply") or payload.get("text") or "").strip()
        if not reply:
            continue
        emoji = _clean_emoji(payload.get("emoji"))
        return reply, emoji or _fallback_emoji(reply)
    return text, _fallback_emoji(text)


def _json_candidates(text: str) -> Iterator[str]:
    body = text.strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?\s*", "", body)
        body = re.sub(r"\s*```$", "", body)
    if body:
        yield body

    start = body.find("{")
    end = body.rfind("}")
    if 0 <= start < end:
        yield body[start : end + 1]


def _clean_emoji(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    match = EMOJI_RE.search(text)
    return match.group(0) if match else ""


def _fallback_emoji(text: str) -> str:
    return ""
