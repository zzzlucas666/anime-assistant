import unittest

from anime_assistant.emotion.manager import (
    apply_ai_emotion_control,
    has_interaction_signal,
    infer_interaction_emotion,
    plan_greeting_emotion,
    plan_proactive_emotion,
    plan_turn_emotion,
    score_turn_emotion_candidates,
    update_emotion,
)


def emotion_state(mood="neutral", strength=0.0):
    return {
        "mood": mood,
        "energy": 80,
        "last_updated": None,
        "mood_set_at": None,
        "mood_strength": strength,
        "pending_mood": None,
        "pending_mood_count": 0,
    }


class InteractionEmotionTests(unittest.TestCase):
    def test_personal_compliment_keeps_shy_and_happy_candidates(self):
        candidates = score_turn_emotion_candidates(
            "感觉你好可爱",
            emotion_state(),
            {"affection": 30, "familiarity": 10},
        )

        reactions = {item["reaction"] for item in candidates}
        self.assertIn("shy", reactions)
        self.assertIn("happy", reactions)
        self.assertEqual(candidates[0]["reaction"], "shy")

    def test_close_happy_relationship_shifts_direct_affection_to_happy(self):
        candidates = score_turn_emotion_candidates(
            "我喜欢你",
            emotion_state("happy", 0.7),
            {"affection": 80, "familiarity": 70},
        )

        self.assertEqual(candidates[0]["reaction"], "happy")

    def test_intensified_direct_affection_is_still_recognized(self):
        signal = plan_turn_emotion(
            "我真的很喜欢你",
            emotion_state("happy", 0.7),
            {"affection": 80, "familiarity": 70},
        )

        self.assertEqual(signal["mood"], "happy")
        self.assertEqual(signal["modifier"], "touched")
        self.assertEqual(signal["voice_style"], "warm")

    def test_user_sadness_becomes_concern_not_mio_sadness(self):
        signal = plan_turn_emotion("我今天很难过，什么都不想做")

        self.assertEqual(signal["user_mood"], "sad")
        self.assertEqual(signal["mood"], "neutral")
        self.assertEqual(signal["modifier"], "worried")
        self.assertEqual(signal["voice_style"], "concerned")

    def test_user_feeling_bad_becomes_visible_concern(self):
        signal = plan_turn_emotion("我今天真的很难受，但暂时不想说原因。")

        self.assertEqual(signal["user_mood"], "sad")
        self.assertEqual(signal["mood"], "neutral")
        self.assertEqual(signal["modifier"], "worried")
        self.assertGreaterEqual(signal["modifier_strength"], 0.7)
        self.assertEqual(signal["voice_style"], "concerned")

    def test_negated_feeling_bad_does_not_trigger_concern(self):
        signal = plan_turn_emotion("我现在已经不难受了，状态还可以。")

        self.assertEqual(signal["user_mood"], "neutral")
        self.assertEqual(signal["modifier"], "none")
        self.assertEqual(signal["voice_style"], "conversational")

    def test_loneliness_takes_priority_over_boredom_and_questions(self):
        signal = plan_turn_emotion(
            "感觉暑假好无聊，也挺孤独的，没人找我聊天，有什么办法吗"
        )

        self.assertEqual(signal["user_mood"], "lonely")
        self.assertEqual(signal["modifier"], "worried")
        self.assertEqual(signal["voice_style"], "concerned")

    def test_busy_internship_uses_reassuring_voice_without_happy_mood(self):
        signal = plan_turn_emotion("确实挺忙的，我最近在实习")

        self.assertEqual(signal["user_mood"], "stressed")
        self.assertEqual(signal["mood"], "neutral")
        self.assertEqual(signal["voice_style"], "reassuring")

    def test_bored_advice_request_uses_thoughtful_voice(self):
        signal = plan_turn_emotion("做什么事情都感到无聊，你有什么好的办法吗")

        self.assertEqual(signal["user_mood"], "bored")
        self.assertEqual(signal["modifier"], "none")
        self.assertEqual(signal["voice_style"], "thoughtful")

    def test_ordinary_question_is_conversational_not_curious(self):
        signal = plan_turn_emotion("桦喵的吉他弹得怎么样？")

        self.assertEqual(signal["modifier"], "none")
        self.assertEqual(signal["voice_style"], "conversational")
        self.assertTrue(has_interaction_signal(signal))

    def test_negated_loneliness_does_not_trigger_concern(self):
        signal = plan_turn_emotion("我现在已经不孤独了，最近过得还可以")

        self.assertEqual(signal["user_mood"], "neutral")
        self.assertEqual(signal["voice_style"], "conversational")

    def test_personal_compliment_and_shy_reply_selects_shy(self):
        signal = infer_interaction_emotion(
            "感觉你好可爱哈哈哈",
            "突、突然说什么啊……这种话太让人不好意思了。",
        )
        self.assertEqual(signal["mood"], "shy")
        self.assertGreaterEqual(signal["intensity"], 0.7)
        self.assertEqual(signal["voice_style"], "bashful")

    def test_ability_compliment_selects_happy_when_reply_accepts_it(self):
        signal = infer_interaction_emotion(
            "你今天贝斯弹得真好",
            "谢谢你这么说，我会继续努力的！",
        )
        self.assertEqual(signal["mood"], "happy")

    def test_ability_compliment_can_be_shy_when_reply_is_shy(self):
        signal = infer_interaction_emotion(
            "你今天贝斯弹得真好",
            "你、你突然这么夸，我会不好意思的……不过谢谢你。",
        )
        self.assertEqual(signal["mood"], "shy")

    def test_personal_compliment_can_be_happy_when_mio_accepts_it(self):
        signal = infer_interaction_emotion(
            "我觉得你很可爱",
            "谢谢你这么说，我很开心。",
        )
        self.assertEqual(signal["mood"], "happy")

    def test_reply_style_alone_does_not_self_renew_shyness(self):
        signal = infer_interaction_emotion(
            "今天天气还不错",
            "我、我也这么觉得……",
        )
        self.assertEqual(signal["mood"], "neutral")
        self.assertEqual(signal["modifier"], "none")

    def test_close_relationship_can_accept_direct_affection_happily(self):
        signal = plan_turn_emotion(
            "我喜欢你",
            emotion_state("happy", 0.7),
            {"affection": 80, "familiarity": 70, "trust": 70},
        )
        self.assertEqual(signal["mood"], "happy")
        self.assertEqual(signal["modifier"], "touched")

    def test_ai_control_can_calibrate_ambiguous_praise_to_happy(self):
        planned = plan_turn_emotion(
            "你好可爱",
            emotion_state(),
            {"affection": 30, "familiarity": 10},
        )
        calibrated = apply_ai_emotion_control(planned, {
            "user_mood": "neutral",
            "reaction": "happy",
            "voice_style": "warm",
            "strength": 0.72,
            "confidence": 0.88,
        })

        self.assertEqual(calibrated["mood"], "happy")
        self.assertEqual(calibrated["voice_style"], "warm")
        self.assertEqual(calibrated["decision_source"], "hybrid_ai")

    def test_ai_control_cannot_turn_strong_user_distress_cheerful(self):
        planned = plan_turn_emotion("我今天真的很难过")
        calibrated = apply_ai_emotion_control(planned, {
            "user_mood": "sad",
            "reaction": "happy",
            "voice_style": "cheerful",
            "strength": 0.9,
            "confidence": 0.95,
        })

        self.assertEqual(calibrated["user_mood"], "sad")
        self.assertEqual(calibrated["mood"], "neutral")
        self.assertEqual(calibrated["modifier"], "worried")
        self.assertEqual(calibrated["voice_style"], "concerned")

    def test_low_confidence_ai_control_is_ignored(self):
        planned = plan_turn_emotion("今天天气怎么样？")
        calibrated = apply_ai_emotion_control(planned, {
            "user_mood": "happy",
            "reaction": "happy",
            "voice_style": "excited",
            "strength": 0.9,
            "confidence": 0.4,
        })

        self.assertEqual(calibrated, planned)


