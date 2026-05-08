def generate_reply(intent: dict) -> str:
    # Stub: replace with Ollama call
    if intent.get("intent") == "medication":
        return "好的，我会在晚上八点提醒你吃药。"
    return "我在听呢，想聊点什么？"
