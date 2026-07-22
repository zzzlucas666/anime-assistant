"""Persistence and deterministic state transitions for long-lived emotion state."""

import datetime

from anime_assistant.infrastructure.storage import safe_load_json, safe_save_json
from anime_assistant.infrastructure.paths import DATA_DIR
from anime_assistant.infrastructure.models import ALLOWED_VOICE_STYLES, normalize_emotion
from anime_assistant.emotion.rules import POSITIVE_MOODS
from anime_assistant.emotion.signals import (
    MODIFIER_DURATIONS,
    MOOD_DURATIONS,
    _base_turn_signal,
    _set_modifier,
    _set_primary,
    _set_voice_style,
    has_interaction_signal,
)


DEFAULT_EMOTION_PATH = str(DATA_DIR / "emotion_state.json")

MOOD_DECAY_MINUTES = 20
ENERGY_RECOVERY_PER_MINUTE = 1 / 10
ENERGY_RECOVERY_CAP = 30
MIN_SIGNAL_INTENSITY = 0.28
STRONG_SWITCH_INTENSITY = 0.72
PENDING_MOOD_MINUTES = 5
FATIGUE_ENTER_ENERGY = 25
FATIGUE_EXIT_ENERGY = 35


def default_emotion():
    return {
        "mood": "neutral",
        "energy": 80,
        "last_updated": None,
        "mood_set_at": None,
        "mood_strength": 0.0,
        "mood_turns_remaining": 0,
        "mood_source": "default",
        "modifier": "none",
        "modifier_strength": 0.0,
        "modifier_turns_remaining": 0,
        "voice_style": "conversational",
        "voice_style_strength": 0.4,
        "user_mood": "neutral",
        "user_mood_strength": 0.0,
        "user_mood_set_at": None,
        "fatigue_strength": 0.0,
        "pending_mood": None,
        "pending_mood_count": 0,
        "pending_mood_expires_at": None,
    }


def load_emotion(path=DEFAULT_EMOTION_PATH):
    raw_emotion = safe_load_json(path, default_emotion)
    emotion = normalize_emotion(raw_emotion)
    if emotion != raw_emotion:
        safe_save_json(path, emotion)
    return emotion


def save_emotion(emotion, path=DEFAULT_EMOTION_PATH):
    normalized = normalize_emotion(emotion)
    emotion.clear()
    emotion.update(normalized)
    return safe_save_json(path, emotion)


def _elapsed_minutes(timestamp_str, now):
    if not timestamp_str:
        return None
    try:
        last_time = datetime.datetime.fromisoformat(timestamp_str)
        return (now - last_time).total_seconds() / 60
    except Exception:
        return None


def _event_signal(event):
    if not isinstance(event, dict):
        return None
    emotion = event.get("emotion", "neutral")
    try:
        importance = float(event.get("importance", 0.3))
    except (TypeError, ValueError):
        importance = 0.3
    importance = max(0.0, min(1.0, importance))
    intensity = max(0.35, min(0.9, 0.35 + importance * 0.55))
    signal = _base_turn_signal("long_term_event")
    signal["source"] = "long_term_event"
    signal["user_mood"] = event.get("user_emotion", "neutral")
    signal["user_intensity"] = intensity if signal["user_mood"] != "neutral" else 0.0
    if emotion in {"happy", "shy", "sad"}:
        _set_primary(signal, emotion, intensity, "long_term_event")
        _set_voice_style(
            signal,
            {"happy": "cheerful", "shy": "bashful", "sad": "disappointed"}[emotion],
            intensity,
        )
    elif emotion == "touched":
        _set_primary(signal, "happy", intensity * 0.8, "touching_event", 4)
        _set_modifier(signal, "touched", intensity, 3)
        _set_voice_style(signal, "warm", intensity)
    elif emotion == "worried":
        _set_modifier(signal, "worried", intensity, 3)
        _set_voice_style(signal, "concerned", intensity)
    elif emotion == "curious":
        _set_modifier(signal, "curious", intensity, 1)
        _set_voice_style(signal, "curious", intensity)
    return signal


def _is_cross_valence(current_mood, new_mood):
    if current_mood in ("neutral", "tired") or new_mood in ("neutral", "tired"):
        return False
    return (current_mood in POSITIVE_MOODS) != (new_mood in POSITIVE_MOODS)


