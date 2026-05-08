def parse_intent(text: str) -> dict:
    # Stub: replace with RASA NLU
    if "吃药" in text:
        return {"intent": "medication", "slots": {"time": "20:00"}}
    return {"intent": "chat", "slots": {"text": text}}
