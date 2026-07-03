"""
CharacterController turns conversation state into character presentation state.

It deliberately stays above the Live2D binding layer: the controller decides
that the character is speaking, happy, sad, and so on; the widget decides how
to apply those values to the concrete model API.
"""

import math
import time


class CharacterController:
    """Small presentation-state controller for Live2D / future TTS integration."""

    EMOTION_TO_EXPRESSION = {
        "happy": "happy",
        "sad": "sad",
        "shy": "shy",
        "tired": "tired",
        "neutral": "neutral",
    }

    def __init__(self, live2d_widget=None):
        self.live2d_widget = live2d_widget
        self.is_speaking = False
        self._last_emotion = None
        self._speaking_started_at = 0.0
        self._last_chunk_at = 0.0
        self._mouth_phase = 0.0

    def set_live2d_widget(self, live2d_widget):
        self.live2d_widget = live2d_widget

    def on_emotion_changed(self, emotion):
        mood = (emotion or {}).get("mood", "neutral")
        if mood == self._last_emotion:
            return

        self._last_emotion = mood
        expression = self.EMOTION_TO_EXPRESSION.get(mood, "neutral")
        self._call_widget("set_expression", expression)

    def on_reply_started(self):
        self.is_speaking = True
        now = time.monotonic()
        self._speaking_started_at = now
        self._last_chunk_at = now

    def on_reply_chunk(self, chunk):
        if chunk:
            if not self.is_speaking:
                self.on_reply_started()
            self._last_chunk_at = time.monotonic()

    def on_reply_finished(self):
        self.is_speaking = False
        self._call_widget("set_mouth_open", 0.0)

    def tick(self):
        """Called once per render frame. Drives a simple non-TTS mouth flap."""
        if not self.live2d_widget:
            return

        if not self.is_speaking:
            self._call_widget("set_mouth_open", 0.0)
            return

        now = time.monotonic()
        # If text streaming stalls briefly, taper the mouth instead of snapping.
        silence = max(0.0, now - self._last_chunk_at)
        activity = max(0.0, 1.0 - silence / 0.8)

        elapsed = now - self._speaking_started_at
        open_value = (0.25 + 0.55 * abs(math.sin(elapsed * 18.0))) * activity
        self._call_widget("set_mouth_open", open_value)

    def _call_widget(self, method_name, *args):
        target = self.live2d_widget
        if not target:
            return
        method = getattr(target, method_name, None)
        if callable(method):
            method(*args)
