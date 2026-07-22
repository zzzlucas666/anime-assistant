"""Monotonic process-local identities for user, greeting, and proactive turns."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable, Optional


@dataclass(frozen=True)
class TurnContext:
    """Immutable identity and creation metadata for one conversational turn."""

    turn_id: str
    sequence: int
    source: str
    created_at: float


class TurnCoordinator:
    """Issue ordered turn IDs and expose the only current conversational turn."""

    def __init__(self):
        self._lock = threading.RLock()
        self._sequence = 0
        self._current: Optional[TurnContext] = None
        self._closed = False
        self._listeners: list[Callable[[Optional[TurnContext], TurnContext], None]] = []

    def add_listener(self, listener):
        if not callable(listener):
            return
        with self._lock:
            self._listeners.append(listener)

    def begin(self, source="user"):
        normalized_source = str(source or "unknown").strip().lower() or "unknown"
        with self._lock:
            if self._closed:
                raise RuntimeError("turn coordinator is closed")
            previous = self._current
            self._sequence += 1
            current = TurnContext(
                turn_id=f"turn-{self._sequence:08d}-{normalized_source}",
                sequence=self._sequence,
                source=normalized_source,
                created_at=time.monotonic(),
            )
            self._current = current
            listeners = tuple(self._listeners)

        for listener in listeners:
            listener(previous, current)
        return current

    @property
    def current(self):
        with self._lock:
            return self._current

    @property
    def current_id(self):
        current = self.current
        return current.turn_id if current is not None else None

    def is_current(self, turn_id):
        if turn_id is None:
            return True
        with self._lock:
            return (
                not self._closed
                and self._current is not None
                and self._current.turn_id == str(turn_id)
            )

    def close(self):
        with self._lock:
            self._closed = True
            self._current = None
