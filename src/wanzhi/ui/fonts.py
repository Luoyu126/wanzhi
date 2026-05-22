from __future__ import annotations

from pathlib import Path


FONT_NAME = "WanzhiChinese"
EMOJI_FONT_NAME = "WanzhiEmoji"
FONT_CANDIDATES = [
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
]
EMOJI_FONT_CANDIDATES = [
    Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
]


def register_chinese_font() -> str:
    try:
        from kivy.core.text import LabelBase
        from kivy.resources import resource_add_path
    except ImportError:
        return "Roboto"

    for font_path in FONT_CANDIDATES:
        if font_path.exists():
            resource_add_path(str(font_path.parent))
            LabelBase.register(name=FONT_NAME, fn_regular=str(font_path))
            return FONT_NAME
    return "Roboto"


def register_emoji_font() -> str:
    try:
        from kivy.core.text import LabelBase
        from kivy.resources import resource_add_path
    except ImportError:
        return "Roboto"

    for font_path in EMOJI_FONT_CANDIDATES:
        if font_path.exists():
            resource_add_path(str(font_path.parent))
            try:
                LabelBase.register(name=EMOJI_FONT_NAME, fn_regular=str(font_path))
                return EMOJI_FONT_NAME
            except Exception:
                return "Roboto"
    return "Roboto"
