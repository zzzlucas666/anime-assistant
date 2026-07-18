"""Shared emotion-signal schema and construction helpers."""

MOOD_DURATIONS = {"happy": 5, "shy": 3, "sad": 6}
MODIFIER_DURATIONS = {
    "worried": 3,
    "touched": 2,
    "curious": 1,
    "surprised": 1,
    "annoyed": 2,
}


def base_turn_signal(reason="no_clear_signal"):
    """Return a complete neutral signal for one conversation turn."""
    return {
        "mood": "neutral",
        "intensity": 0.0,
        "duration_turns": 0,
        "modifier": "none",
        "modifier_strength": 0.0,
        "modifier_duration_turns": 0,
        "voice_style": "conversational",
        "voice_style_strength": 0.4,
        "user_mood": "neutral",
        "user_intensity": 0.0,
        "reset_primary": False,
        "reason": reason,
        "source": "user_input",
        "confidence": 0.25,
        "candidates": [],
        "decision_source": "local_rules",
    }


def set_primary(signal, mood, intensity, reason, duration=None):
    signal["reset_primary"] = False
    signal["mood"] = mood
    signal["intensity"] = intensity
    signal["duration_turns"] = (
        duration if duration is not None else MOOD_DURATIONS.get(mood, 0)
    )
    signal["reason"] = reason
    return signal


def set_modifier(signal, modifier, intensity, duration=None):
    signal["modifier"] = modifier
    signal["modifier_strength"] = intensity
    signal["modifier_duration_turns"] = (
        duration if duration is not None else MODIFIER_DURATIONS.get(modifier, 1)
    )
    return signal


def set_voice_style(signal, voice_style, intensity=0.6):
    signal["voice_style"] = voice_style
    signal["voice_style_strength"] = max(0.0, min(1.0, float(intensity)))
    return signal


def has_interaction_signal(signal):
    """Return whether a signal contains any actionable emotional information."""
    if not isinstance(signal, dict):
        return False
    return any((
        signal.get("mood") not in (None, "neutral"),
        signal.get("modifier") not in (None, "none"),
        signal.get("voice_style") not in (None, ""),
        signal.get("user_mood") not in (None, "neutral"),
        bool(signal.get("reset_primary")),
    ))


# Private aliases keep the manager's established internal vocabulary readable.
_base_turn_signal = base_turn_signal
_set_primary = set_primary
_set_modifier = set_modifier
_set_voice_style = set_voice_style