class EmotionTransitionTests(unittest.TestCase):
    def test_happy_and_shy_can_transition_directly(self):
        state = emotion_state("happy", 0.7)
        updated = update_emotion(
            state,
            interaction={"mood": "shy", "intensity": 0.76},
        )
        self.assertEqual(updated["mood"], "shy")
        self.assertIsNone(updated["pending_mood"])

    def test_mild_cross_valence_change_requires_confirmation(self):
        state = emotion_state("happy", 0.7)
        first = update_emotion(
            state,
            interaction={"mood": "sad", "intensity": 0.55},
        )
        self.assertEqual(first["mood"], "happy")
        self.assertEqual(first["pending_mood"], "sad")

        second = update_emotion(
            first,
            interaction={"mood": "sad", "intensity": 0.55},
        )
        self.assertEqual(second["mood"], "sad")
        self.assertIsNone(second["pending_mood"])

    def test_shy_event_is_supported(self):
        updated = update_emotion(
            emotion_state(),
            event={"emotion": "shy", "importance": 0.7},
        )
        self.assertEqual(updated["mood"], "shy")

    def test_pending_mood_is_cleared_by_an_unrelated_turn(self):
        first = update_emotion(
            emotion_state("happy", 0.7),
            interaction={"mood": "sad", "intensity": 0.55},
        )
        self.assertEqual(first["pending_mood"], "sad")

        unrelated = update_emotion(first)
        self.assertIsNone(unrelated["pending_mood"])

    def test_mood_fades_by_turn_count_without_new_trigger(self):
        state = emotion_state("happy", 0.7)
        state["mood_turns_remaining"] = 1

        update_emotion(state)
        self.assertEqual(state["mood"], "happy")
        update_emotion(state)
        self.assertEqual(state["mood"], "happy")
        update_emotion(state)
        self.assertEqual(state["mood"], "neutral")

    def test_fatigue_uses_separate_enter_and_exit_thresholds(self):
        state = emotion_state()
        state["energy"] = 26
        update_emotion(state)
        self.assertEqual(state["mood"], "tired")

        state["energy"] = 36
        state["last_updated"] = None
        update_emotion(state)
        self.assertEqual(state["mood"], "neutral")

    def test_worried_event_uses_modifier_instead_of_sad_mood(self):
        updated = update_emotion(
            emotion_state(),
            event={"emotion": "worried", "importance": 0.7, "user_emotion": "sad"},
        )
        self.assertEqual(updated["mood"], "neutral")
        self.assertEqual(updated["modifier"], "worried")
        self.assertEqual(updated["voice_style"], "concerned")
        self.assertEqual(updated["user_mood"], "sad")

    def test_user_sadness_clears_old_happiness_before_comforting(self):
        signal = plan_turn_emotion("我今天真的很难过")
        updated = update_emotion(
            emotion_state("happy", 0.8),
            interaction=signal,
        )
        self.assertEqual(updated["mood"], "neutral")
        self.assertEqual(updated["modifier"], "worried")


