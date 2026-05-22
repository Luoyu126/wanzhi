from __future__ import annotations

import re
from difflib import SequenceMatcher


VOICE_ALIASES: dict[str, tuple[str, ...]] = {
    "elder_male": (
        "老年男声",
        "老人男声",
        "老年男性",
        "老人男性",
        "老爷爷",
        "爷爷声",
        "男声老一点",
        "老一点的男声",
        "成熟男声",
    ),
    "elder_female": (
        "老年女声",
        "老人女声",
        "老年女性",
        "老人女性",
        "老奶奶",
        "奶奶声",
        "女声老一点",
        "老一点的女声",
        "成熟女声",
    ),
    "child_male": (
        "童年男声",
        "儿童男声",
        "小男孩",
        "男孩声",
        "小朋友男声",
        "孩子男声",
        "男童声",
    ),
    "child_female": (
        "童年女声",
        "儿童女声",
        "小女孩",
        "女孩声",
        "小朋友女声",
        "孩子女声",
        "女童声",
    ),
    "default_soft": (
        "温柔女声",
        "默认声音",
        "普通女声",
        "柔和声音",
    ),
}

VOICE_ACTION_ALIASES = (
    "换声音",
    "切换声音",
    "改声音",
    "换成",
    "切换到",
    "改成",
    "使用",
    "变成",
    "声音",
    "声线",
)


def resolve_voice_id(text: str, available_voice_ids: set[str] | None = None, threshold: float = 0.58) -> str | None:
    normalized = normalize_voice_text(text)
    if not normalized:
        return None

    available = available_voice_ids or set(VOICE_ALIASES)
    best_voice: str | None = None
    best_score = 0.0
    for voice_id, aliases in VOICE_ALIASES.items():
        if voice_id not in available:
            continue
        for alias in aliases:
            alias_norm = normalize_voice_text(alias)
            score = _score(normalized, alias_norm)
            if score > best_score:
                best_score = score
                best_voice = voice_id

    if best_score >= threshold:
        return best_voice
    return None


def looks_like_voice_change(text: str) -> bool:
    normalized = normalize_voice_text(text)
    if not normalized:
        return False
    if any(normalize_voice_text(alias) in normalized for alias in VOICE_ACTION_ALIASES):
        return True
    return resolve_voice_id(normalized, threshold=0.66) is not None


def normalize_voice_text(text: str) -> str:
    compact = re.sub(r"[\s,，。.!！?？、：:；;\"'“”‘’\-]+", "", text.strip().lower())
    replacements = {
        "男生": "男声",
        "女生": "女声",
        "小孩": "孩子",
        "孩童": "儿童",
        "老头": "老年男声",
        "老太": "老年女声",
        "姥姥": "老年女声",
        "姥爷": "老年男声",
    }
    for old, new in replacements.items():
        compact = compact.replace(old, new)
    return compact


def _score(text: str, alias: str) -> float:
    if not text or not alias:
        return 0.0
    if alias in text:
        return 1.0
    ratio = SequenceMatcher(None, text, alias).ratio()
    window_ratio = _best_window_ratio(text, alias)
    token_bonus = _semantic_bonus(text, alias)
    return max(ratio, window_ratio, token_bonus)


def _best_window_ratio(text: str, alias: str) -> float:
    best = 0.0
    for size in range(max(2, len(alias) - 2), len(alias) + 3):
        for start in range(0, max(1, len(text) - size + 1)):
            best = max(best, SequenceMatcher(None, text[start : start + size], alias).ratio())
    return best


def _semantic_bonus(text: str, alias: str) -> float:
    age_words = {
        "elder": ("老", "老人", "老年", "爷爷", "奶奶"),
        "child": ("小", "孩子", "儿童", "男孩", "女孩", "童"),
    }
    gender_words = {
        "male": ("男", "爷爷", "男孩"),
        "female": ("女", "奶奶", "女孩"),
    }
    score = 0.0
    if any(word in alias for word in age_words["elder"]) and any(word in text for word in age_words["elder"]):
        score += 0.35
    if any(word in alias for word in age_words["child"]) and any(word in text for word in age_words["child"]):
        score += 0.35
    if any(word in alias for word in gender_words["male"]) and any(word in text for word in gender_words["male"]):
        score += 0.35
    if any(word in alias for word in gender_words["female"]) and any(word in text for word in gender_words["female"]):
        score += 0.35
    if "声" in text or "声音" in text:
        score += 0.1
    return min(score, 1.0)