def _clear_pending(emotion):
    emotion["pending_mood"] = None
    emotion["pending_mood_count"] = 0
    emotion["pending_mood_expires_at"] = None


def _pending_valid(emotion, now, mood):
    if emotion.get("pending_mood") != mood:
        return False
    expires_at = emotion.get("pending_mood_expires_at")
    if not expires_at:
        return False
    try:
        return datetime.datetime.fromisoformat(expires_at) >= now
    except Exception:
        return False


def _apply_mood_signal(emotion, signal, now):
    new_mood = signal.get("mood") if isinstance(signal, dict) else None
    try:
        intensity = float(signal.get("intensity", 0.0))
    except (AttributeError, TypeError, ValueError):
        return False
    intensity = max(0.0, min(1.0, intensity))
    if new_mood not in {"happy", "shy", "sad"} or intensity < MIN_SIGNAL_INTENSITY:
        return False

    current_mood = emotion.get("mood", "neutral")
    current_strength = float(emotion.get("mood_strength", 0.0) or 0.0)
    duration = int(signal.get("duration_turns") or MOOD_DURATIONS.get(new_mood, 3))
    remaining_after_trigger = max(0, duration - 1)

    if new_mood == current_mood:
        emotion["mood_strength"] = min(1.0, current_strength * 0.55 + intensity * 0.55)
        emotion["mood_turns_remaining"] = max(
            emotion.get("mood_turns_remaining", 0),
            remaining_after_trigger,
        )
        emotion["mood_set_at"] = now.isoformat()
        emotion["mood_source"] = str(signal.get("source") or signal.get("reason") or "interaction")
        _clear_pending(emotion)
        return True

    if _is_cross_valence(current_mood, new_mood) and intensity < STRONG_SWITCH_INTENSITY:
        if _pending_valid(emotion, now, new_mood):
            emotion["pending_mood_count"] = int(emotion.get("pending_mood_count", 0)) + 1
        else:
            emotion["pending_mood"] = new_mood
            emotion["pending_mood_count"] = 1
        emotion["pending_mood_expires_at"] = (
            now + datetime.timedelta(minutes=PENDING_MOOD_MINUTES)
        ).isoformat()
        if emotion["pending_mood_count"] < 2:
            return False

    emotion["mood"] = new_mood
    emotion["mood_strength"] = intensity
    emotion["mood_turns_remaining"] = remaining_after_trigger
    emotion["mood_set_at"] = now.isoformat()
    emotion["mood_source"] = str(signal.get("source") or signal.get("reason") or "interaction")
    _clear_pending(emotion)
    return True


def _advance_mood_lifetime(emotion):
    if emotion.get("mood") in (None, "neutral", "tired"):
        return
    remaining = max(0, int(emotion.get("mood_turns_remaining", 0)))
    if remaining > 1:
        emotion["mood_turns_remaining"] = remaining - 1
        return
    emotion["mood"] = "neutral"
    emotion["mood_strength"] = 0.0
    emotion["mood_turns_remaining"] = 0
    emotion["mood_source"] = "natural_decay"


def _advance_modifier(emotion, signal):
    modifier = signal.get("modifier") if isinstance(signal, dict) else "none"
    if modifier not in (None, "none"):
        emotion["modifier"] = modifier
        emotion["modifier_strength"] = max(0.0, min(1.0, float(signal.get("modifier_strength", 0.5))))
        emotion["modifier_turns_remaining"] = int(
            signal.get("modifier_duration_turns") or MODIFIER_DURATIONS.get(modifier, 1)
        )
        return

    remaining = max(0, int(emotion.get("modifier_turns_remaining", 0)))
    if remaining > 1:
        emotion["modifier_turns_remaining"] = remaining - 1
        emotion["modifier_strength"] *= 0.82
    else:
        emotion["modifier"] = "none"
        emotion["modifier_strength"] = 0.0
        emotion["modifier_turns_remaining"] = 0


