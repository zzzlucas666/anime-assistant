"""Typed queue messages used by the speech synthesis worker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Union


@dataclass(frozen=True)
class SpeechJob:
    """One immutable speech request passed to the background TTS worker."""

    text: str
    mood: str = "neutral"
    emotion_strength: float = 1.0
    modifier: str = "none"
    fatigue_strength: float = 0.0
    voice_style: Optional[str] = None
    voice_style_strength: float = 0.6
    turn_id: Optional[str] = None

    @classmethod
    def from_legacy(cls, job: Union["SpeechJob", Sequence[object]]) -> "SpeechJob":
        """Normalize tuple jobs kept for compatibility with older callers/tests."""
        if isinstance(job, cls):
            return job
        if not isinstance(job, (tuple, list)) or len(job) < 2:
            raise TypeError("Speech queue item must be SpeechJob or a legacy tuple")
        values = list(job[:8])
        defaults = ["neutral", 1.0, "none", 0.0, None, 0.6, None]
        values.extend(defaults[len(values) - 1 :])
        return cls(
            text=str(values[0]),
            mood=str(values[1]),
            emotion_strength=float(values[2]),
            modifier=str(values[3]),
            fatigue_strength=float(values[4]),
            voice_style=None if values[5] is None else str(values[5]),
            voice_style_strength=float(values[6]),
            turn_id=None if values[7] is None else str(values[7]),
        )


@dataclass(frozen=True)
class WarmupJob:
    """Load a local model before the first speech request."""

    on_complete: Optional[Callable[[], None]] = None
