import threading
import unittest
import datetime
from unittest.mock import Mock, patch

from anime_assistant.proactive.initiative_engine import InitiativeEngine


class InitiativeEngineCompatibilityTests(unittest.TestCase):
    def test_missing_legacy_event_id_does_not_drop_generated_message(self):
        context = Mock()
        context.get_context.return_value = {"context": "snapshot"}
        engine = InitiativeEngine(
            config={"api_key": "unused", "model": "unused"},
            context=context,
            conversation_history=[],
            emotion={"mood": "neutral", "energy": 80},
            profile={},
            relationship={"familiarity": 10},
            lock=threading.Lock(),
        )
        signals = {
            "event_score": 1.0,
            "emotion_score": 0.0,
            "idle_score": 0.0,
            "top_event": {"event": "legacy", "importance": 1.0},
            "idle_minutes": 60,
            "mood": "neutral",
            "energy": 80,
            "familiarity_pct": 10,
        }

        with (
            patch("anime_assistant.proactive.initiative_engine.can_trigger_proactive", return_value=True),
            patch("anime_assistant.proactive.initiative_engine.load_last_interaction_time", return_value=None),
            patch.object(engine, "_compute_signals", return_value=signals),
            patch("anime_assistant.proactive.initiative_engine.generate_proactive_message", return_value="generated") as generate,
            patch("anime_assistant.proactive.initiative_engine.mark_event_notified") as mark_notified,
            patch("anime_assistant.proactive.initiative_engine.save_emotion"),
            patch.object(engine, "_record_message", return_value=[]) as record_message,
            patch("anime_assistant.proactive.initiative_engine.summarize_pending_if_ready", return_value=False),
        ):
            message = engine.check_and_trigger()

        self.assertEqual(message, "generated")
        generate.assert_called_once()
        mark_notified.assert_not_called()
        record_message.assert_called_once_with("generated")

    def test_ai_generation_runs_without_holding_state_lock(self):
        state_lock = threading.Lock()
        context = Mock()
        context.get_context.return_value = {"nested": {"value": 1}}
        engine = InitiativeEngine(
            config={"api_key": "unused", "model": "unused"},
            context=context,
            conversation_history=[],
            emotion={"mood": "neutral", "energy": 80},
            profile={},
            relationship={"familiarity": 10},
            lock=state_lock,
        )
        interaction_time = datetime.datetime.now() - datetime.timedelta(hours=1)
        signals = {
            "event_score": 1.0,
            "emotion_score": 0.0,
            "idle_score": 0.0,
            "top_event": None,
            "idle_minutes": 60,
            "mood": "neutral",
            "energy": 80,
            "familiarity_pct": 10,
        }

        def generate_while_unlocked(context_snapshot, reason_hint):
            self.assertFalse(state_lock.locked())
            context_snapshot["nested"]["value"] = 2
            self.assertEqual(context.get_context.return_value["nested"]["value"], 1)
            return "generated"

        with (
            patch("anime_assistant.proactive.initiative_engine.can_trigger_proactive", return_value=True),
            patch("anime_assistant.proactive.initiative_engine.load_last_interaction_time", return_value=interaction_time),
            patch.object(engine, "_compute_signals", return_value=signals),
            patch("anime_assistant.proactive.initiative_engine.generate_proactive_message", side_effect=generate_while_unlocked),
            patch("anime_assistant.proactive.initiative_engine.save_emotion"),
            patch.object(engine, "_record_message", return_value=[]) as record_message,
            patch("anime_assistant.proactive.initiative_engine.summarize_pending_if_ready", return_value=False),
        ):
            message = engine.check_and_trigger()

        self.assertEqual(message, "generated")
        record_message.assert_called_once_with("generated")

    def test_proactive_concern_is_committed_before_message_delivery(self):
        context = Mock()
        context.get_context.return_value = {
            "config": {"api_key": "unused", "model": "unused"},
            "profile": {},
            "emotion": {"mood": "neutral", "energy": 80},
            "relationship": {"familiarity": 50},
        }
        emotion = {"mood": "neutral", "energy": 80}
        engine = InitiativeEngine(
            config={"api_key": "unused", "model": "unused"},
            context=context,
            conversation_history=[],
            emotion=emotion,
            profile={},
            relationship={"familiarity": 50},
            lock=threading.Lock(),
        )
        signals = {
            "event_score": 0.9,
            "emotion_score": 0.0,
            "idle_score": 0.3,
            "top_event": {
                "id": "event-1",
                "event": "用户之前说自己很难过",
                "importance": 0.9,
                "emotion": "worried",
                "user_emotion": "sad",
            },
            "idle_minutes": 60,
            "mood": "neutral",
            "energy": 80,
            "familiarity_pct": 50,
        }

        def generate(context_snapshot, _reason_hint):
            self.assertEqual(
                context_snapshot["turn_emotion"]["voice_style"],
                "concerned",
            )
            return "你今天还好吗？我有点担心。"

        def record_after_emotion(_message):
            self.assertEqual(emotion["modifier"], "worried")
            self.assertEqual(emotion["voice_style"], "concerned")
            return []

        with (
            patch("anime_assistant.proactive.initiative_engine.can_trigger_proactive", return_value=True),
            patch("anime_assistant.proactive.initiative_engine.load_last_interaction_time", return_value=None),
            patch.object(engine, "_compute_signals", return_value=signals),
            patch("anime_assistant.proactive.initiative_engine.generate_proactive_message", side_effect=generate),
            patch("anime_assistant.proactive.initiative_engine.mark_event_notified"),
            patch("anime_assistant.proactive.initiative_engine.save_emotion"),
            patch.object(engine, "_record_message", side_effect=record_after_emotion),
            patch("anime_assistant.proactive.initiative_engine.summarize_pending_if_ready", return_value=False),
        ):
            message = engine.check_and_trigger()

        self.assertEqual(message, "你今天还好吗？我有点担心。")
        context.update.assert_called()

    def test_user_interaction_during_generation_discards_stale_message(self):
        context = Mock()
        context.get_context.return_value = {}
        engine = InitiativeEngine(
            config={"api_key": "unused", "model": "unused"},
            context=context,
            conversation_history=[],
            emotion={"mood": "neutral", "energy": 80},
            profile={},
            relationship={"familiarity": 10},
            lock=threading.Lock(),
        )
        before = datetime.datetime.now() - datetime.timedelta(hours=1)
        after = datetime.datetime.now()
        signals = {
            "event_score": 1.0,
            "emotion_score": 0.0,
            "idle_score": 0.0,
            "top_event": None,
            "idle_minutes": 60,
            "mood": "neutral",
            "energy": 80,
            "familiarity_pct": 10,
        }

        with (
            patch("anime_assistant.proactive.initiative_engine.can_trigger_proactive", return_value=True),
            patch("anime_assistant.proactive.initiative_engine.load_last_interaction_time", side_effect=[before, after]),
            patch.object(engine, "_compute_signals", return_value=signals),
            patch("anime_assistant.proactive.initiative_engine.generate_proactive_message", return_value="stale"),
            patch.object(engine, "_record_message") as record_message,
        ):
            message = engine.check_and_trigger()

        self.assertIsNone(message)
        record_message.assert_not_called()

    def test_run_loop_does_not_emit_callback_after_stop(self):
        callback = Mock()
        engine = InitiativeEngine(
            config={"api_key": "unused", "model": "unused"},
            context=Mock(),
            conversation_history=[],
            emotion={},
            profile={},
            relationship={},
            lock=threading.Lock(),
            check_interval_minutes=0,
            on_message=callback,
        )

        def finish_while_returning_message():
            engine.stop()
            return "generated"

        with patch.object(engine, "check_and_trigger", side_effect=finish_while_returning_message):
            engine.run_loop()

        callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
