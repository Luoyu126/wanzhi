from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

import requests


MUSICU_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
DEFAULT_TIMEOUT_SECONDS = 8.0


class QQMusicError(RuntimeError):
    """Raised when QQ Music search or stream URL resolution fails."""


class HttpSession(Protocol):
    def post(self, url: str, **kwargs: Any): ...


@dataclass(frozen=True)
class QQMusicTrack:
    songmid: str
    media_mid: str
    title: str
    artist: str

    @property
    def display_title(self) -> str:
        if self.artist:
            return f"{self.title} - {self.artist}"
        return self.title


class QQMusicProvider:
    """Small QQ Music web API client backed by a user-provided browser cookie."""

    def __init__(
        self,
        *,
        cookie: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        session: HttpSession | None = None,
    ) -> None:
        self.cookie = (cookie if cookie is not None else os.getenv("QQ_MUSIC_COOKIE", "")).strip()
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def resolve_play_url(self, query: str, *, quality: str = "128") -> dict[str, Any]:
        cleaned = query.strip()
        if not cleaned:
            raise QQMusicError("没有收到要播放的音乐名称。")
        if not self.cookie:
            raise QQMusicError("QQ 音乐 Cookie 未配置，请设置 QQ_MUSIC_COOKIE。")

        track = self._search_first_track(cleaned)
        url = self._resolve_track_url(track, quality=quality)
        return {
            "status": "success",
            "url": url,
            "title": track.display_title,
            "provider": "qq_music",
            "songmid": track.songmid,
        }

    def _search_first_track(self, query: str) -> QQMusicTrack:
        payload = {
            "comm": self._common_payload(),
            "req_1": {
                "module": "music.search.SearchCgiService",
                "method": "DoSearchForQQMusicDesktop",
                "param": {
                    "remoteplace": "txt.yqq.song",
                    "searchid": _search_id(),
                    "search_type": 0,
                    "query": query,
                    "page_num": 1,
                    "num_per_page": 10,
                },
            },
        }
        data = self._post_musicu(payload)
        songs = (
            data.get("req_1", {})
            .get("data", {})
            .get("body", {})
            .get("song", {})
            .get("list", [])
        )
        if not songs:
            raise QQMusicError(f"QQ 音乐没有找到：{query}")

        for song in songs:
            track = _parse_track(song)
            if track is not None:
                return track
        raise QQMusicError(f"QQ 音乐搜索结果没有可播放歌曲：{query}")

    def _resolve_track_url(self, track: QQMusicTrack, *, quality: str) -> str:
        for filename in _candidate_filenames(track.media_mid, quality=quality):
            payload = {
                "comm": self._common_payload(),
                "req_1": {
                    "module": "vkey.GetVkeyServer",
                    "method": "CgiGetVkey",
                    "param": {
                        "guid": _guid(),
                        "songmid": [track.songmid],
                        "songtype": [0],
                        "uin": self._uin(),
                        "loginflag": 1,
                        "platform": "20",
                        "filename": [filename],
                    },
                },
            }
            data = self._post_musicu(payload)
            url = _extract_stream_url(data)
            if url:
                return url

        raise QQMusicError(f"没有拿到《{track.display_title}》的播放地址，可能需要更新 Cookie 或账号权限不足。")

    def _post_musicu(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            MUSICU_URL,
            headers=self._headers(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise QQMusicError("QQ 音乐返回了无法解析的响应。")
        return data

    def _common_payload(self) -> dict[str, Any]:
        return {
            "ct": 24,
            "cv": 0,
            "format": "json",
            "uin": self._uin(),
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Cookie": self.cookie,
            "Origin": "https://y.qq.com",
            "Referer": "https://y.qq.com/",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
        }

    def _uin(self) -> str:
        for key in ("uin", "qqmusic_uin", "wxuin"):
            value = _cookie_value(self.cookie, key)
            if value:
                return value.lstrip("o") or "0"
        return "0"


def _parse_track(song: dict[str, Any]) -> QQMusicTrack | None:
    songmid = str(song.get("mid") or song.get("songmid") or "").strip()
    media_mid = str((song.get("file") or {}).get("media_mid") or song.get("media_mid") or songmid).strip()
    title = str(song.get("name") or song.get("songname") or "").strip()
    singers = song.get("singer") or []
    artist = "、".join(str(item.get("name", "")).strip() for item in singers if isinstance(item, dict)).strip("、")
    if not songmid or not media_mid or not title:
        return None
    return QQMusicTrack(songmid=songmid, media_mid=media_mid, title=title, artist=artist)


def _candidate_filenames(media_mid: str, *, quality: str) -> list[str]:
    candidates = {
        "m4a": [f"C400{media_mid}.m4a"],
        "128": [f"M500{media_mid}.mp3", f"C400{media_mid}.m4a"],
        "320": [f"M800{media_mid}.mp3", f"M500{media_mid}.mp3", f"C400{media_mid}.m4a"],
        "flac": [f"F000{media_mid}.flac", f"M800{media_mid}.mp3", f"M500{media_mid}.mp3"],
    }
    return candidates.get(quality, candidates["128"])


def _extract_stream_url(data: dict[str, Any]) -> str | None:
    result = data.get("req_1", {}).get("data", {})
    items = result.get("midurlinfo") or []
    sip = result.get("sip") or []
    for item in items:
        purl = str(item.get("purl") or "").strip()
        if not purl:
            continue
        if purl.startswith("http"):
            return purl
        base = str(sip[0]).rstrip("/") if sip else "https://isure.stream.qqmusic.qq.com"
        return f"{base}/{purl.lstrip('/')}"
    return None


def _cookie_value(cookie: str, key: str) -> str:
    match = re.search(rf"(?:^|;\s*){re.escape(key)}=([^;]+)", cookie)
    return match.group(1).strip() if match else ""


def _guid() -> str:
    return str(random.randint(10_000_000, 99_999_999))


def _search_id() -> str:
    return f"{int(time.time() * 1000)}{random.randint(1000, 9999)}"
