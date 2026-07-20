"""Translate deterministic runtime state into semantic behavior tendencies."""

from anime_assistant.character.relationship_behavior import build_relationship_policy


NEGATIVE_USER_MOODS = {
    "sad", "anxious", "angry", "lonely", "stressed", "tired", "disappointed",
}


def _ratio(value, maximum=1.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if maximum > 1.0:
        number /= maximum
    return max(0.0, min(1.0, number))


def _level(value, low=0.34, high=0.7):
    if value >= high:
        return "高"
    if value >= low:
        return "中"
    return "低"


def _expression_level(turn_emotion, emotion, canonical_policy):
    strengths = []
    for key in (
        "intensity", "modifier_strength", "voice_style_strength", "user_intensity",
    ):
        strengths.append(_ratio(turn_emotion.get(key)))
    strength = max(strengths or [0.0])
    if not any(strengths):
        strength = _ratio(canonical_policy.get("emotion_expression"))
    fatigue = _ratio(emotion.get("fatigue_strength"))
    if fatigue >= 0.65:
        strength = min(strength, 0.58)
    return _level(strength, low=0.3, high=0.7)


def derive_behavior_state(context, mode="chat"):
    """Return prompt-friendly labels without exposing raw relationship scores."""
    context = context if isinstance(context, dict) else {}
    relationship = context.get("relationship")
    relationship = relationship if isinstance(relationship, dict) else {}
    emotion = context.get("emotion")
    emotion = emotion if isinstance(emotion, dict) else {}
    turn_emotion = context.get("turn_emotion")
    turn_emotion = turn_emotion if isinstance(turn_emotion, dict) else {}
    canonical = build_relationship_policy(relationship, emotion)

    energy = _ratio(emotion.get("energy", 50), maximum=100.0)
    user_mood = str(turn_emotion.get("user_mood") or "neutral")
    reaction = str(turn_emotion.get("modifier") or "none")
    voice_style = str(turn_emotion.get("voice_style") or emotion.get("voice_style") or "conversational")
    current_mood = str(turn_emotion.get("mood") or emotion.get("mood") or "neutral")
    needs_support = user_mood in NEGATIVE_USER_MOODS or reaction == "worried"

    initiative = 0.22 + _ratio(canonical.get("initiative")) * 0.3 + energy * 0.15
    if mode == "proactive":
        initiative += 0.22
    elif mode == "greeting":
        initiative += 0.08
    if needs_support:
        initiative = min(initiative, 0.62)

    playfulness = _ratio(canonical.get("warmth")) * 0.28
    if current_mood == "happy":
        playfulness += 0.28
    if reaction in {"annoyed", "worried"} or voice_style in {"serious", "concerned", "reassuring"}:
        playfulness *= 0.35

    seriousness = 0.3
    if needs_support:
        seriousness += 0.48
    if voice_style in {"serious", "concerned", "reassuring", "disappointed"}:
        seriousness += 0.25
    if current_mood == "happy" and not needs_support:
        seriousness -= 0.12

    if needs_support:
        response_depth = "中；先陪伴，再按需要给建议"
    elif mode in {"greeting", "proactive"}:
        response_depth = "低；只自然开启话题"
    else:
        response_depth = "低；直接回应，确有必要时再补充"

    relationship_stage = {
        "close": "亲近朋友",
        "friendly": "熟悉朋友",
        "reserved": "关系尚浅",
    }[canonical["closeness"]]
    openness = {
        "open": "高；可以分享真实想法",
        "careful": "中；真诚但有所保留",
        "guarded": "低；保持友好边界",
    }[canonical["openness"]]
    familiarity = {
        "familiar": "高；可以自然使用昵称和有来源的共同记忆",
        "acquainted": "中；偶尔使用昵称，不假装熟知细节",
        "new": "低；像认识不久一样交流",
    }[canonical["familiarity_level"]]

    return {
        "relationship_stage": relationship_stage,
        "warmth": _level(_ratio(canonical.get("warmth"))),
        "openness": openness,
        "familiarity": familiarity,
        "initiative": _level(max(0.0, min(1.0, initiative))),
        "playfulness": _level(max(0.0, min(1.0, playfulness))),
        "seriousness": _level(max(0.0, min(1.0, seriousness))),
        "emotion_expression": _expression_level(turn_emotion, emotion, canonical),
        "response_depth": response_depth,
    }


def build_behavior_layer(context, mode="chat"):
    state = derive_behavior_state(context, mode=mode)
    return f"""# 【Behavior｜当前行为倾向】
这些是本轮的表达方向，不要逐字复述给用户：

- 温暖程度：{state['warmth']}
- 表达开放度：{state['openness']}
- 主动延展程度：{state['initiative']}
- 玩笑倾向：{state['playfulness']}
- 认真程度：{state['seriousness']}
- 情绪外显程度：{state['emotion_expression']}
- 回复深度：{state['response_depth']}"""
