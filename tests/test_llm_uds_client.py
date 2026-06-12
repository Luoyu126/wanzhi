from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn, UnixStreamServer

import pytest

from wanzhi.voice.llm_llamacpp import LlamaCppClient, StreamChunk, parse_tool_call_text


class _FakeLlmHandler(BaseHTTPRequestHandler):
    server_version = "FakeLlm/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self.send_error(404)
            return
        self._send_json({"ready": True, "model_path": "models/test.gguf"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        payload = self._read_json()
        messages = payload.get("messages") or []
        user_text = ""
        if messages:
            user_text = str(messages[-1].get("content") or "")
        if "tool" in user_text:
            self._send_json(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '<tool_call>\n{{"name": "change_voice", "arguments": {"voice_id": "elder_male"}}}\n</tool_call>'
                            }
                        }
                    ]
                }
            )
            return
        self._send_json(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"reply": "我运行正常。", "emoji": ""}'
                        }
                    }
                ]
            }
        )

    def log_message(self, fmt: str, *args) -> None:  # type: ignore[no-untyped-def]
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("content-length", "0") or "0")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _FakeUnixServer(ThreadingMixIn, UnixStreamServer):
    daemon_threads = True

    def server_bind(self) -> None:
        Path(str(self.server_address)).unlink(missing_ok=True)
        super().server_bind()


@pytest.fixture
def fake_llm_socket(tmp_path: Path) -> str:
    socket_path = str(tmp_path / "llm.sock")
    server = _FakeUnixServer(socket_path, _FakeLlmHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield socket_path
    finally:
        server.shutdown()
        server.server_close()
        Path(socket_path).unlink(missing_ok=True)


def test_llm_client_health_and_chat(fake_llm_socket: str) -> None:
    client = LlamaCppClient(socket_path=fake_llm_socket, startup_wait_seconds=1)

    assert client.wait_for_ready(timeout_seconds=1) is True
    assert client.ready is True

    response = client.chat([{"role": "user", "content": "你好"}], stream=False)
    assert isinstance(response, dict)
    message = response["choices"][0]["message"]["content"]
    assert "我运行正常" in message


def test_llm_client_stream_converts_tool_call(fake_llm_socket: str) -> None:
    client = LlamaCppClient(socket_path=fake_llm_socket, startup_wait_seconds=1)
    client.wait_for_ready(timeout_seconds=1)

    stream = client.chat([{"role": "user", "content": "please tool"}], stream=True)
    chunks = list(stream)

    assert any(chunk.tool_call for chunk in chunks)
    tool_chunk = next(chunk for chunk in chunks if chunk.tool_call)
    assert tool_chunk.tool_call == {
        "name": "change_voice",
        "arguments": {"voice_id": "elder_male"},
    }
    assert chunks[-1].done is True


def test_llm_client_generate(fake_llm_socket: str) -> None:
    client = LlamaCppClient(socket_path=fake_llm_socket, startup_wait_seconds=1)
    client.wait_for_ready(timeout_seconds=1)

    reply = client.generate("ping")
    assert "我运行正常" in reply


def test_llm_client_not_ready_raises(tmp_path: Path) -> None:
    missing_socket = tmp_path / "missing.sock"
    client = LlamaCppClient(socket_path=missing_socket, startup_wait_seconds=0.1)

    assert client.wait_for_ready(timeout_seconds=0.1) is False
    with pytest.raises(ConnectionError):
        client.chat([{"role": "user", "content": "hello"}], stream=False)


def test_parse_tool_call_text_still_handles_qwen_tags() -> None:
    parsed = parse_tool_call_text(
        '<tool_call>\n{{"name": "change_voice", "arguments": {"voice_id": "elder_male"}}}\n</tool_call>'
    )
    assert parsed == {
        "name": "change_voice",
        "arguments": {"voice_id": "elder_male"},
    }


def test_response_to_stream_chunks_from_plain_text(fake_llm_socket: str) -> None:
    client = LlamaCppClient(socket_path=fake_llm_socket, startup_wait_seconds=1)
    client.wait_for_ready(timeout_seconds=1)

    stream = client.chat([{"role": "user", "content": "hello"}], stream=True)
    chunks = [chunk for chunk in stream if chunk.text or chunk.done]

    assert chunks[0].text == '{"reply": "我运行正常。", "emoji": ""}'
    assert chunks[-1].done is True
    assert isinstance(chunks[0], StreamChunk)
