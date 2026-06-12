from __future__ import annotations

from typing import Any

from wanzhi.actions.emergency import EmergencyActions
from wanzhi.actions.media import MediaActions
from wanzhi.actions.medication import MedicationActions
from wanzhi.core.bus import EventBus
from wanzhi.core.config import AppConfig
from wanzhi.core.events import Event, EventTypes
from wanzhi.integrations.mcp_client import MediaMcpClient
from wanzhi.voice.router import Intent
from wanzhi.voice.tools import ToolResult
from wanzhi.voice.tts_manager import TTSManager


class ActionRegistry:
    def __init__(
        self,
        config: AppConfig,
        bus: EventBus,
        tts: TTSManager | None = None,
        *,
        media: MediaActions | None = None,
        mcp_client: MediaMcpClient | None = None,
    ) -> None:
        self.config = config
        self.medication = MedicationActions(config=config, bus=bus)
        self.emergency = EmergencyActions(bus=bus)
        self.media = media or MediaActions(config)
        self.mcp_client = mcp_client if mcp_client is not None else MediaMcpClient.from_config(config)
        self.tts = tts
        self.bus = bus

    def handle(self, intent: Intent) -> str | None:
        if intent.name == "show_medication":
            return self.medication.show_today()
        if intent.name == "medication_reminder":
            return self.medication.schedule_from_text(intent.slots.get("text", ""))
        if intent.name == "emergency":
            return self.emergency.trigger(intent.slots.get("reason", "语音求救"))
        if intent.name == "goodbye":
            return "好的，我先退下了。有需要再叫我。"
        if intent.name == "change_voice":
            return self._change_voice(
                voice_id=intent.slots.get("voice_id"),
                request_text=intent.slots.get("text", ""),
            )
        if intent.name == "empty":
            return "我没有听清楚，可以再说一遍吗？"
        return None

    def execute_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        if name == "switch_ui_screen":
            target = str(args.get("target_screen") or "")
            if target == "medication":
                reply = self.medication.show_today()
                return ToolResult(observation=reply, spoken_reply=reply)
            if target == "vision":
                self.bus.emit(Event(EventTypes.UI_SHOW_CAMERA, source="voice"))
                reply = "我已经打开摄像头画面。"
                return ToolResult(observation=reply, spoken_reply=reply)
            return ToolResult(observation="未知的目标屏幕。")

        if name == "show_medication_list":
            reply = self.medication.show_today()
            return ToolResult(observation=reply, spoken_reply=reply)

        if name == "open_medication_for_confirmation":
            query = str(args.get("query") or "")
            reply = self.medication.schedule_from_text(query)
            return ToolResult(observation=reply, spoken_reply=reply)

        if name == "trigger_emergency":
            reason = str(args.get("reason") or "语音求救")
            reply = self.emergency.trigger(reason)
            return ToolResult(observation=reply, spoken_reply=reply)

        if name == "change_voice":
            reply = self._change_voice(
                voice_id=args.get("voice_id"),
                request_text=str(args.get("request_text") or ""),
            )
            return ToolResult(observation=reply, spoken_reply=reply)

        if name == "play_music":
            return self._execute_play_music(args)

        if name == "play_story":
            return self._execute_play_story(args)

        if name == "stop_media":
            return self._execute_stop_media(args)

        if name == "end_conversation":
            reply = "好的，我先退下了。有需要再叫我。"
            return ToolResult(observation=reply, spoken_reply=reply, end_session=True)

        return ToolResult(observation=f"未知工具：{name}")

    def _execute_play_music(self, args: dict[str, Any]) -> ToolResult:
        if not self.media.enabled:
            reply = "媒体播放功能还没有启用。"
            return ToolResult(observation=reply, spoken_reply=reply)
        if self.mcp_client is None:
            reply = "媒体服务还没有配置好。"
            return ToolResult(observation=reply, spoken_reply=reply)

        query = str(args.get("query") or "").strip()
        if not query:
            reply = "我没有听清楚想播放哪首歌。"
            return ToolResult(observation=reply, spoken_reply=reply)

        payload = self.mcp_client.call_tool(
            "play_music",
            {
                "query": query,
                "mood": args.get("mood"),
            },
        )
        return self._handle_media_payload(payload, fallback_title=query, kind="music")

    def _execute_play_story(self, args: dict[str, Any]) -> ToolResult:
        if not self.media.enabled:
            reply = "媒体播放功能还没有启用。"
            return ToolResult(observation=reply, spoken_reply=reply)
        if self.mcp_client is None:
            reply = "媒体服务还没有配置好。"
            return ToolResult(observation=reply, spoken_reply=reply)

        query = str(args.get("query") or "").strip()
        if not query:
            reply = "我没有听清楚想播放哪个故事。"
            return ToolResult(observation=reply, spoken_reply=reply)

        payload = self.mcp_client.call_tool(
            "play_story",
            {
                "query": query,
                "episode": args.get("episode"),
            },
        )
        return self._handle_media_payload(payload, fallback_title=query, kind="story")

    def _execute_stop_media(self, args: dict[str, Any]) -> ToolResult:
        del args
        stopped = self.media.stop()
        if stopped:
            reply = "好的，已经停止播放。"
        else:
            reply = "当前没有在播放音乐或故事。"
        return ToolResult(observation=reply, spoken_reply=reply)

    def _handle_media_payload(
        self,
        payload: dict[str, Any],
        *,
        fallback_title: str,
        kind: str,
    ) -> ToolResult:
        if payload.get("status") != "success":
            reason = str(payload.get("reason") or "暂时找不到可播放的内容。")
            return ToolResult(observation=reason, spoken_reply=reason)

        url = str(payload.get("url") or "").strip()
        if not url:
            reply = "找到了内容，但没有拿到播放地址。"
            return ToolResult(observation=reply, spoken_reply=reply)

        title = str(payload.get("title") or fallback_title).strip() or fallback_title
        started = self.media.play_after_delay(url, title=title, kind=kind)
        if not started:
            reply = "播放失败了，可能是播放器没有安装。"
            return ToolResult(observation=reply, spoken_reply=reply)

        if kind == "story":
            reply = f"好的，开始为你播放故事《{title}》。"
        else:
            reply = f"好的，为你播放{title}。"

        observation = f"已开始播放：{title}。"
        return ToolResult(observation=observation, spoken_reply=reply)

    def _change_voice(self, voice_id: str | None, request_text: str) -> str:
        if self.tts is None:
            return "好的，之后我会切换声音。"
        resolved = voice_id or self.tts.resolve_requested_voice(request_text)
        if resolved is None:
            return "我还不确定要换成哪种声音，可以说老年男声、老年女声、小男孩声音或小女孩声音。"
        self.tts.set_voice(resolved)
        return f"好的，已经切换成最接近的{self.tts.describe_voice(resolved)}。"
