import threading
import unittest
from unittest.mock import patch

from context_manager import ContextManager
from orchestrator import ConversationOrchestrator


class OrchestratorSnapshotTests(unittest.TestCase):
    def test_prepare_turn_returns_isolated_history_and_context_snapshots(self):
        config = {"api_key": "unused", "model": "unused"}
        emotion = {"mood": "neutral", "energy": 80}
        profile = {"name": "", "nickname": "", "likes": [], "dislikes": []}
        relationship = {"affection": 30, "trust": 30, "familiarity": 10}
        history = []
        context = ContextManager(config, emotion, profile, relationship)
        orchestrator = ConversationOrchestrator(
            config,
            context,
            history,
            emotion,
            profile,
            relationship,
            lock=threading.Lock(),
        )

        def preserve_history(shared_history):
            return shared_history, []

        try:
            with (
                patch("orchestrator.detect_intent", return_value={"intent": "chat", "confidence": 1.0}),
                patch("orchestrator.save_memory", side_effect=preserve_history),
                patch("orchestrator.update_last_interaction_time"),
            ):
                prepared = orchestrator.prepare_turn("hello")

            history.append({"role": "assistant", "content": "later"})
            emotion["mood"] = "sad"

            self.assertEqual(len(prepared["conversation_snapshot"]), 1)
            self.assertEqual(prepared["conversation_snapshot"][0]["content"], "hello")
            self.assertEqual(prepared["context_snapshot"]["emotion"]["mood"], "neutral")
        finally:
            orchestrator.shutdown()


if __name__ == "__main__":
    unittest.main()
