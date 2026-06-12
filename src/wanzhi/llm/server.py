from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn, UnixStreamServer
from typing import Any

from wanzhi.core.config import AppConfig, load_config
from wanzhi.core.timing import log_timing, now_seconds


class LlmState:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.model_path = config.path("llm.model_path", "models/llm/qwen2.5-3b-instruct-q4_k_m.gguf")
        self.n_ctx = int(config.get("llm.n_ctx", 4096))
        self.n_threads = int(config.get("llm.n_threads", 4))
        self.n_gpu_layers = int(config.get("llm.n_gpu_layers", 0))
        self.use_mlock = bool(config.get("llm.use_mlock", True))
        self.temperature = float(config.get("llm.temperature", 0.4))
        self.verbose = bool(config.get("llm.verbose", False))
        self.loaded_at: float | None = None
        self.load_seconds: float | None = None
        self._llm = None
        self._chat_lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._llm is not None

    def load(self) -> None:
        if self._llm is not None:
            return
        if not self.model_path.exists():
            raise FileNotFoundError(f"GGUF model not found: {self.model_path}")

        from llama_cpp import Llama

        started = time.monotonic()
        print(
            "llm server loading model "
            f"path={self.model_path} n_ctx={self.n_ctx} n_threads={self.n_threads} "
            f"use_mlock={self.use_mlock}",
            flush=True,
        )
        self._llm = Llama(
            model_path=str(self.model_path),
            n_ctx=self.n_ctx,
            n_threads=self.n_threads,
            n_gpu_layers=self.n_gpu_layers,
            use_mlock=self.use_mlock,
            verbose=self.verbose,
        )
        self.load_seconds = time.monotonic() - started
        self.loaded_at = time.time()
        print(f"llm server model loaded seconds={self.load_seconds:.3f}", flush=True)

    def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.load()
        assert self._llm is not None
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise ValueError("messages must be a list")
        kwargs: dict[str, Any] = {
            "messages": messages,
            "temperature": float(payload.get("temperature", self.temperature)),
            "stream": False,
        }
        tools = payload.get("tools")
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = payload.get("tool_choice", "auto")
        max_tokens = payload.get("max_tokens")
        if max_tokens is not None:
            kwargs["max_tokens"] = int(max_tokens)
        with self._chat_lock:
            started = now_seconds()
            response = dict(self._llm.create_chat_completion(**kwargs))
        usage = dict(response.get("usage") or {})
        log_timing(
            "llm.server.chat",
            started,
            messages=len(messages),
            tools=len(tools) if isinstance(tools, list) else 0,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        return response

    def health(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "model_path": str(self.model_path),
            "model_exists": self.model_path.exists(),
            "model_size_bytes": self.model_path.stat().st_size if self.model_path.exists() else None,
            "use_mlock": self.use_mlock,
            "n_ctx": self.n_ctx,
            "n_threads": self.n_threads,
            "n_gpu_layers": self.n_gpu_layers,
            "loaded_at": self.loaded_at,
            "load_seconds": self.load_seconds,
            "pid": os.getpid(),
        }


class ThreadingUnixHTTPServer(ThreadingMixIn, UnixStreamServer):
    daemon_threads = True

    def __init__(self, server_address: str, handler_cls, state: LlmState) -> None:  # type: ignore[no-untyped-def]
        self.state = state
        super().__init__(server_address, handler_cls)

    def server_bind(self) -> None:
        socket_path = Path(str(self.server_address))
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        socket_path.unlink(missing_ok=True)
        super().server_bind()
        socket_path.chmod(0o660)


class LlmRequestHandler(BaseHTTPRequestHandler):
    server_version = "WanzhiLlmServer/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(self.server.state.health())  # type: ignore[attr-defined]
            return
        self.send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._read_json()
            if self.path == "/v1/chat/completions":
                response = self.server.state.chat(payload)  # type: ignore[attr-defined]
                self._send_json(response)
                return
            self.send_error(HTTPStatus.NOT_FOUND, "not found")
        except Exception as exc:
            print(f"llm server request failed: {exc}", flush=True)
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"llm server: {fmt % args}", flush=True)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0") or "0")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Wanzhi local LLM daemon over Unix Domain Socket HTTP.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--socket", default=None)
    parser.add_argument("--no-preload", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    socket_path = args.socket or str(config.get("llm.socket_path", "/run/wanzhi-llm/llm.sock"))
    state = LlmState(config)
    if not args.no_preload:
        state.load()

    server = ThreadingUnixHTTPServer(socket_path, LlmRequestHandler, state)
    print(f"llm server listening socket={socket_path} pid={os.getpid()}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        Path(socket_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
