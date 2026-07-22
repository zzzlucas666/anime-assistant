"""Day34 regression coverage for runtime supervision and turn identity."""

from io import BytesIO
import queue
import threading
import time
import unittest
from unittest.mock import patch
import wave

from anime_assistant.runtime.application import ApplicationRuntime
from anime_assistant.conversation.context_manager import ContextManager
from anime_assistant.conversation.orchestrator import ConversationOrchestrator
from anime_assistant.runtime.supervisor import TaskSupervisor
from anime_assistant.runtime.turns import TurnCoordinator
from anime_assistant.speech.jobs import SpeechJob
from anime_assistant.speech.service import SpeechSynthesisService


def _silent_wav():
    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x00\x00" * 80)
    return output.getvalue()


class TurnCoordinatorTests(unittest.TestCase):
    def test_turn_ids_are_monotonic_and_only_latest_is_current(self):
        turns = TurnCoordinator()
        first = turns.begin("greeting")
        second = turns.begin("user")

        self.assertEqual(first.turn_id, "turn-00000001-greeting")
        self.assertEqual(second.turn_id, "turn-00000002-user")
        self.assertFalse(turns.is_current(first.turn_id))
        self.assertTrue(turns.is_current(second.turn_id))


class TaskSupervisorTests(unittest.TestCase):
    def test_stale_turn_task_receives_cooperative_cancellation(self):
        turns = TurnCoordinator()
        supervisor = TaskSupervisor(turns.is_current)
        first = turns.begin("user")
        stopped = threading.Event()

        def work(token):
            while not token.cancelled:
                time.sleep(0.001)
            stopped.set()

        handle = supervisor.start(
            "old-turn",
            work,
            turn_id=first.turn_id,
            scope="conversation",
        )
        second = turns.begin("user")
        self.assertEqual(
            supervisor.cancel_stale_turns(
                second.turn_id,
                scopes={"conversation"},
            ),
            1,
        )
        self.assertTrue(stopped.wait(1.0))
        handle.join(timeout=1.0)
        snapshot = next(
            item for item in supervisor.snapshots() if item.task_id == handle.task_id
        )
        self.assertEqual(snapshot.state, "cancelled")
        supervisor.shutdown()


class SpeechTurnTests(unittest.TestCase):
    def test_legacy_speech_jobs_remain_compatible(self):
        job = SpeechJob.from_legacy(("hello", "happy"))
        self.assertEqual(job.text, "hello")
        self.assertEqual(job.mood, "happy")
        self.assertIsNone(job.turn_id)

    def test_completed_audio_from_stale_turn_is_silently_discarded(self):
        current = {"turn_id": "turn-1"}
        supervisor = TaskSupervisor(
            lambda turn_id: turn_id is None or current["turn_id"] == turn_id
        )

        class FakeClient:
            endpoint = "fake"
            backend_name = "mio_gpt_sovits_v2proplus"
            supports_voice_style = False
            supports_mood_reference = False

            def __init__(self):
                self.close_calls = 0

            @staticmethod
            def is_available():
                return True

            def synthesize(self, *_args, **_kwargs):
                current["turn_id"] = "turn-2"
                return _silent_wav()

            def close(self):
                self.close_calls += 1

        service = SpeechSynthesisService.__new__(SpeechSynthesisService)
        service.config = {
            "tts_translate_to_japanese": False,
            "tts_speed_scale": 1.0,
            "tts_volume_scale": 1.0,
        }
        client = FakeClient()
        service.client = client
        service.fallback_client = None
        service.translator = None
        service.local_retry_attempts = 1
        service._jobs = queue.Queue()
        service._stop_event = threading.Event()
        service._turn_checker = supervisor.is_turn_current
        service.task_supervisor = supervisor
        audio = []
        errors = []
        service.on_audio_ready = audio.append
        service.on_error = errors.append
        service.on_status = lambda _status: None
        service._jobs.put(SpeechJob("hello", turn_id="turn-1"))
        service._jobs.put(None)

        service._run()

        self.assertEqual(audio, [])
        self.assertEqual(errors, [])
        self.assertEqual(client.close_calls, 0)
        supervisor.shutdown()


