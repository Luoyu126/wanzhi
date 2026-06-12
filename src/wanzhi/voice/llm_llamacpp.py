from __future__ import annotations

import http.client
import json
import re
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from wanzhi.core.timing import log_timing, now_seconds

TOOL_CALL_STARTS = ("<|tool_call|>", "<tool_call>")
TOOL_CALL_ENDS = ("</tool_call|>", "</tool_call>")


@dataclass(frozen=True)
class StreamChunk:
    text: str = ""
    tool_call: dict[str, Any] | None = None
    done: bool = False


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str) -> None:
        super().__init__("localhost")
        self._socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self._socket_path)


class LlamaCppClient:
    """UDS HTTP client for the system-level Wanzhi LLM daemon."""

    def __init__(
        self,
        model_path: Path | None = None,
        *,
        socket_path: str | Path = "/run/wanzhi-llm/llm.sock",
        n_ctx: int = 4096,
        n_threads: int = 4,
        n_gpu_layers: int = 0,
        use_mlock: bool = True,
        temperature: float = 0.4,
        max_tokens: int | None = None,
        timeout_seconds: int = 30,
        startup_wait_seconds: float = 5.0,
    ) -> None:
        self.model_path = model_path
        self.socket_path = Path(socket_path)
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.n_gpu_layers = n_gpu_layers
        self.use_mlock = use_mlock
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.startup_wait_seconds = startup_wait_seconds
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def wait_for_ready(self, *, timeout_seconds: float | None = None) -> bool:
        deadline = time.monotonic() + float(
            timeout_seconds if timeout_seconds is not None else self.startup_wait_seconds
        )
        while time.monotonic() < deadline:
            if self.check_health():
                return True
            time.sleep(0.25)
        return self.check_health()

    def check_health(self) -> bool:
        started = now_seconds()
        try:
            payload = self._request("GET", "/health")
        except (OSError, TimeoutError, json.JSONDecodeError, ValueError):
            self._ready = False
            log_timing("llm.health", started, ready=False)
            return False
        self._ready = bool(payload.get("ready"))
        log_timing("llm.health", started, ready=self._ready)
        return self._ready

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> dict[str, Any] | Iterator[StreamChunk]:
        if not self._ready and not self.check_health():
            raise ConnectionError(
                f"LLM daemon not ready at socket={self.socket_path}. "
                "Ensure wanzhi-llm.service is running."
            )

        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        started = now_seconds()
        response = self._request("POST", "/v1/chat/completions", payload=payload)
        usage = dict(response.get("usage") or {})
        log_timing(
            "llm.chat",
            started,
            stream=stream,
            messages=len(messages),
            tools=len(tools or []),
            prompt_chars=_message_chars(messages),
            response_chars=_response_chars(response),
            max_tokens=self.max_tokens,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        if not stream:
            return response
        return self._response_to_stream(response)

    def _response_to_stream(self, response: dict[str, Any]) -> Iterator[StreamChunk]:
        message = (response.get("choices") or [{}])[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            for call in tool_calls:
                function = call.get("function") or {}
                name = str(function.get("name") or "").strip()
                if not name:
                    continue
                yield StreamChunk(
                    tool_call={
                        "name": name,
                        "arguments": _safe_json_loads(str(function.get("arguments") or "")),
                    }
                )
            yield StreamChunk(done=True)
            return

        content = str(message.get("content") or "")
        parsed = parse_tool_call_text(content)
        if parsed:
            yield StreamChunk(tool_call=parsed)
        elif content.strip():
            yield StreamChunk(text=content)
        yield StreamChunk(done=True)

    def generate(self, prompt: str) -> str:
        response = self.chat(
            [{"role": "user", "content": prompt}],
            stream=False,
        )
        if not isinstance(response, dict):
            return ""
        message = (response.get("choices") or [{}])[0].get("message") or {}
        return str(message.get("content") or "").strip()

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"

        started = now_seconds()
        connection = _UnixHTTPConnection(str(self.socket_path))
        connection.timeout = self.timeout_seconds
        try:
            connection.request(method, path, body=body, headers=headers)
            raw_response = connection.getresponse()
            raw_body = raw_response.read()
        except Exception:
            log_timing("llm.request", started, method=method, path=path, success=False)
            raise
        finally:
            connection.close()

        log_timing(
            "llm.request",
            started,
            method=method,
            path=path,
            status=raw_response.status,
            bytes=len(raw_body),
            success=raw_response.status < 400,
        )
        if raw_response.status >= 400:
            detail = raw_body.decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM request failed status={raw_response.status} body={detail}")

        if not raw_body:
            return {}
        parsed = json.loads(raw_body.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("LLM response must be a JSON object")
        if "error" in parsed:
            raise RuntimeError(str(parsed["error"]))
        return parsed


def _safe_json_loads(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _message_chars(messages: list[dict[str, Any]]) -> int:
    return sum(len(str(message.get("content") or "")) for message in messages)


def _response_chars(response: dict[str, Any]) -> int:
    message = (response.get("choices") or [{}])[0].get("message") or {}
    content = str(message.get("content") or "")
    tool_calls = message.get("tool_calls") or []
    return len(content) + len(json.dumps(tool_calls, ensure_ascii=False))


def parse_tool_call_text(text: str) -> dict[str, Any] | None:
    body = _strip_tool_tags(text)
    if body == text and not _looks_like_tool_payload(body):
        return None

    for candidate in _json_candidates(body):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        name = payload.get("name")
        if not name:
            continue
        arguments = payload.get("arguments") or payload.get("parameters") or {}
        if isinstance(arguments, str):
            arguments = _safe_json_loads(arguments)
        return {"name": str(name), "arguments": dict(arguments)}
    return None


def _strip_tool_tags(text: str) -> str:
    body = text.strip()
    for start in TOOL_CALL_STARTS:
        if start in body:
            body = body.split(start, 1)[1]
            break
    for end in TOOL_CALL_ENDS:
        if end in body:
            body = body.split(end, 1)[0]
            break
    return body.strip()


def _looks_like_tool_payload(text: str) -> bool:
    return "tool_call" in text or '"name"' in text and '"arguments"' in text


def _json_candidates(text: str) -> Iterator[str]:
    body = text.strip()
    if body:
        yield body
    if body.startswith("{{"):
        yield body[1:]
    if body.endswith("}}"):
        yield body[:-1]
    if body.startswith("{{") and body.endswith("}}"):
        yield body[1:-1]

    for start, char in enumerate(body):
        if char != "{":
            continue
        balance = 0
        in_string = False
        escaped = False
        for index in range(start, len(body)):
            current = body[index]
            if escaped:
                escaped = False
                continue
            if current == "\\":
                escaped = True
                continue
            if current == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if current == "{":
                balance += 1
            elif current == "}":
                balance -= 1
                if balance == 0:
                    yield body[start : index + 1]
                    break
