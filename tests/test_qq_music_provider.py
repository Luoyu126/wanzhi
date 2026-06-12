from __future__ import annotations

import json
from typing import Any

import pytest

from wanzhi.integrations.qq_music import QQMusicError, QQMusicProvider


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        return FakeResponse(self.responses.pop(0))


def test_qq_music_provider_requires_cookie() -> None:
    provider = QQMusicProvider(cookie="", session=FakeSession([]))

    with pytest.raises(QQMusicError, match="Cookie"):
        provider.resolve_play_url("周杰伦")


def test_qq_music_provider_searches_and_resolves_url() -> None:
    session = FakeSession(
        [
            {
                "req_1": {
                    "data": {
                        "body": {
                            "song": {
                                "list": [
                                    {
                                        "mid": "song_mid_1",
                                        "name": "月亮代表我的心",
                                        "singer": [{"name": "邓丽君"}],
                                        "file": {"media_mid": "media_mid_1"},
                                    }
                                ]
                            }
                        }
                    }
                }
            },
            {
                "req_1": {
                    "data": {
                        "midurlinfo": [{"purl": "M500media_mid_1.mp3?vkey=abc"}],
                        "sip": ["https://isure.stream.qqmusic.qq.com/"],
                    }
                }
            },
        ]
    )
    provider = QQMusicProvider(
        cookie="wxuin=1152921500000000000; qqmusic_key=fake; qm_keyst=fake",
        session=session,
    )

    result = provider.resolve_play_url("月亮代表我的心")

    assert result == {
        "status": "success",
        "url": "https://isure.stream.qqmusic.qq.com/M500media_mid_1.mp3?vkey=abc",
        "title": "月亮代表我的心 - 邓丽君",
        "provider": "qq_music",
        "songmid": "song_mid_1",
    }
    search_payload = json.loads(session.requests[0]["data"].decode("utf-8"))
    assert search_payload["req_1"]["param"]["query"] == "月亮代表我的心"
    vkey_payload = json.loads(session.requests[1]["data"].decode("utf-8"))
    assert vkey_payload["req_1"]["param"]["songmid"] == ["song_mid_1"]
    assert vkey_payload["comm"]["uin"] == "1152921500000000000"


def test_qq_music_provider_tries_fallback_quality() -> None:
    session = FakeSession(
        [
            {
                "req_1": {
                    "data": {
                        "body": {
                            "song": {
                                "list": [
                                    {
                                        "mid": "song_mid_1",
                                        "name": "测试歌曲",
                                        "singer": [],
                                        "file": {"media_mid": "media_mid_1"},
                                    }
                                ]
                            }
                        }
                    }
                }
            },
            {"req_1": {"data": {"midurlinfo": [{"purl": ""}], "sip": []}}},
            {
                "req_1": {
                    "data": {
                        "midurlinfo": [{"purl": "C400media_mid_1.m4a?vkey=abc"}],
                        "sip": ["https://isure.stream.qqmusic.qq.com/"],
                    }
                }
            },
        ]
    )
    provider = QQMusicProvider(cookie="uin=o12345; qqmusic_key=fake", session=session)

    result = provider.resolve_play_url("测试歌曲", quality="128")

    assert result["url"].endswith("C400media_mid_1.m4a?vkey=abc")
    first_vkey = json.loads(session.requests[1]["data"].decode("utf-8"))
    second_vkey = json.loads(session.requests[2]["data"].decode("utf-8"))
    assert first_vkey["req_1"]["param"]["filename"] == ["M500media_mid_1.mp3"]
    assert second_vkey["req_1"]["param"]["filename"] == ["C400media_mid_1.m4a"]


def test_qq_music_provider_reports_empty_search_result() -> None:
    session = FakeSession([{"req_1": {"data": {"body": {"song": {"list": []}}}}}])
    provider = QQMusicProvider(cookie="qqmusic_key=fake", session=session)

    with pytest.raises(QQMusicError, match="没有找到"):
        provider.resolve_play_url("不存在的歌")