class ApplicationRuntimeTests(unittest.TestCase):
    @patch("anime_assistant.runtime.application.schedule_embedding_backfill")
    @patch("anime_assistant.runtime.application.warmup_model_async")
    @patch("anime_assistant.runtime.application.load_relationship")
    @patch("anime_assistant.runtime.application.load_profile")
    @patch("anime_assistant.runtime.application.load_emotion")
    @patch("anime_assistant.runtime.application.load_memory")
    def test_runtime_owns_shared_services_and_shutdown(
        self,
        load_memory,
        load_emotion,
        load_profile,
        load_relationship,
        warmup,
        backfill,
    ):
        load_memory.return_value = []
        load_emotion.return_value = {"mood": "neutral", "energy": 100}
        load_profile.return_value = {"name": "", "likes": [], "dislikes": []}
        load_relationship.return_value = {
            "affection": 30,
            "trust": 30,
            "familiarity": 10,
        }
        config = {
            "api_key": "unused",
            "model": "unused",
            "tts_enabled": False,
            "proactive_check_interval_minutes": 5,
            "proactive_idle_threshold_minutes": 30,
            "proactive_min_interval_minutes": 120,
            "proactive_max_per_day": 3,
        }
        runtime = ApplicationRuntime(config, enable_speech=False)
        try:
            self.assertIs(runtime.orchestrator.task_supervisor, runtime.tasks)
            self.assertIs(runtime.initiative_engine.task_supervisor, runtime.tasks)
            self.assertTrue(runtime.start())
            self.assertFalse(runtime.start())
            turn_id = runtime.begin_turn("user")
            self.assertTrue(runtime.is_turn_current(turn_id))
            warmup.assert_called_once_with(task_supervisor=runtime.tasks)
            backfill.assert_called_once_with(task_supervisor=runtime.tasks)
        finally:
            runtime.shutdown()


class StalePostprocessTests(unittest.TestCase):
    def test_old_turn_may_save_fact_but_cannot_mutate_live_state(self):
        config = {"api_key": "unused", "model": "unused"}
        emotion = {"mood": "neutral", "energy": 80}
        profile = {"name": "", "nickname": "", "likes": [], "dislikes": []}
        relationship = {"affection": 30, "trust": 30, "familiarity": 10}
        context = ContextManager(config, emotion, profile, relationship)
        turns = TurnCoordinator()
        supervisor = TaskSupervisor(turns.is_current)
        orchestrator = ConversationOrchestrator(
            config,
            context,
            [],
            emotion,
            profile,
            relationship,
            turn_coordinator=turns,
            task_supervisor=supervisor,
        )
        old_turn = turns.begin("user").turn_id
        turns.begin("user")
        task = {
            "turn_id": old_turn,
            "clean_message": "I started an internship",
            "reply": "That sounds busy.",
            "router_reply": None,
            "profile_strategy": "none",
            "immediate_emotion_applied": False,
        }
        event = {
            "event": "started an internship",
            "importance": 0.9,
            "source": "user_explicit",
            "status": "confirmed",
        }
        try:
            with (
                patch(
                    "anime_assistant.conversation.orchestrator.extract_event",
                    return_value=event,
                ),
                patch(
                    "anime_assistant.conversation.orchestrator.can_event_affect_state",
                    return_value=True,
                ),
                patch("anime_assistant.conversation.orchestrator.save_event") as save_event,
                patch("anime_assistant.conversation.orchestrator.update_emotion") as update_emotion,
                patch(
                    "anime_assistant.conversation.orchestrator.update_relationship"
                ) as update_relationship,
                patch(
                    "anime_assistant.conversation.orchestrator.summarize_pending_if_ready",
                    return_value=False,
                ),
            ):
                orchestrator._postprocess_turn(task)

            save_event.assert_called_once_with(event)
            update_emotion.assert_not_called()
            update_relationship.assert_not_called()
            self.assertEqual(emotion["mood"], "neutral")
            self.assertEqual(relationship["affection"], 30)
        finally:
            orchestrator.shutdown()
            supervisor.shutdown()


if __name__ == "__main__":
    unittest.main()
