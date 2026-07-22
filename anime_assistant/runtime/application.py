"""Process-level ownership for conversation, proactive, memory, and speech work."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import threading
from typing import Callable, Optional

from anime_assistant.ai.chat import generate_greeting
from anime_assistant.character.profile_manager import load_profile
from anime_assistant.character.relationship_manager import load_relationship
from anime_assistant.conversation.context_manager import ContextManager
from anime_assistant.conversation.orchestrator import ConversationOrchestrator
from anime_assistant.emotion.manager import (
    load_emotion,
    plan_greeting_emotion,
    save_emotion,
    update_emotion,
)
from anime_assistant.infrastructure.logging import get_logger
from anime_assistant.memory.event_manager import schedule_embedding_backfill
from anime_assistant.memory.memory_manager import load_memory
from anime_assistant.memory.semantic_memory import warmup_model_async
from anime_assistant.proactive.initiative_engine import InitiativeEngine
from anime_assistant.runtime.supervisor import TaskSupervisor
from anime_assistant.runtime.turns import TurnCoordinator
from anime_assistant.speech.service import SpeechSynthesisService


logger = get_logger(__name__)


@dataclass(frozen=True)
class RuntimeMessage:
    """A generated message tied to the turn that is allowed to present it."""

    turn_id: str
    text: str
    source: str


class ApplicationRuntime:
    """Own application services and coordinate their lifecycle in one place."""

    def __init__(
        self,
        config,
        *,
        enable_speech=True,
        on_proactive_message: Optional[Callable[[str, Optional[str]], None]] = None,
        on_state_updated: Optional[Callable[[], None]] = None,
        on_audio_ready: Optional[Callable[[object], None]] = None,
        on_speech_error: Optional[Callable[[str], None]] = None,
        on_speech_status: Optional[Callable[[str], None]] = None,
        on_turn_started: Optional[Callable[[object], None]] = None,
    ):
        self.config = config
        self.conversation_history = load_memory()
        self.emotion = load_emotion()
        self.profile = load_profile()
        self.relationship = load_relationship()
        self.context = ContextManager(
            config,
            self.emotion,
            self.profile,
            self.relationship,
        )
        self.state_lock = threading.Lock()

        self.turns = TurnCoordinator()
        self.tasks = TaskSupervisor(self.turns.is_current)
        self.turns.add_listener(self._on_turn_started)

        self._on_proactive_message = on_proactive_message
        self._on_turn_started_callback = on_turn_started
        self._started = False
        self._closed = False
        self._lifecycle_lock = threading.RLock()
        self._initiative_task = None
        self._memory_start_lock = threading.Lock()
        self._memory_tasks_started = False

        self.orchestrator = ConversationOrchestrator(
            config,
            self.context,
            self.conversation_history,
            self.emotion,
            self.profile,
            self.relationship,
            lock=self.state_lock,
            on_state_updated=on_state_updated,
            turn_coordinator=self.turns,
            task_supervisor=self.tasks,
        )
        self.initiative_engine = InitiativeEngine(
            config,
            self.context,
            self.conversation_history,
            self.emotion,
            self.profile,
            self.relationship,
            lock=self.state_lock,
            check_interval_minutes=config["proactive_check_interval_minutes"],
            idle_threshold_minutes=config["proactive_idle_threshold_minutes"],
            proactive_min_interval_minutes=config["proactive_min_interval_minutes"],
            proactive_max_per_day=config["proactive_max_per_day"],
            on_message=self._deliver_proactive_message,
            turn_coordinator=self.turns,
            task_supervisor=self.tasks,
        )

        self.speech_service = None
        if enable_speech and bool(config.get("tts_enabled", False)):
            self.speech_service = SpeechSynthesisService(
                config,
                on_audio_ready=on_audio_ready or (lambda _audio: None),
                on_error=on_speech_error,
                on_status=on_speech_status,
                task_supervisor=self.tasks,
                is_turn_current=self.turns.is_current,
            )

    def _on_turn_started(self, _previous, current):
        if not self.turns.is_current(current.turn_id):
            return
        cancelled = self.tasks.cancel_stale_turns(
            current.turn_id,
            scopes={"conversation", "postprocess", "proactive", "speech"},
        )
        if cancelled:
            logger.info(
                "新轮次已取消 %d 个过时任务 turn_id=%s source=%s",
                cancelled,
                current.turn_id,
                current.source,
            )
        callback = self._on_turn_started_callback
        if callable(callback):
            try:
                callback(current)
            except Exception as exc:
                logger.warning("通知新轮次失败 turn_id=%s: %s", current.turn_id, exc)

    @property
    def current_turn_id(self):
        return self.turns.current_id

    def is_turn_current(self, turn_id):
        return self.turns.is_current(turn_id)

    def begin_turn(self, source="user"):
        return self.turns.begin(source).turn_id

    def _start_memory_tasks(self):
        with self._memory_start_lock:
            if self._memory_tasks_started or self._closed:
                return
            self._memory_tasks_started = True
        warmup_model_async(task_supervisor=self.tasks)
        schedule_embedding_backfill(task_supervisor=self.tasks)

    def start(self):
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("application runtime is closed")
            if self._started:
                return False
            self._started = True
            self._initiative_task = self.tasks.start(
                "initiative-loop",
                lambda _token: self.initiative_engine.run_loop(),
                scope="proactive-worker",
                cancel=self.initiative_engine.stop,
            )

        prewarm_started = False
        if self.speech_service is not None:
            prewarm_started = self.speech_service.prewarm(
                on_complete=self._start_memory_tasks
            )
        if not prewarm_started:
            self._start_memory_tasks()
        return True

    def create_greeting(self):
        turn_id = self.begin_turn("greeting")
        with self.state_lock:
            emotion_snapshot = copy.deepcopy(self.emotion)
            relationship_snapshot = copy.deepcopy(self.relationship)
            context_snapshot = copy.deepcopy(self.context.get_context())
        context_snapshot["turn_emotion"] = plan_greeting_emotion(
            "",
            emotion_snapshot,
            relationship_snapshot,
        )
        greeting = generate_greeting(context_snapshot)
        if not self.is_turn_current(turn_id):
            return None
        greeting_emotion = plan_greeting_emotion(
            greeting,
            emotion_snapshot,
            relationship_snapshot,
        )
        with self.state_lock:
            if not self.is_turn_current(turn_id):
                return None
            update_emotion(
                self.emotion,
                interaction=greeting_emotion,
                consume_energy=False,
            )
            save_emotion(self.emotion)
            self.context.update(self.emotion, self.profile, self.relationship)
        return RuntimeMessage(turn_id=turn_id, text=greeting, source="greeting")

    def _deliver_proactive_message(self, message):
        turn_id = self.initiative_engine.last_turn_id
        if not message or not self.is_turn_current(turn_id):
            return
        callback = self._on_proactive_message
        if callable(callback):
            callback(message, turn_id)
        else:
            print(f"\n\n[Mio 突然找你说话]\nMio:\n{message}\n")

    def speak(self, text, turn_id=None):
        if self.speech_service is None or not text:
            return False
        if turn_id is not None and not self.is_turn_current(turn_id):
            return False
        with self.state_lock:
            emotion = copy.deepcopy(self.emotion)
        return self.speech_service.speak(
            text,
            emotion.get("mood", "neutral"),
            emotion_strength=emotion.get("mood_strength", 1.0),
            modifier=emotion.get("modifier", "none"),
            fatigue_strength=emotion.get("fatigue_strength", 0.0),
            voice_style=emotion.get("voice_style", "conversational"),
            voice_style_strength=emotion.get("voice_style_strength", 0.4),
            turn_id=turn_id,
        )

    def task_snapshots(self, active_only=False):
        return self.tasks.snapshots(active_only=active_only)

    def shutdown(self, timeout=2.0):
        with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
        self.turns.close()
        self.initiative_engine.stop()
        if self.speech_service is not None:
            self.speech_service.shutdown()
        self.orchestrator.shutdown()
        if self._initiative_task is not None:
            self._initiative_task.cancel()
            self._initiative_task.join(timeout=timeout)
        self.tasks.shutdown(timeout=timeout)