class ProactiveEmotionTests(unittest.TestCase):
    def test_concerned_proactive_message_sets_expression_and_voice(self):
        signal = plan_proactive_emotion(
            "你今天还好吗？之前你很难过，我有点担心。",
            {"top_event": None, "idle_score": 0.3},
            emotion_state(),
            {"familiarity": 50},
        )

        self.assertEqual(signal["modifier"], "worried")
        self.assertEqual(signal["voice_style"], "concerned")
        self.assertEqual(signal["source"], "proactive")

    def test_happy_event_gives_proactive_message_cheerful_voice(self):
        signal = plan_proactive_emotion(
            "有个好消息想告诉你。",
            {
                "top_event": {
                    "emotion": "happy",
                    "user_emotion": "happy",
                }
            },
            emotion_state(),
        )

        self.assertEqual(signal["mood"], "happy")
        self.assertEqual(signal["voice_style"], "cheerful")

    def test_idle_contact_uses_warm_voice_without_forcing_a_mood(self):
        signal = plan_proactive_emotion(
            "好久没聊了，有空吗？",
            {"top_event": None, "idle_score": 0.5},
            emotion_state(),
            {"familiarity": 60},
        )

        self.assertEqual(signal["mood"], "neutral")
        self.assertEqual(signal["voice_style"], "warm")


class GreetingEmotionTests(unittest.TestCase):
    def test_familiar_neutral_greeting_uses_warm_voice(self):
        signal = plan_greeting_emotion(
            "啊，你来了。今天过得怎么样？",
            emotion_state(),
            {"affection": 50, "familiarity": 40},
        )

        self.assertEqual(signal["mood"], "neutral")
        self.assertEqual(signal["voice_style"], "warm")
        self.assertEqual(signal["source"], "greeting")

    def test_existing_happy_mood_gives_greeting_cheerful_voice(self):
        signal = plan_greeting_emotion(
            "你来了。",
            emotion_state("happy", 0.7),
            {"affection": 50, "familiarity": 40},
        )

        self.assertEqual(signal["voice_style"], "cheerful")

    def test_concerned_greeting_sets_worried_expression(self):
        signal = plan_greeting_emotion(
            "你还好吗？别太勉强自己。",
            emotion_state(),
            {"affection": 50, "familiarity": 40},
        )

        self.assertEqual(signal["modifier"], "worried")
        self.assertEqual(signal["voice_style"], "concerned")

    def test_startup_greeting_does_not_consume_energy(self):
        state = emotion_state()
        signal = plan_greeting_emotion("你来了。", state, {"familiarity": 40})

        update_emotion(state, interaction=signal, consume_energy=False)

        self.assertEqual(state["energy"], 80)


if __name__ == "__main__":
    unittest.main()
