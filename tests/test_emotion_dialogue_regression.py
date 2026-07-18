import json
import unittest
from pathlib import Path

from anime_assistant.ai.chat import parse_emotion_control_tag
from anime_assistant.emotion.manager import (
    apply_ai_emotion_control,
    infer_interaction_emotion,
    plan_turn_emotion,
)


CASES_PATH = Path(__file__).with_name("emotion_dialogue_regression_cases.json")


def _initial_emotion(overrides=None):
    state = {
        "mood": "neutral",
        "energy": 80,
        "last_updated": None,
        "mood_set_at": None,
        "mood_strength": 0.0,
        "pending_mood": None,
        "pending_mood_count": 0,
    }
    if isinstance(overrides, dict):
        state.update(overrides)
    return state


class EmotionDialogueRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CASES_PATH, "r", encoding="utf-8") as handle:
            fixture = json.load(handle)
        if fixture.get("schema_version") != 1:
            raise AssertionError("不支持的情绪回归样例版本")
        cls.cases = fixture.get("cases", [])

    def test_fixture_has_unique_named_cases(self):
        case_ids = [case.get("id") for case in self.cases]
        self.assertGreaterEqual(len(case_ids), 10)
        self.assertTrue(all(case_ids))
        self.assertEqual(len(case_ids), len(set(case_ids)))

    def test_fixed_dialogue_cases(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                emotion = _initial_emotion(case.get("initial_emotion"))
                relationship = case.get("relationship", {
                    "affection": 30,
                    "familiarity": 10,
                    "trust": 30,
                })
                planned = plan_turn_emotion(
                    case["user_message"],
                    emotion=emotion,
                    relationship=relationship,
                )
                reply_calibrated = infer_interaction_emotion(
                    case["user_message"],
                    case["assistant_reply"],
                    relationship=relationship,
                    planned=planned,
                )
                control = parse_emotion_control_tag(case["control_tag"])
                self.assertIsNotNone(control)
                final_signal = apply_ai_emotion_control(reply_calibrated, control)

                for field, expected in case["expected"].items():
                    self.assertEqual(
                        final_signal.get(field),
                        expected,
                        msg=f"{case['id']} 的 {field} 发生回归",
                    )


if __name__ == "__main__":
    unittest.main()