def _apply_user_emotion(emotion, signal, now):
    user_mood = signal.get("user_mood") if isinstance(signal, dict) else "neutral"
    if user_mood in (None, "neutral"):
        emotion["user_mood_strength"] *= 0.7
        if emotion["user_mood_strength"] < 0.2:
            emotion["user_mood"] = "neutral"
            emotion["user_mood_strength"] = 0.0
        return
    emotion["user_mood"] = user_mood
    emotion["user_mood_strength"] = max(0.0, min(1.0, float(signal.get("user_intensity", 0.6))))
    emotion["user_mood_set_at"] = now.isoformat()


def _apply_voice_style(emotion, signal):
    voice_style = signal.get("voice_style") if isinstance(signal, dict) else None
    if voice_style not in ALLOWED_VOICE_STYLES:
        voice_style = "conversational"
    emotion["voice_style"] = voice_style
    emotion["voice_style_strength"] = max(
        0.0,
        min(1.0, float(signal.get("voice_style_strength", 0.4) or 0.4)),
    )


def _fatigue_strength(energy):
    return max(0.0, min(1.0, (45.0 - float(energy)) / 25.0))


def update_emotion(emotion, event=None, interaction=None, consume_energy=True):
    """推进一轮情绪状态；即时反应优先，事件分析只作为兜底。"""
    normalized = normalize_emotion(emotion)
    emotion.clear()
    emotion.update(normalized)
    now = datetime.datetime.now()
    was_tired = emotion.get("mood") == "tired"

    elapsed = _elapsed_minutes(emotion.get("last_updated"), now)
    mood_elapsed = _elapsed_minutes(emotion.get("mood_set_at"), now)
    if consume_energy:
        emotion["energy"] -= 1
    if elapsed is not None:
        emotion["energy"] += min(
            elapsed * ENERGY_RECOVERY_PER_MINUTE,
            ENERGY_RECOVERY_CAP,
        )
    emotion["energy"] = max(0, min(100, emotion["energy"]))
    emotion["fatigue_strength"] = _fatigue_strength(emotion["energy"])

    signal = interaction if has_interaction_signal(interaction) else _event_signal(event)
    if signal is None:
        signal = _base_turn_signal()

    _apply_user_emotion(emotion, signal, now)
    _apply_voice_style(emotion, signal)
    _advance_modifier(emotion, signal)

    has_primary = signal.get("mood") not in (None, "neutral")
    reset_primary = bool(signal.get("reset_primary"))
    if reset_primary:
        emotion["mood"] = "neutral"
        emotion["mood_strength"] = 0.0
        emotion["mood_turns_remaining"] = 0
        emotion["mood_source"] = str(signal.get("reason") or "empathetic_reset")
        _clear_pending(emotion)
    elif (
        not has_primary
        and emotion.get("mood_source") == "proactive"
        and emotion.get("mood") not in (None, "neutral", "tired")
    ):
        emotion["mood"] = "neutral"
        emotion["mood_strength"] = 0.0
        emotion["mood_turns_remaining"] = 0
        emotion["mood_source"] = "proactive_transient_recovery"
        _clear_pending(emotion)
    elif has_primary:
        mood_changed = _apply_mood_signal(emotion, signal, now)
        if not mood_changed and not emotion.get("pending_mood"):
            _advance_mood_lifetime(emotion)
    else:
        _clear_pending(emotion)
        _advance_mood_lifetime(emotion)

    if (
        emotion.get("mood") not in (None, "neutral", "tired")
        and mood_elapsed is not None
        and mood_elapsed >= MOOD_DECAY_MINUTES
        and not has_primary
        and not reset_primary
    ):
        emotion["mood"] = "neutral"
        emotion["mood_strength"] = 0.0
        emotion["mood_turns_remaining"] = 0
        emotion["mood_source"] = "time_decay"

    if emotion["energy"] <= FATIGUE_ENTER_ENERGY or (
        was_tired and emotion["energy"] < FATIGUE_EXIT_ENERGY
    ):
        emotion["mood"] = "tired"
        emotion["mood_strength"] = max(0.65, emotion["fatigue_strength"])
        emotion["mood_turns_remaining"] = 0
        emotion["mood_source"] = "fatigue"
        _clear_pending(emotion)
    elif was_tired and emotion["energy"] >= FATIGUE_EXIT_ENERGY and not has_primary:
        emotion["mood"] = "neutral"
        emotion["mood_strength"] = 0.0
        emotion["mood_source"] = "recovered"

    emotion["last_updated"] = now.isoformat()
    return emotion
