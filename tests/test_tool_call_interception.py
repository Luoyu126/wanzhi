from wanzhi.voice.agent import VoiceAgent
from wanzhi.voice.llm_llamacpp import StreamChunk, parse_tool_call_text
from wanzhi.voice.session import VoiceSession
from wanzhi.voice.tools import ToolResult


def test_parse_qwen_tool_call_with_plain_tags_and_double_brace() -> None:
    parsed = parse_tool_call_text(
        '<tool_call>\n{{"name": "change_voice", "arguments": {"voice_id": "elder_male", "request_text": ""}}\n</tool_call>'
    )

    assert parsed == {
        "name": "change_voice",
        "arguments": {"voice_id": "elder_male", "request_text": ""},
    }


def test_agent_intercepts_tool_call_text_before_speaking() -> None:
    class FakeLlm:
        def __init__(self) -> None:
            self.calls = 0

        def chat(self, messages, *, tools=None, stream=False):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return iter(
                    [
                        StreamChunk(
                            text='<tool_call>\n{{"name": "change_voice", "arguments": {"voice_id": "elder_male"}}\n</tool_call>'
                        ),
                        StreamChunk(done=True),
                    ]
                )
            return iter([StreamChunk(text="已经切换好了。"), StreamChunk(done=True)])

    executed: list[tuple[str, dict]] = []
    spoken: list[str] = []

    def execute_tool(name: str, args: dict) -> ToolResult:
        executed.append((name, args))
        return ToolResult(observation="voice changed")

    agent = VoiceAgent(FakeLlm(), execute_tool)
    turn = agent.run_turn_streaming("换成老年男声", on_sentence=spoken.append)

    assert executed == [("change_voice", {"voice_id": "elder_male"})]
    assert turn.final_reply == "已经切换好了。"
    assert spoken == ["已经切换好了。"]


def test_agent_parses_reply_payload_with_emoji_suggestion() -> None:
    class FakeLlm:
        def chat(self, messages, *, tools=None, stream=False):  # type: ignore[no-untyped-def]
            return iter(
                [
                    StreamChunk(text='{"reply": "我在呢，慢慢说。", "emoji": "😊"}'),
                    StreamChunk(done=True),
                ]
            )

    agent = VoiceAgent(FakeLlm(), lambda name, args: ToolResult(observation="unused"))
    spoken: list[str] = []

    turn = agent.run_turn_streaming("你好", on_sentence=spoken.append)

    assert turn.final_reply == "我在呢，慢慢说。"
    assert turn.suggested_emoji == "😊"
    assert spoken == ["我在呢，", "慢慢说。"]


def test_agent_extracts_emoji_from_verbose_suggestion() -> None:
    class FakeLlm:
        def chat(self, messages, *, tools=None, stream=False):  # type: ignore[no-untyped-def]
            return iter(
                [
                    StreamChunk(text='{"reply": "我想一想。", "emoji": "建议表情：🤔"}'),
                    StreamChunk(done=True),
                ]
            )

    agent = VoiceAgent(FakeLlm(), lambda name, args: ToolResult(observation="unused"))

    turn = agent.run_turn_streaming("这个怎么办")

    assert turn.final_reply == "我想一想。"
    assert turn.suggested_emoji == "🤔"


def test_agent_preserves_history_between_turns() -> None:
    class FakeLlm:
        def __init__(self) -> None:
            self.calls: list[list[dict]] = []

        def chat(self, messages, *, tools=None, stream=False):  # type: ignore[no-untyped-def]
            self.calls.append([dict(message) for message in messages])
            if len(self.calls) == 1:
                return iter([StreamChunk(text='{"reply": "我是丸智。", "emoji": ""}'), StreamChunk(done=True)])
            return iter([StreamChunk(text='{"reply": "我可以陪你聊天。", "emoji": ""}'), StreamChunk(done=True)])

    session = VoiceSession()
    agent = VoiceAgent(FakeLlm(), lambda name, args: ToolResult(observation="unused"))

    first_turn = agent.run_turn_streaming("你是谁")
    session.update_from_turn(first_turn)
    second_turn = agent.run_turn_streaming("那你能做什么", history=session.snapshot())

    second_messages = agent.llm.calls[1]
    assert any(message.get("content") == "你是谁" for message in second_messages)
    assert any("我是丸智" in str(message.get("content")) for message in second_messages)
    assert second_turn.final_reply == "我可以陪你聊天。"


def test_agent_turn_messages_include_tool_chain() -> None:
    class FakeLlm:
        def __init__(self) -> None:
            self.calls = 0

        def chat(self, messages, *, tools=None, stream=False):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return iter(
                    [
                        StreamChunk(
                            tool_call={
                                "name": "change_voice",
                                "arguments": {"voice_id": "elder_female"},
                            }
                        ),
                        StreamChunk(done=True),
                    ]
                )
            return iter([StreamChunk(text='{"reply": "声音换好了。", "emoji": ""}'), StreamChunk(done=True)])

    agent = VoiceAgent(FakeLlm(), lambda name, args: ToolResult(observation="voice changed"))
    turn = agent.run_turn_streaming("换个声音")

    roles = [message["role"] for message in turn.messages]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]
    assert turn.messages[2]["tool_calls"][0]["function"]["name"] == "change_voice"
    assert turn.messages[3]["content"] == "voice changed"
    assert "声音换好了" in turn.messages[4]["content"]
