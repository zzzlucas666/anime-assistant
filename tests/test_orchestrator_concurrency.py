import threading
import unittest
from unittest.mock import patch

from anime_assistant.conversation.context_manager import ContextManager
from anime_assistant.ai.fallbacks import FALLBACK_REPLIES
from anime_assistant.conversation.orchestrator import ConversationOrchestrator


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
                patch("anime_assistant.conversation.orchestrator.save_memory", side_effect=preserve_history),
                patch("anime_assistant.conversation.orchestrator.update_last_interaction_time"),
            ):
                prepared = orchestrator.prepare_turn("hello")

            history.append({"role": "assistant", "content": "later"})
            emotion["mood"] = "sad"

            self.assertEqual(len(prepared["conversation_snapshot"]), 1)
            self.assertEqual(prepared["conversation_snapshot"][0]["content"], "hello")
            self.assertEqual(prepared["context_snapshot"]["emotion"]["mood"], "neutral")
        finally:
            orchestrator.shutdown()

    def test_transient_fallback_is_not_saved_or_postprocessed(self):
        config = {"api_key": "unused", "model": "unused"}
        emotion = {"mood": "neutral", "energy": 80}
        profile = {"name": "", "nickname": "", "likes": [], "dislikes": []}
        relationship = {"affection": 30, "trust": 30, "familiarity": 10}
        history = [{"role": "user", "content": "hello"}]
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
        prepared = {
            "router_reply": None,
            "clean_message": "hello",
        }

        def preserve_history(shared_history):
            return shared_history, []

        try:
            with patch("anime_assistant.conversation.orchestrator.save_memory", side_effect=preserve_history):
                reply = orchestrator.finalize_turn(prepared, FALLBACK_REPLIES[0])

            self.assertEqual(reply, FALLBACK_REPLIES[0])
            self.assertEqual(history, [{"role": "user", "content": "hello"}])
            self.assertTrue(orchestrator._postprocess_queue.empty())
        finally:
            orchestrator.shutdown()

    def test_prepare_turn_limits_style_context_to_recent_messages(self):
        config = {
            "api_key": "unused",
            "model": "unused",
            "chat_history_max_messages": 4,
        }
        emotion = {"mood": "neutral", "energy": 80}
        profile = {"name": "", "nickname": "", "likes": [], "dislikes": []}
        relationship = {"affection": 30, "trust": 30, "familiarity": 10}
        history = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": str(index)}
            for index in range(8)
        ]
        context = ContextManager(config, emotion, profile, relationship)
        orchestrator = ConversationOrchestrator(
            config, context, history, emotion, profile, relationship,
            lock=threading.Lock(),
        )

        try:
            with (
                patch("anime_assistant.conversation.orchestrator.save_memory", side_effect=lambda items: (items, [])),
                patch("anime_assistant.conversation.orchestrator.update_last_interaction_time"),
            ):
                prepared = orchestrator.prepare_turn("new")

            self.assertEqual(
                [item["content"] for item in prepared["conversation_snapshot"]],
                ["5", "6", "7", "new"],
            )
        finally:
            orchestrator.shutdown()


if __name__ == "__main__":
    unittest.main()
