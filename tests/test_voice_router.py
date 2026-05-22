from wanzhi.voice.router import IntentRouter


def test_router_detects_medication_screen() -> None:
    intent = IntentRouter().parse("打开药物清单")

    assert intent.name == "show_medication"


def test_router_detects_emergency() -> None:
    intent = IntentRouter().parse("帮我报警")

    assert intent.name == "emergency"


def test_router_detects_specific_voice_change() -> None:
    intent = IntentRouter().parse("换成小女孩声音")

    assert intent.name == "change_voice"
    assert intent.slots["voice_id"] == "child_female"


def test_router_detects_elder_male_voice_change() -> None:
    intent = IntentRouter().parse("切换到老年男声")

    assert intent.name == "change_voice"
    assert intent.slots["voice_id"] == "elder_male"


def test_router_detects_fuzzy_voice_change() -> None:
    intent = IntentRouter().parse("帮我改成老人男生")

    assert intent.name == "change_voice"
    assert intent.slots["voice_id"] == "elder_male"


def test_router_detects_goodbye() -> None:
    assert IntentRouter().parse("再见").name == "goodbye"
    assert IntentRouter().parse("不用了先这样").name == "goodbye"
