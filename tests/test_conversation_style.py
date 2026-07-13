import unittest
from unittest.mock import Mock, patch

from ai import chat
from intent_manager import _local_detect_intent
from router import handle_intent


class PreferenceRoutingTests(unittest.TestCase):
    def test_assistant_preference_question_is_normal_chat(self):
        result = _local_detect_intent("你喜欢什么样的男生")
        self.assertEqual(result["intent"], "chat")

    def test_user_profile_question_still_uses_profile_router(self):
        result = _local_detect_intent("你还记得我喜欢什么吗")
        self.assertEqual(result["intent"], "get_profile")

    def test_router_defensively_rejects_assistant_preference_question(self):
        reply = handle_intent(
            "get_profile",
            "你喜欢什么样的男生",
            {"likes": ["摇滚"], "dislikes": [], "name": "", "nickname": ""},
            {},
            {},
        )
        self.assertIsNone(reply)

    def test_router_still_answers_user_likes(self):
        reply = handle_intent(
            "get_profile",
            "我喜欢什么",
            {"likes": ["摇滚"], "dislikes": [], "name": "", "nickname": ""},
            {},
            {},
        )
        self.assertEqual(reply, "你喜欢：摇滚")


class ConversationStylePromptTests(unittest.TestCase):
    def test_prompt_requires_short_conversational_non_literary_replies(self):
        context = {
            "profile": {"name": "", "nickname": "", "likes": [], "dislikes": []},
            "emotion": {"mood": "neutral", "energy": 80},
            "relationship": {"affection": 30, "trust": 30, "familiarity": 10},
        }
        memory = {
            "event_memory_hint": "无",
            "long_term_summary_hint": "无",
        }
        with patch("ai.chat.build_memory_context", return_value=memory):
            prompt = chat.build_system_prompt(context, "你喜欢什么天气")

        self.assertIn("日常聊天通常只回复 1~2 句", prompt)
        self.assertIn("12~55 个汉字", prompt)
        self.assertIn("不写散文", prompt)
        self.assertIn("不要虚构朋友的动作", prompt)
        self.assertIn("完全不使用括号动作描写", prompt)
        self.assertIn("不要主动提贝斯", prompt)
        self.assertIn("历史内容只用于记住", prompt)
        self.assertIn("喜欢什么样的人", prompt)

    def test_chat_request_has_bounded_output_budget(self):
        client = Mock()
        client.chat.completions.create.return_value = []
        context = {
            "config": {
                "api_key": "unused",
                "base_url": "https://example.invalid",
                "model": "test-model",
            }
        }
        with (
            patch("ai.chat.build_system_prompt", return_value="system"),
            patch("ai.chat.create_ai_client", return_value=client),
        ):
            chat._create_stream(
                [{"role": "user", "content": "你喜欢什么天气"}],
                context,
            )

        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["max_tokens"], 72)
        self.assertTrue(kwargs["stream"])
        self.assertNotIn("extra_body", kwargs)

    def test_deepseek_daily_chat_explicitly_disables_thinking(self):
        client = Mock()
        client.chat.completions.create.return_value = []
        context = {
            "config": {
                "api_key": "unused",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-pro",
                "chat_thinking_enabled": False,
            }
        }
        with (
            patch("ai.chat.build_system_prompt", return_value="system"),
            patch("ai.chat.create_ai_client", return_value=client),
        ):
            chat._create_stream(
                [{"role": "user", "content": "你害怕很多人的目光吗"}],
                context,
            )

        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(
            kwargs["extra_body"],
            {"thinking": {"type": "disabled"}},
        )

    def test_deepseek_thinking_can_be_reenabled_by_config(self):
        client = Mock()
        client.chat.completions.create.return_value = []
        context = {
            "config": {
                "api_key": "unused",
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-v4-pro",
                "chat_thinking_enabled": True,
            }
        }
        with (
            patch("ai.chat.build_system_prompt", return_value="system"),
            patch("ai.chat.create_ai_client", return_value=client),
        ):
            chat._create_stream([], context)

        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(
            kwargs["extra_body"],
            {"thinking": {"type": "enabled"}},
        )

    def test_short_character_line_removes_actions_and_limits_length(self):
        text = "（低头抱紧贝斯）" + "今天发生了很多很多事情，" * 8
        result = chat._normalize_short_character_line(text, max_chars=30)

        self.assertNotIn("低头", result)
        self.assertNotIn("贝斯", result)
        self.assertLessEqual(len(result), 31)
        self.assertTrue(result.endswith("。"))


class EmptyStreamRecoveryTests(unittest.TestCase):
    @staticmethod
    def _content_chunk(text):
        chunk = Mock()
        delta = Mock(content=text, reasoning_content=None)
        chunk.choices = [Mock(delta=delta, finish_reason=None)]
        return chunk

    def test_empty_stream_is_retried_and_second_reply_is_returned(self):
        reply_chunk = self._content_chunk("嗯，会有一点。不过熟悉之后就好多了。")

        with patch("ai.chat._create_stream", side_effect=[[], [reply_chunk]]) as create_stream:
            result = list(chat.chat_with_ai_stream([], {}))

        self.assertEqual(result, ["嗯，会有一点。不过熟悉之后就好多了。"])
        self.assertEqual(create_stream.call_count, 2)

    def test_two_empty_streams_return_visible_fallback(self):
        fallback = "抱歉…刚刚好像没听清，可以再说一遍吗？"

        with (
            patch("ai.chat._create_stream", side_effect=[[], []]) as create_stream,
            patch("random.choice", return_value=fallback),
        ):
            result = list(chat.chat_with_ai_stream([], {}))

        self.assertEqual(result, [fallback])
        self.assertEqual(create_stream.call_count, 2)


if __name__ == "__main__":
    unittest.main()
