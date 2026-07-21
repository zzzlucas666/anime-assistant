import unittest
from unittest.mock import Mock, patch

from anime_assistant.ai import chat
from anime_assistant.conversation.intent_manager import _local_detect_intent
from anime_assistant.conversation.router import handle_intent


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

    def test_router_describes_neutral_mood_in_natural_language(self):
        reply = handle_intent(
            "emotion_query",
            "你现在开心吗",
            {},
            {"mood": "neutral", "energy": 80},
            {"affection": 30},
        )

        self.assertEqual(reply, "现在还说不上很开心，心情比较平静。")


class ConversationStylePromptTests(unittest.TestCase):
    def test_proactive_emotion_hint_does_not_invent_current_user_input(self):
        hint = chat.build_turn_emotion_hint(
            {
                "source": "proactive",
                "mood": "neutral",
                "modifier": "worried",
                "modifier_strength": 0.7,
                "voice_style": "concerned",
                "voice_style_strength": 0.8,
            }
        )

        self.assertIn("Mio 主动开口", hint)
        self.assertIn("认真关心对方", hint)
        self.assertIn("不要假装用户刚刚说过一句话", hint)

    def test_greeting_prompt_receives_independent_voice_style(self):
        client = Mock()
        response = Mock()
        response.choices = [Mock(message=Mock(content="啊，你来了。"))]
        client.chat.completions.create.return_value = response
        context = {
            "config": {
                "api_key": "unused",
                "base_url": "https://example.invalid",
                "model": "test-model",
            },
            "profile": {
                "name": "",
                "nickname": "",
                "likes": [],
                "dislikes": [],
            },
            "emotion": {"mood": "neutral", "energy": 80},
            "relationship": {"affection": 50, "trust": 40, "familiarity": 40},
            "turn_emotion": {
                "source": "greeting",
                "mood": "neutral",
                "modifier": "none",
                "voice_style": "warm",
                "voice_style_strength": 0.6,
            },
        }

        with patch("anime_assistant.ai.chat.create_ai_client", return_value=client):
            greeting = chat.generate_greeting(context)

        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(greeting, "啊，你来了。")
        self.assertIn("程序启动后的见面问候", prompt)
        self.assertIn("温暖亲近", prompt)

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
        with patch("anime_assistant.ai.chat.build_memory_context", return_value=memory):
            prompt = chat.build_system_prompt(context, "你喜欢什么天气")

        self.assertLess(
            prompt.index("Identity｜固定身份"),
            prompt.index("Values｜交流价值观"),
        )
        self.assertLess(
            prompt.index("Values｜交流价值观"),
            prompt.index("Behavior｜当前行为倾向"),
        )
        self.assertLess(
            prompt.index("Behavior｜当前行为倾向"),
            prompt.index("Context｜本轮动态上下文"),
        )
        self.assertLess(
            prompt.index("Context｜本轮动态上下文"),
            prompt.index("Output Rules｜输出契约"),
        )
        self.assertIn("日常聊天通常回复 1~2 句", prompt)
        self.assertIn("12~55 个汉字", prompt)
        self.assertIn("散文或连续比喻", prompt)
        self.assertIn("不使用换行列表、括号动作", prompt)
        self.assertIn("不编造未经确认的事实", prompt)
        self.assertIn("不主动提贝斯", prompt)
        self.assertIn("记忆只用于理解背景", prompt)
        self.assertIn("真诚优先于讨好", prompt)
        self.assertNotIn("好感度 affection", prompt)
        self.assertNotIn("信任度 trust", prompt)
        self.assertIn("<mio:USER_MOOD|REACTION|VOICE_STYLE|STRENGTH|CONFIDENCE>", prompt)
        self.assertIn("用户难过、焦虑或疲惫时", prompt)

    def test_proactive_prompt_can_disable_interactive_control_tag(self):
        context = {
            "profile": {"name": "", "nickname": "", "likes": [], "dislikes": []},
            "emotion": {"mood": "neutral", "energy": 80},
            "relationship": {"affection": 30, "trust": 30, "familiarity": 10},
        }
        memory = {
            "event_memory_hint": "无",
            "long_term_summary_hint": "无",
        }
        with patch("anime_assistant.ai.chat.build_memory_context", return_value=memory):
            prompt = chat.build_system_prompt(
                context,
                "主动找用户聊天",
                include_emotion_control=False,
                mode="proactive",
                purpose_hint="已经有一段时间没有聊天",
            )

        self.assertNotIn("<mio:USER_MOOD|REACTION|VOICE_STYLE", prompt)
        self.assertIn("当前由 Mio 主动开启话题", prompt)
        self.assertIn("不解释触发原因", prompt)

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
            patch("anime_assistant.ai.chat.build_system_prompt", return_value="system"),
            patch("anime_assistant.ai.chat.create_ai_client", return_value=client),
        ):
            chat._create_stream(
                [{"role": "user", "content": "你喜欢什么天气"}],
                context,
            )

        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["max_tokens"], 112)
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
            patch("anime_assistant.ai.chat.build_system_prompt", return_value="system"),
            patch("anime_assistant.ai.chat.create_ai_client", return_value=client),
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
            patch("anime_assistant.ai.chat.build_system_prompt", return_value="system"),
            patch("anime_assistant.ai.chat.create_ai_client", return_value=client),
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

        with patch("anime_assistant.ai.chat._create_stream", side_effect=[[], [reply_chunk]]) as create_stream:
            result = list(chat.chat_with_ai_stream([], {}))

        self.assertEqual(result, ["嗯，会有一点。不过熟悉之后就好多了。"])
        self.assertEqual(create_stream.call_count, 2)

    def test_two_empty_streams_return_visible_fallback(self):
        fallback = "抱歉…刚刚好像没听清，可以再说一遍吗？"

        with (
            patch("anime_assistant.ai.chat._create_stream", side_effect=[[], []]) as create_stream,
            patch("random.choice", return_value=fallback),
        ):
            result = list(chat.chat_with_ai_stream([], {}))

        self.assertEqual(result, [fallback])
        self.assertEqual(create_stream.call_count, 2)

    def test_hidden_emotion_tag_is_filtered_across_stream_chunks(self):
        chunks = [
            self._content_chunk("嗯，会有一点。不过熟悉以后会好些。<mi"),
            self._content_chunk("o:neutral|shy|bashful|0.72|0.86"),
            self._content_chunk(">"),
        ]
        controls = []

        with patch("anime_assistant.ai.chat._create_stream", return_value=chunks):
            result = list(chat.chat_with_ai_stream(
                [], {}, on_emotion_control=controls.append
            ))

        self.assertEqual("".join(result), "嗯，会有一点。不过熟悉以后会好些。")
        self.assertNotIn("<mio:", "".join(result))
        self.assertEqual(controls, [{
            "user_mood": "neutral",
            "reaction": "shy",
            "voice_style": "bashful",
            "strength": 0.72,
            "confidence": 0.86,
        }])

    def test_missing_control_tag_keeps_visible_reply_unchanged(self):
        chunks = [self._content_chunk("普通回复末尾刚好有<mi字样")]
        controls = []

        with patch("anime_assistant.ai.chat._create_stream", return_value=chunks):
            result = list(chat.chat_with_ai_stream(
                [], {}, on_emotion_control=controls.append
            ))

        self.assertEqual("".join(result), "普通回复末尾刚好有<mi字样")
        self.assertEqual(controls, [])

    def test_invalid_control_tag_is_hidden_and_ignored(self):
        chunks = [self._content_chunk(
            "回复。<mio:neutral|dancing|loud|0.9|0.9>"
        )]
        controls = []

        with patch("anime_assistant.ai.chat._create_stream", return_value=chunks):
            result = list(chat.chat_with_ai_stream(
                [], {}, on_emotion_control=controls.append
            ))

        self.assertEqual("".join(result), "回复。")
        self.assertEqual(controls, [])


if __name__ == "__main__":
    unittest.main()
