"""Compatibility facade for the vertically split emotion subsystem.

Existing callers keep importing from ``emotion.manager`` while the actual
responsibilities live in rules, planning, calibration, and state modules.
"""

from anime_assistant.emotion.calibration import apply_ai_emotion_control
from anime_assistant.emotion.planning import (
    infer_interaction_emotion,
    plan_greeting_emotion,
    plan_proactive_emotion,
    plan_turn_emotion,
    score_turn_emotion_candidates,
)
from anime_assistant.emotion.signals import has_interaction_signal
from anime_assistant.emotion.state import (
    DEFAULT_EMOTION_PATH,
    default_emotion,
    load_emotion as _load_emotion,
    save_emotion as _save_emotion,
    update_emotion,
)


EMOTION_PATH = DEFAULT_EMOTION_PATH


def load_emotion():
    return _load_emotion(EMOTION_PATH)


def save_emotion(emotion):
    return _save_emotion(emotion, EMOTION_PATH)


__all__ = [
    "EMOTION_PATH",
    "apply_ai_emotion_control",
    "default_emotion",
    "has_interaction_signal",
    "infer_interaction_emotion",
    "load_emotion",
    "plan_greeting_emotion",
    "plan_proactive_emotion",
    "plan_turn_emotion",
    "save_emotion",
    "score_turn_emotion_candidates",
    "update_emotion",
]
