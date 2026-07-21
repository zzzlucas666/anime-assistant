"""Conservative local parsing for explicit, user-evidenced profile updates."""

from __future__ import annotations

import re

from anime_assistant.conversation.types import ProfileUpdate


_QUESTION_MARKERS = ("什么", "多少", "怎么", "哪", "为何", "为什么", "是否")
_RELATIONSHIP_VALUES = {
    "你",
    "mio",
    "澪",
    "秋山澪",
    "你呀",
    "你啊",
}
_DIRECT_RELATIONSHIP_PHRASES = (
    "我喜欢你",
    "我爱你",
    "我好喜欢你",
    "我很喜欢你",
    "感觉你好可爱",
    "觉得你好可爱",
)
_AMBIGUOUS_VALUE_MARKERS = (
    "，",
    ",",
    "；",
    ";",
    "但是",
    "不过",
    "而且",
    "因为",
    "所以",
    "或者",
)
_EXPLICIT_PATTERNS = (
    (r"^我不再喜欢(?P<value>.+)$", "remove_like"),
    (r"^我不再讨厌(?P<value>.+)$", "remove_dislike"),
    (r"^我现在不喜欢(?P<value>.+)$", "add_dislike"),
    (r"^我现在不讨厌(?P<value>.+)$", "remove_dislike"),
    (r"^我不喜欢(?P<value>.+)$", "add_dislike"),
    (r"^我讨厌(?P<value>.+)$", "add_dislike"),
    (r"^我反感(?P<value>.+)$", "add_dislike"),
    (r"^我喜欢(?P<value>.+)$", "add_like"),
    (r"^我爱(?P<value>.+)$", "add_like"),
    (r"^我的名字(?:是|叫)(?P<value>.+)$", "set_name"),
    (r"^我名字(?:是|叫)(?P<value>.+)$", "set_name"),
    (r"^我叫(?P<value>.+)$", "set_name"),
    (r"^我的昵称(?:是|叫)(?P<value>.+)$", "set_nickname"),
    (r"^你可以叫我(?P<value>.+)$", "set_nickname"),
    (r"^以后叫我(?P<value>.+)$", "set_nickname"),
)
_DEFERRED_PATTERNS = (
    r"(?:我|本人).{0,8}(?:喜欢|爱上|迷上|讨厌|不喜欢|反感)",
    r"(?:最近|突然|这阵子).{0,6}(?:喜欢上|爱上|迷上|讨厌)",
    r"(?:大家|朋友|同学|别人).{0,8}(?:叫我|称呼我)",
    r"(?:我的|我).{0,6}(?:名字|昵称).{0,4}(?:改成|是|叫)",
    r"(?:更正一下|记错了).{0,12}(?:名字|昵称|喜欢|讨厌|叫我)",
)


def _clean_value(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"[，。！？!?；;]+$", "", value).strip()
    if len(value) > 1:
        value = re.sub(r"(?:了|啦|呀|啊|呢)$", "", value).strip()
    return value


def parse_explicit_profile_update(user_message: str) -> ProfileUpdate | None:
    """Parse only short, anchored statements that are safe without an AI call."""
    text = str(user_message or "").strip()
    if not text or "?" in text or "？" in text:
        return None
    if any(marker in text for marker in _QUESTION_MARKERS):
        return None

    for pattern, action in _EXPLICIT_PATTERNS:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match is None:
            continue
        value = _clean_value(match.group("value"))
        if (
            not value
            or len(value) > 64
            or value.casefold() in _RELATIONSHIP_VALUES
            or any(marker in value for marker in _AMBIGUOUS_VALUE_MARKERS)
        ):
            return None
        return ProfileUpdate(action=action, value=value, confidence=1.0)
    return None


def looks_like_deferred_profile_update(user_message: str) -> bool:
    """Flag ambiguous profile language for post-reply AI extraction."""
    text = str(user_message or "").strip()
    if not text or "?" in text or "？" in text:
        return False
    # 这是对 Mio 的关系表达，不是用户稳定档案中的兴趣偏好。
    if any(phrase in text.casefold() for phrase in _DIRECT_RELATIONSHIP_PHRASES):
        return False
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _DEFERRED_PATTERNS)
