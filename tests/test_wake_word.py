from wanzhi.voice.wake import matches_wake_word, normalize_wake_text


def test_wake_word_matches_exact_phrase() -> None:
    assert matches_wake_word("你好，小丸子")


def test_wake_word_matches_common_asr_confusions() -> None:
    assert matches_wake_word("你要 小丸纸")
    assert matches_wake_word("您好 小玩子")
    assert matches_wake_word("你好 小圆子")


def test_wake_word_rejects_unrelated_text() -> None:
    assert not matches_wake_word("今天晚上提醒我吃药")


def test_wake_text_normalization() -> None:
    assert normalize_wake_text("你要，小丸纸！") == "你好小丸子"
