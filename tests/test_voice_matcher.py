from wanzhi.voice.voice_matcher import looks_like_voice_change, resolve_voice_id


def test_resolve_voice_id_with_fuzzy_phrasing() -> None:
    assert resolve_voice_id("切到老人男生") == "elder_male"
    assert resolve_voice_id("用爷爷声说话") == "elder_male"
    assert resolve_voice_id("想听老一点的女声") == "elder_female"
    assert resolve_voice_id("换小朋友男声") == "child_male"
    assert resolve_voice_id("改成女童声") == "child_female"


def test_looks_like_voice_change_without_fixed_command() -> None:
    assert looks_like_voice_change("老一点的男声")
    assert looks_like_voice_change("小朋友女声")
