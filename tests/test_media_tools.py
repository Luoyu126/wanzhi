from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from wanzhi.actions.media import MediaActions
from wanzhi.actions.registry import ActionRegistry
from wanzhi.core.bus import JsonlEventBus
from wanzhi.core.config import AppConfig
from wanzhi.voice.tools import TOOL_SCHEMAS


@dataclass
class FakeMediaActions:
    enabled: bool = True
    start_delay_seconds: float = 0.0
    play_calls: list[dict[str, str]] = field(default_factory=list)
    stop_calls: int = 0

    def play_after_delay(self, url: str, *, title: str = "", kind: str = "music") -> bool:
        self.play_calls.append({"url": url, "title": title, "kind": kind})
        return True

    def stop(self) -> bool:
        self.stop_calls += 1
        return True


@dataclass
class FakeMcpClient:
    responses: dict[str, dict[str, Any]]

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        del arguments
        return self.responses[tool_name]


def _registry(
    tmp_path,
    *,
    media: FakeMediaActions | None = None,
    mcp_client: FakeMcpClient | None = None,
    media_enabled: bool = True,
    mcp_enabled: bool = True,
) -> tuple[ActionRegistry, FakeMediaActions, FakeMcpClient | None]:
    bus = JsonlEventBus(tmp_path / "events.jsonl")
    config = AppConfig(
        data={
            "database": {"path": str(tmp_path / "wanzhi.db")},
            "media": {"enabled": media_enabled},
            "mcp": {"enabled": mcp_enabled},
        },
        root=tmp_path,
    )
    fake_media = media or FakeMediaActions()
    fake_mcp = mcp_client or FakeMcpClient(
        responses={
            "play_music": {
                "status": "success",
                "url": "https://example.com/song.mp3",
                "title": "月亮代表我的心",
                "provider": "qq_music_mock",
            },
            "play_story": {
                "status": "success",
                "url": "https://example.com/story.mp3",
                "title": "西游记",
                "provider": "ximalaya_mock",
            },
        }
    )
    registry = ActionRegistry(
        config=config,
        bus=bus,
        media=fake_media,
        mcp_client=fake_mcp,
    )
    return registry, fake_media, fake_mcp


def test_tool_schemas_include_media_tools() -> None:
    names = [schema["function"]["name"] for schema in TOOL_SCHEMAS]
    assert "play_music" in names
    assert "play_story" in names
    assert "stop_media" in names


def test_execute_tool_play_music(tmp_path) -> None:
    registry, media, _ = _registry(tmp_path)

    result = registry.execute_tool("play_music", {"query": "月亮代表我的心", "mood": "轻松"})

    assert result.end_session is False
    assert "月亮代表我的心" in result.spoken_reply
    assert media.play_calls == [
        {
            "url": "https://example.com/song.mp3",
            "title": "月亮代表我的心",
            "kind": "music",
        }
    ]


def test_execute_tool_play_story(tmp_path) -> None:
    registry, media, _ = _registry(tmp_path)

    result = registry.execute_tool("play_story", {"query": "西游记", "episode": "1"})

    assert result.end_session is False
    assert "西游记" in result.spoken_reply
    assert media.play_calls[0]["kind"] == "story"


def test_execute_tool_play_story_handles_mcp_failure(tmp_path) -> None:
    fake_mcp = FakeMcpClient(
        responses={
            "play_story": {"status": "error", "reason": "暂时找不到这个故事。"},
        }
    )
    registry, media, _ = _registry(tmp_path, mcp_client=fake_mcp)

    result = registry.execute_tool("play_story", {"query": "不存在的故事"})

    assert "暂时找不到这个故事" in result.observation
    assert media.play_calls == []


def test_execute_tool_stop_media(tmp_path) -> None:
    registry, media, _ = _registry(tmp_path)

    result = registry.execute_tool("stop_media", {"reason": "别放了"})

    assert media.stop_calls == 1
    assert "停止播放" in result.spoken_reply


def test_media_actions_play_after_delay_uses_timer(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    scheduled: list[tuple[float, object]] = []

    class FakeTimer:
        def __init__(self, delay: float, callback) -> None:
            scheduled.append((delay, callback))
            self.daemon = False

        def start(self) -> None:
            callback = scheduled[-1][1]
            callback()

    monkeypatch.setattr("wanzhi.actions.media.threading.Timer", FakeTimer)
    monkeypatch.setattr(
        "wanzhi.actions.media.MediaActions.play_url",
        lambda self, url, *, title="", kind="music": True,
    )

    config = AppConfig(data={"media": {"enabled": True, "start_delay_seconds": 1.5}}, root=tmp_path)
    media = MediaActions(config)
    assert media.play_after_delay("https://example.com/song.mp3", title="测试", kind="music") is True
    assert scheduled[0][0] == 1.5
