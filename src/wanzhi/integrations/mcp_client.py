from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from wanzhi.core.config import AppConfig


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    command: str
    args: list[str]
    env: dict[str, str] | None = None
    cwd: str | None = None


class MediaMcpClient:
    """Sync wrapper around a stdio MCP media server."""

    def __init__(
        self,
        server: McpServerConfig,
        *,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.server = server
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_config(cls, config: AppConfig, *, server_name: str = "media") -> MediaMcpClient | None:
        if not bool(config.get("mcp.enabled", False)):
            return None

        servers = config.get("mcp.servers") or {}
        if not isinstance(servers, dict):
            return None

        server_cfg = servers.get(server_name)
        if not isinstance(server_cfg, dict):
            return None

        command = str(server_cfg.get("command") or "").strip()
        if not command:
            return None

        raw_args = server_cfg.get("args") or []
        args = [str(item) for item in raw_args] if isinstance(raw_args, list) else []
        env = server_cfg.get("env")
        env_dict = {str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else None
        cwd = server_cfg.get("cwd")
        timeout_seconds = float(config.get("mcp.timeout_seconds", 8))

        return cls(
            McpServerConfig(
                name=server_name,
                command=command,
                args=args,
                env=env_dict,
                cwd=str(cwd) if cwd else None,
            ),
            timeout_seconds=timeout_seconds,
        )

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return asyncio.run(self._call_tool_async(tool_name, arguments or {}))
        except Exception as exc:
            return {"status": "error", "reason": f"MCP 调用失败：{exc}"}

    async def _call_tool_async(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command=self.server.command,
            args=self.server.args,
            env=self.server.env,
            cwd=self.server.cwd,
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments),
                    timeout=self.timeout_seconds,
                )
                return self._normalize_result(result)

    @staticmethod
    def _normalize_result(result: Any) -> dict[str, Any]:
        structured = getattr(result, "structured_content", None)
        if isinstance(structured, dict):
            return structured

        content = getattr(result, "content", None) or []
        for block in content:
            text = getattr(block, "text", None)
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                return {"status": "success", "message": text}
            if isinstance(payload, dict):
                return payload

        if getattr(result, "isError", False):
            return {"status": "error", "reason": "MCP 工具返回错误。"}

        return {"status": "error", "reason": "MCP 工具没有返回可用内容。"}
