"""Small thread supervisor with cancellation, scopes, and turn attribution."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import threading
import time
from typing import Callable, Optional

from anime_assistant.infrastructure.logging import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class TaskSnapshot:
    task_id: str
    name: str
    state: str
    turn_id: Optional[str]
    scope: Optional[str]
    started_at: float
    finished_at: Optional[float]


class TaskToken:
    """Cooperative cancellation token visible to supervised work."""

    def __init__(self, supervisor, task_id, name, turn_id, cancel_event):
        self._supervisor = supervisor
        self.task_id = task_id
        self.name = name
        self.turn_id = turn_id
        self._cancel_event = cancel_event

    @property
    def cancelled(self):
        return self._cancel_event.is_set()

    def is_current(self):
        return not self.cancelled and self._supervisor.is_turn_current(self.turn_id)


class TaskHandle:
    """Stable handle returned for a supervised background thread."""

    def __init__(self, supervisor, task_id, thread):
        self._supervisor = supervisor
        self.task_id = task_id
        self.thread = thread

    def cancel(self):
        return self._supervisor.cancel(self.task_id)

    def join(self, timeout=None):
        self.thread.join(timeout=timeout)

    def is_alive(self):
        return self.thread.is_alive()


@dataclass
class _TaskRecord:
    task_id: str
    name: str
    turn_id: Optional[str]
    scope: Optional[str]
    started_at: float
    cancel_event: threading.Event
    cancel_callback: Optional[Callable[[], None]] = None
    thread: Optional[threading.Thread] = None
    state: str = "running"
    finished_at: Optional[float] = None


class TaskSupervisor:
    """Own background task metadata and coordinate cooperative cancellation."""

    def __init__(self, is_turn_current=None):
        self._turn_checker = is_turn_current or (lambda _turn_id: True)
        self._lock = threading.RLock()
        self._sequence = 0
        self._accepting = True
        self._records: dict[str, _TaskRecord] = {}

    def is_turn_current(self, turn_id):
        return turn_id is None or bool(self._turn_checker(turn_id))

    def _new_record(self, name, turn_id=None, scope=None, cancel=None):
        with self._lock:
            if not self._accepting:
                raise RuntimeError("task supervisor is shutting down")
            self._sequence += 1
            task_id = f"task-{self._sequence:08d}"
            record = _TaskRecord(
                task_id=task_id,
                name=str(name or "background-task"),
                turn_id=None if turn_id is None else str(turn_id),
                scope=None if scope is None else str(scope),
                started_at=time.monotonic(),
                cancel_event=threading.Event(),
                cancel_callback=cancel,
            )
            self._records[task_id] = record
            return record

    def start(
        self,
        name,
        target,
        *,
        turn_id=None,
        scope=None,
        cancel=None,
        daemon=True,
    ):
        record = self._new_record(name, turn_id=turn_id, scope=scope, cancel=cancel)
        token = TaskToken(
            self,
            record.task_id,
            record.name,
            record.turn_id,
            record.cancel_event,
        )

        def runner():
            try:
                target(token)
            except Exception:
                logger.exception(
                    "受监督后台任务失败 name=%s task_id=%s turn_id=%s",
                    record.name,
                    record.task_id,
                    record.turn_id,
                )
            finally:
                self._finish(record.task_id)

        thread = threading.Thread(target=runner, name=record.name, daemon=daemon)
        record.thread = thread
        thread.start()
        return TaskHandle(self, record.task_id, thread)

    @contextmanager
    def track(self, name, *, turn_id=None, scope=None):
        """Attribute work already running on another managed worker thread."""
        record = self._new_record(name, turn_id=turn_id, scope=scope)
        token = TaskToken(
            self,
            record.task_id,
            record.name,
            record.turn_id,
            record.cancel_event,
        )
        try:
            yield token
        finally:
            self._finish(record.task_id)

    def _finish(self, task_id):
        with self._lock:
            record = self._records.get(task_id)
            if record is None or record.finished_at is not None:
                return
            record.state = "cancelled" if record.cancel_event.is_set() else "finished"
            record.finished_at = time.monotonic()

    def cancel(self, task_id):
        callback = None
        with self._lock:
            record = self._records.get(task_id)
            if record is None or record.finished_at is not None:
                return False
            if not record.cancel_event.is_set():
                record.cancel_event.set()
                record.state = "cancelling"
                callback = record.cancel_callback
        if callable(callback):
            try:
                callback()
            except Exception as exc:
                logger.warning("取消后台任务失败 task_id=%s: %s", task_id, exc)
        return True

    def cancel_scope(self, scope):
        with self._lock:
            task_ids = [
                record.task_id
                for record in self._records.values()
                if record.scope == scope and record.finished_at is None
            ]
        return sum(1 for task_id in task_ids if self.cancel(task_id))

    def cancel_stale_turns(self, current_turn_id, scopes=None):
        allowed_scopes = None if scopes is None else set(scopes)
        with self._lock:
            task_ids = [
                record.task_id
                for record in self._records.values()
                if record.finished_at is None
                and record.turn_id is not None
                and record.turn_id != current_turn_id
                and (allowed_scopes is None or record.scope in allowed_scopes)
            ]
        return sum(1 for task_id in task_ids if self.cancel(task_id))

    def snapshots(self, active_only=False):
        with self._lock:
            records = tuple(self._records.values())
        return tuple(
            TaskSnapshot(
                task_id=record.task_id,
                name=record.name,
                state=record.state,
                turn_id=record.turn_id,
                scope=record.scope,
                started_at=record.started_at,
                finished_at=record.finished_at,
            )
            for record in records
            if not active_only or record.finished_at is None
        )

    def shutdown(self, timeout=2.0):
        with self._lock:
            self._accepting = False
            active_ids = [
                record.task_id
                for record in self._records.values()
                if record.finished_at is None
            ]
        for task_id in active_ids:
            self.cancel(task_id)

        deadline = time.monotonic() + max(0.0, float(timeout))
        with self._lock:
            threads = [
                record.thread
                for record in self._records.values()
                if record.thread is not None
            ]
        current = threading.current_thread()
        for thread in threads:
            if thread is current or not thread.is_alive():
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(timeout=remaining)
