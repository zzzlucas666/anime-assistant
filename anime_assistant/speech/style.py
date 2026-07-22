"""Map emotion signals to backend reference styles and speech speed."""

from anime_assistant.speech.config import DEFAULT_MIO_GPT_SOVITS_REFERENCES


def effective_mood(mood, emotion_strength, modifier, fatigue_strength):
    """把连续情绪强度压到现有五组语音参考，避免轻微情绪直接满强度。"""
    try:
        strength = max(0.0, min(1.0, float(emotion_strength)))
    except (TypeError, ValueError):
        strength = 1.0
    try:
        fatigue = max(0.0, min(1.0, float(fatigue_strength)))
    except (TypeError, ValueError):
        fatigue = 0.0

    if mood == "tired" or fatigue >= 0.65:
        return "tired"
    if mood in {"happy", "shy", "sad"} and strength < 0.38:
        return "neutral"
    if mood == "neutral" and modifier == "touched" and strength >= 0.5:
        return "happy"
    return mood if mood in {"neutral", "happy", "shy", "sad", "tired"} else "neutral"


def effective_voice_style(
    mood,
    emotion_strength,
    modifier,
    fatigue_strength,
    voice_style=None,
):
    """选择本句语气；显式 voice_style 优先，mood 仅用于兼容旧调用方。"""
    try:
        fatigue = max(0.0, min(1.0, float(fatigue_strength)))
    except (TypeError, ValueError):
        fatigue = 0.0
    if mood == "tired" or fatigue >= 0.65:
        return "tired"

    allowed = set(DEFAULT_MIO_GPT_SOVITS_REFERENCES) - {
        "neutral", "happy", "shy", "sad"
    }
    if isinstance(voice_style, str) and voice_style in allowed:
        return voice_style

    modifier_styles = {
        "worried": "concerned",
        "touched": "warm",
        "curious": "curious",
        "surprised": "surprised",
        "annoyed": "mild_annoyed",
    }
    if modifier in modifier_styles:
        return modifier_styles[modifier]
    return {
        "happy": "cheerful",
        "shy": "bashful",
        "sad": "disappointed",
        "tired": "tired",
    }.get(mood, "conversational")


def emotion_speed_multiplier(
    mood,
    emotion_strength,
    modifier,
    fatigue_strength,
    voice_style=None,
    voice_style_strength=0.6,
):
    """按本句语气微调语速；保留旧 mood 路径以兼容其他后端。"""
    try:
        strength = max(0.0, min(1.0, float(emotion_strength)))
    except (TypeError, ValueError):
        strength = 0.0
    try:
        fatigue = max(0.0, min(1.0, float(fatigue_strength)))
    except (TypeError, ValueError):
        fatigue = 0.0
    try:
        style_strength = max(0.0, min(1.0, float(voice_style_strength)))
    except (TypeError, ValueError):
        style_strength = 0.6

    multiplier = 1.0
    style_deltas = {
        "conversational": 0.0,
        "thoughtful": -0.03,
        "warm": -0.01,
        "cheerful": 0.03,
        "excited": 0.07,
        "bashful": -0.04,
        "embarrassed": -0.07,
        "concerned": -0.06,
        "reassuring": -0.04,
        "curious": 0.01,
        "surprised": 0.05,
        "mild_annoyed": -0.02,
        "serious": -0.05,
        "disappointed": -0.07,
        "tired": -0.10,
    }
    if voice_style in style_deltas:
        multiplier += style_deltas[voice_style] * (0.55 + 0.45 * style_strength)
    else:
        if mood == "happy":
            multiplier += 0.05 * strength
        elif mood == "shy":
            multiplier -= 0.035 * strength
        elif mood == "sad":
            multiplier -= 0.06 * strength
        if modifier == "worried":
            multiplier -= 0.035
        elif modifier == "surprised":
            multiplier += 0.035
        elif modifier == "annoyed":
            multiplier -= 0.02
    multiplier -= 0.08 * fatigue
    return max(0.86, min(1.09, multiplier))
