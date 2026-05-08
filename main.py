from __future__ import annotations

from modules.llm import generate_reply
from modules.nlu import parse_intent
from modules.stt import listen_text
from modules.tts import speak_text
from modules.wake_word import wait_wake_word


def main() -> None:
    wait_wake_word()
    text = listen_text()
    intent = parse_intent(text)
    reply = generate_reply(intent)
    speak_text(reply)


if __name__ == "__main__":
    main()
