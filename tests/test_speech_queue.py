from wanzhi.voice.speech_queue import split_sentences


def test_split_sentences_keeps_short_chunks() -> None:
    assert split_sentences("你好。我是丸智，今天陪着你。") == [
        "你好。",
        "我是丸智，",
        "今天陪着你。",
    ]
