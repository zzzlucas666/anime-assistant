import threading
import time
import unittest
from unittest.mock import patch

from anime_assistant.character.profile_parser import parse_explicit_profile_update
from anime_assistant.conversation.context_manager import ContextManager
from anime_assistant.conversation.intent_manager import plan_local_route
from anime_assistant.conversation.orchestrator import ConversationOrchestrator


class Day30LocalRoutingTests(unittest.TestCase):
    def test_fixed_route_regression_examples(self):
        examples = (
            ("我喜欢 Radiohead", "set_profile", "local", False),
            ("我喜欢什么", "get_profile", "none", True),
            ("你喜欢什么样的男生", "chat", "none", False),
            ("你还记得我喜欢什么吗", "get_profile", "none", True),
            ("你还记得昨天那件事吗", "chat", "none", False),
            ("我今天很开心", "chat", "none", False),
            ("你现在开心吗", "emotion_query", "none", True),
            ("最近迷上爵士乐了", "set_profile", "deferred_ai", False),
            ("我喜欢你", "chat", "none", False),
        )

        for message, intent, profile_strategy, router_eligible in examples:
            with self.subTest(message=message):
                decision = plan_local_route(message)
                self.assertEqual(decision.intent, intent)
                self.assertEqual(decision.profile_strategy, profile_strategy)
                self.assertEqual(decision.router_eligible, router_eligible)

    def test_explicit_profile_parser_is_anchored_and_question_safe(self):
        update = parse_explicit_profile_update("我喜欢 Radiohead")
        self.assertIsNotNone(update)
        self.assertEqual(update.action, "add_like")
        self.assertEqual(update.value, "Radiohead")

        correction = parse_explicit_profile_update("我现在不喜欢咖啡了")
        self.assertIsNotNone(correction)
        self.assertEqual(correction.action, "add_dislike")
        self.assertEqual(correction.value, "咖啡")

        self.assertIsNone(parse_explicit_profile_update("我喜欢什么"))
        self.assertIsNone(parse_explicit_profile_update("我喜欢你"))
        self.assertIsNone(parse_explicit_profile_update("我喜欢咖啡吗？"))
        self.assertIsNone(
            parse_explicit_profile_update("我喜欢咖啡，不过最近更常喝茶")
        )
        self.assertEqual(
            plan_local_route("我喜欢咖啡，不过最近更常喝茶").profile_strategy,
            "deferred_ai",
        )


class Day30OrchestratorTests(unittest.TestCase):
    def _make_orchestrator(self):
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
        return orchestrator, profile

    def test_ordinary_chat_has_no_preflight_ai_call(self):
        orchestrator, _profile = self._make_orchestrator()
        try:
            with (
                patch("anime_assistant.conversation.intent_manager.create_ai_client") as client_mock,
                patch("anime_assistant.conversation.orchestrator.extract_profile_info") as extract_mock,
                patch(
                    "anime_assistant.conversation.orchestrator.save_memory",
                    side_effect=lambda items: (items, []),
                ),
                patch("anime_assistant.conversation.orchestrator.update_last_interaction_time"),
            ):
                prepared = orchestrator.prepare_turn("今天练习有点累")

            self.assertEqual(prepared["intent"], "chat")
            self.assertEqual(prepared["route_source"], "local_chat")
            client_mock.assert_not_called()
            extract_mock.assert_not_called()
        finally:
            orchestrator.shutdown()

    def test_explicit_profile_update_is_local_and_query_never_extracts(self):
        orchestrator, profile = self._make_orchestrator()
        try:
            with (
                patch("anime_assistant.conversation.orchestrator.extract_profile_info") as extract_mock,
                patch("anime_assistant.conversation.orchestrator.save_profile"),
                patch(
                    "anime_assistant.conversation.orchestrator.save_memory",
                    side_effect=lambda items: (items, []),
                ),
                patch("anime_assistant.conversation.orchestrator.update_last_interaction_time"),
            ):
                explicit = orchestrator.prepare_turn("我喜欢 Radiohead")
                query = orchestrator.prepare_turn("我喜欢什么")

            self.assertEqual(explicit["profile_strategy"], "local")
            self.assertIn("Radiohead", profile["likes"])
            self.assertEqual(query["intent"], "get_profile")
            self.assertIn("Radiohead", query["router_reply"])
            extract_mock.assert_not_called()
        finally:
            orchestrator.shutdown()

    def test_ambiguous_profile_extraction_starts_only_after_reply(self):
        orchestrator, profile = self._make_orchestrator()
        extraction_started = threading.Event()
        allow_extraction = threading.Event()

        def delayed_extraction(*_args, **_kwargs):
            extraction_started.set()
            allow_extraction.wait(timeout=1)
            return {"action": "add_like", "value": "爵士乐"}

        try:
            with (
                patch(
                    "anime_assistant.conversation.orchestrator.extract_profile_info",
                    side_effect=delayed_extraction,
                ) as extract_mock,
                patch("anime_assistant.conversation.orchestrator.extract_event", return_value=None),
                patch("anime_assistant.conversation.orchestrator.save_event"),
                patch("anime_assistant.conversation.orchestrator.save_profile"),
                patch("anime_assistant.conversation.orchestrator.save_emotion"),
                patch(
                    "anime_assistant.conversation.orchestrator.save_memory",
                    side_effect=lambda items: (items, []),
                ),
                patch("anime_assistant.conversation.orchestrator.update_last_interaction_time"),
                patch("anime_assistant.conversation.orchestrator.has_interaction_signal", return_value=False),
                patch("anime_assistant.conversation.orchestrator.summarize_pending_if_ready", return_value=False),
            ):
                started_at = time.perf_counter()
                prepared = orchestrator.prepare_turn("最近迷上爵士乐了")
                prepare_duration = time.perf_counter() - started_at

                self.assertEqual(prepared["profile_strategy"], "deferred_ai")
                self.assertLess(prepare_duration, 0.2)
                extract_mock.assert_not_called()

                started_at = time.perf_counter()
                reply = orchestrator.finalize_turn(prepared, "爵士乐挺有意思的。")
                finalize_duration = time.perf_counter() - started_at

                self.assertEqual(reply, "爵士乐挺有意思的。")
                self.assertLess(finalize_duration, 0.2)
                self.assertTrue(extraction_started.wait(timeout=0.5))
                allow_extraction.set()
                orchestrator._postprocess_queue.join()

            self.assertIn("爵士乐", profile["likes"])
        finally:
            allow_extraction.set()
            orchestrator.shutdown()


if __name__ == "__main__":
    unittest.main()
