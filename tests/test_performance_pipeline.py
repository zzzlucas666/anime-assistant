import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import event_manager
import long_term_memory
import semantic_memory
from context_manager import ContextManager
from orchestrator import ConversationOrchestrator


class SemanticFallbackTests(unittest.TestCase):
    def test_similarity_falls_back_without_waiting_for_loading_model(self):
        candidates = [
            {"id": "related", "event": "下周数学考试很重要", "embedding": None},
            {"id": "other", "event": "今天晚饭吃了蛋糕", "embedding": None},
        ]
        with (
            patch.object(semantic_memory, "_model_state", "loading"),
            patch.object(semantic_memory, "_model", None),
        ):
            started_at = time.perf_counter()
            scores = semantic_memory.compute_similarity_scores("数学考试", candidates)
            duration = time.perf_counter() - started_at

        self.assertLess(duration, 0.1)
        self.assertGreater(scores["related"], scores["other"])

    def test_ready_model_uses_lexical_fallback_for_event_without_embedding(self):
        candidates = [
            {"id": "vector", "event": "unrelated", "embedding": [1.0, 0.0]},
            {"id": "missing", "event": "数学考试复习", "embedding": None},
        ]
        with patch("semantic_memory.embed_text", return_value=[1.0, 0.0]):
            scores = semantic_memory.compute_similarity_scores("数学考试", candidates)

        self.assertIn("vector", scores)
        self.assertIn("missing", scores)
        self.assertGreater(scores["missing"], 0)


class EventCacheTests(unittest.TestCase):
    def test_unchanged_event_file_is_parsed_only_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = Path(temp_dir) / "events.json"
            event_path.write_text(json.dumps([{"id": "1", "event": "x"}]), encoding="utf-8")
            original_loader = event_manager.safe_load_json

            with (
                patch.object(event_manager, "EVENT_PATH", str(event_path)),
                patch("event_manager.safe_load_json", wraps=original_loader) as loader,
            ):
                event_manager.clear_event_cache()
                first = event_manager.load_all_events()
                second = event_manager.load_all_events()

            event_manager.clear_event_cache()

        self.assertEqual(first, second)
        self.assertEqual(loader.call_count, 1)


class SummaryBatchTests(unittest.TestCase):
    def test_pending_messages_are_persisted_and_summarized_as_a_batch(self):
        messages = [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "two"},
            {"role": "user", "content": "three"},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            pending_path = Path(temp_dir) / "pending.json"
            summary_path = Path(temp_dir) / "summaries.json"
            with (
                patch.object(long_term_memory, "PENDING_SUMMARY_PATH", str(pending_path)),
                patch.object(long_term_memory, "SUMMARY_PATH", str(summary_path)),
            ):
                long_term_memory.queue_summary_messages(messages[:2])
                with patch("long_term_memory.summarize_overflow") as summarize:
                    self.assertFalse(long_term_memory.summarize_pending_if_ready("k", "m", batch_size=3))
                    summarize.assert_not_called()

                long_term_memory.queue_summary_messages(messages[2:])
                with patch("long_term_memory.summarize_overflow", return_value={}) as summarize:
                    self.assertTrue(long_term_memory.summarize_pending_if_ready("k", "m", batch_size=3))
                    summarize.assert_called_once_with("k", "m", messages, None)

                self.assertEqual(long_term_memory.load_pending_summary_messages(), [])


class BackgroundPostprocessTests(unittest.TestCase):
    def test_finalize_returns_before_slow_event_extraction_finishes(self):
        config = {"api_key": "unused", "model": "unused", "base_url": None}
        emotion = {"mood": "neutral", "energy": 80}
        profile = {"name": "", "nickname": "", "names": [], "nicknames": [], "likes": [], "dislikes": []}
        relationship = {"affection": 30, "trust": 30, "familiarity": 10}
        history = [{"role": "user", "content": "hello"}]
        context = ContextManager(config, emotion, profile, relationship)
        state_updated = Mock()
        orchestrator = ConversationOrchestrator(
            config,
            context,
            history,
            emotion,
            profile,
            relationship,
            lock=threading.Lock(),
            on_state_updated=state_updated,
        )
        extraction_started = threading.Event()
        release_extraction = threading.Event()

        def slow_extract(*args, **kwargs):
            extraction_started.set()
            release_extraction.wait(timeout=2)
            return None

        prepared = {"clean_message": "hello", "router_reply": None}

        try:
            with (
                patch("orchestrator.save_memory", side_effect=lambda shared: (shared, [])),
                patch("orchestrator.queue_summary_messages"),
                patch("orchestrator.extract_event", side_effect=slow_extract),
                patch("orchestrator.save_emotion"),
                patch("orchestrator.save_event"),
                patch("orchestrator.update_relationship", side_effect=lambda state, event: state),
                patch("orchestrator.save_relationship"),
                patch("orchestrator.summarize_pending_if_ready", return_value=False),
            ):
                started_at = time.perf_counter()
                reply = orchestrator.finalize_turn(prepared, "reply")
                finalize_duration = time.perf_counter() - started_at

                self.assertTrue(extraction_started.wait(timeout=1))
                self.assertLess(finalize_duration, 0.1)
                self.assertEqual(reply, "reply")
                self.assertEqual(history[-1], {"role": "assistant", "content": "reply"})

                release_extraction.set()
                orchestrator._postprocess_queue.join()

            state_updated.assert_called_once()
        finally:
            release_extraction.set()
            orchestrator.shutdown()


if __name__ == "__main__":
    unittest.main()
