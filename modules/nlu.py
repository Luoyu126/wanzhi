from wanzhi.voice.router import IntentRouter


def parse_intent(text: str) -> dict:
    intent = IntentRouter().parse(text)
    return {"intent": intent.name, "slots": intent.slots}
