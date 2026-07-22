"""AI-assisted calibration constrained by the local emotion safety plan."""

from anime_assistant.infrastructure.models import ALLOWED_VOICE_STYLES
from anime_assistant.emotion.rules import DISTRESS_USER_MOODS, SUPPORT_VOICE_STYLES
from anime_assistant.emotion.signals import (
    EMOTION_CONTROL_REACTIONS,
    EMOTION_CONTROL_USER_MOODS,
    _base_turn_signal,
    _set_modifier,
    _set_primary,
    _set_voice_style,
)


def _bounded_probability(value, default=0.0):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def apply_ai_emotion_control(planned, control):
    """用主回复附带的控制信息校准本轮反应；异常时原样回退本地计划。"""
    signal = dict(planned) if isinstance(planned, dict) else _base_turn_signal()
    if not isinstance(control, dict):
        return signal

    user_mood = str(control.get("user_mood", "neutral") or "neutral")
    reaction = str(control.get("reaction", "neutral") or "neutral")
    voice_style = str(control.get("voice_style", "conversational") or "conversational")
    strength = _bounded_probability(control.get("strength"), 0.5)
    ai_confidence = _bounded_probability(control.get("confidence"), 0.0)
    if (
        ai_confidence < 0.55
        or user_mood not in EMOTION_CONTROL_USER_MOODS
        or reaction not in EMOTION_CONTROL_REACTIONS
        or voice_style not in ALLOWED_VOICE_STYLES
    ):
        return signal

    local_confidence = _bounded_probability(signal.get("confidence"), 0.25)
    local_user_mood = str(signal.get("user_mood", "neutral") or "neutral")
    local_reason = str(signal.get("reason", "") or "")
    strong_support = (
        local_user_mood in DISTRESS_USER_MOODS
        and local_confidence >= 0.72
        and local_reason != "negative_words_toward_mio"
    )
    possible_support = (
        local_user_mood in DISTRESS_USER_MOODS
        and local_confidence >= 0.5
        and local_reason != "negative_words_toward_mio"
    )
    conflicts_with_support = (
        user_mood not in DISTRESS_USER_MOODS
        and reaction in {"happy", "shy"}
    )
    strong_directed_negative = (
        local_reason == "negative_words_toward_mio" and local_confidence >= 0.72
    )

    if strong_directed_negative:
        if voice_style in {"disappointed", "serious"}:
            _set_voice_style(signal, voice_style, strength)
    elif strong_support:
        if reaction == "worried":
            _set_modifier(signal, "worried", max(0.5, strength), 3)
        if voice_style in SUPPORT_VOICE_STYLES:
            _set_voice_style(signal, voice_style, strength)
    elif possible_support and conflicts_with_support:
        pass
    else:
        if user_mood != "neutral" and (
            local_user_mood == "neutral" or ai_confidence > local_confidence + 0.08
        ):
            signal["user_mood"] = user_mood
            signal["user_intensity"] = max(0.35, strength)
            if user_mood in DISTRESS_USER_MOODS:
                signal["reset_primary"] = True

        if user_mood in DISTRESS_USER_MOODS:
            if reaction == "worried":
                _set_modifier(signal, "worried", max(0.45, strength), 3)
            if voice_style in SUPPORT_VOICE_STYLES:
                _set_voice_style(signal, voice_style, strength)
        elif reaction in {"happy", "shy", "sad"}:
            _set_primary(
                signal,
                reaction,
                max(0.35, strength),
                f"ai_calibrated_{reaction}",
            )
        elif reaction in {"worried", "touched", "curious", "surprised", "annoyed"}:
            _set_modifier(signal, reaction, max(0.3, strength))
            signal["reason"] = f"ai_calibrated_{reaction}"

        if user_mood not in DISTRESS_USER_MOODS:
            _set_voice_style(signal, voice_style, strength)

    signal["decision_source"] = "hybrid_ai"
    signal["ai_confidence"] = ai_confidence
    signal["ai_control"] = {
        "user_mood": user_mood,
        "reaction": reaction,
        "voice_style": voice_style,
        "strength": strength,
    }
    return signal
