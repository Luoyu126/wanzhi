def generate_reply(intent: dict) -> str:
    if intent.get("intent") in {"show_medication", "medication_reminder"}:
        return "好的，我帮你打开药物清单。"
    if intent.get("intent") == "emergency":
        return "我已经记录紧急情况。"
    return "我在听呢，想聊点什么？"
