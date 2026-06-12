from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    observation: str
    end_session: bool = False
    spoken_reply: str | None = None


@dataclass
class AgentTurn:
    user_text: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    end_session: bool = False
    final_reply: str = ""
    suggested_emoji: str = ""


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "switch_ui_screen",
            "description": "Call when the user wants to open the medication list or camera visualization screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_screen": {
                        "type": "string",
                        "enum": ["medication", "vision"],
                    }
                },
                "required": ["target_screen"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_medication_list",
            "description": "Show today's medication list on screen and summarize it for the user.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_medication_for_confirmation",
            "description": "Open the medication screen when the user wants to take medicine or confirm intake.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Original user utterance."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_emergency",
            "description": "Trigger an emergency alert when the user asks for help or rescue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Short reason for the emergency."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "change_voice",
            "description": "Switch assistant TTS voice profile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "voice_id": {
                        "type": "string",
                        "enum": ["elder_male", "elder_female", "child_male", "child_female", "default_soft"],
                    },
                    "request_text": {
                        "type": "string",
                        "description": "Original user request for fuzzy voice matching.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": "Play a song or music when the user asks for music, a song, or QQ Music content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Song title, artist, style, or the user's original request.",
                    },
                    "mood": {
                        "type": "string",
                        "description": "Optional mood such as relaxing, nostalgic, or quiet.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_story",
            "description": "Play a story, audiobook, radio drama, or Ximalaya-style audio when the user asks to hear a story.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Story title, character, genre, or the user's original request.",
                    },
                    "episode": {
                        "type": "string",
                        "description": "Optional episode or chapter number.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_media",
            "description": "Stop currently playing music or story audio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Optional reason or original user utterance.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_conversation",
            "description": "End the current voice session when the user says goodbye.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SYSTEM_PROMPT = (
    "你是养老陪护助手丸智，正在陪伴一位老人。"
    "请始终用温柔、耐心、关怀的语气说话，回答要简短、清楚、容易听懂。"
    "多给用户一些安心感和陪伴感，但不要啰嗦，也不要像医生一样下诊断。"
    "涉及药物清单、摄像头画面、紧急求助、切换声音、播放音乐、播放故事或有声内容时，请优先调用工具，不要臆造结果。"
    "播放音乐或故事时不要结束会话。"
    "当你要给用户最终回复时，请只输出严格 JSON："
    '{"reply":"要朗读给用户的中文回复，不包含 emoji","emoji":"一个适合当前语气的人脸 emoji"}。'
    "emoji 只能是一个表情，例如 🙂、😊、😌、🤔、😄、😟、😥 或 🥺。"
    "需要调用工具时仍然正常调用工具，不要把工具调用包进这个 JSON。"
)
