#!/usr/bin/env python3
"""MCP media server for QQ Music and Ximalaya-style playback lookups."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from wanzhi.integrations.qq_music import QQMusicError, QQMusicProvider

mcp = FastMCP("wanzhi-media")


def _success(*, url: str, title: str, provider: str) -> dict[str, Any]:
    return {
        "status": "success",
        "url": url,
        "title": title,
        "provider": provider,
    }


def _failure(reason: str) -> dict[str, Any]:
    return {
        "status": "error",
        "reason": reason,
    }


@mcp.tool()
def play_music(query: str, mood: str | None = None) -> dict[str, Any]:
    """Search QQ Music and return a playable stream URL."""
    cleaned = query.strip()
    if not cleaned:
        return _failure("没有收到要播放的音乐名称。")
    del mood

    try:
        return QQMusicProvider().resolve_play_url(cleaned)
    except QQMusicError as exc:
        return _failure(str(exc))
    except Exception as exc:
        return _failure(f"QQ 音乐暂时不可用：{exc}")


@mcp.tool()
def play_story(query: str, episode: str | None = None) -> dict[str, Any]:
    """Search Ximalaya and return a playable story stream URL."""
    cleaned = query.strip()
    if not cleaned:
        return _failure("没有收到要播放的故事名称。")

    title = cleaned
    if episode:
        title = f"{cleaned} 第{episode.strip()}集"

    # TODO: replace with real Ximalaya album/track lookup.
    return _success(
        url="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        title=title,
        provider="ximalaya_mock",
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
