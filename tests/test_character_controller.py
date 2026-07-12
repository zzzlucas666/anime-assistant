import random
import unittest
from unittest.mock import patch

from character_controller import CharacterController


class FakeClock:
    def __init__(self, value=100.0):
        self.value = value

    def monotonic(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeLive2DWidget:
    def __init__(self):
        self.parameter_updates = []
        self.mouth_updates = []
        self.expressions = []
        self.motions = []

    def set_parameters(self, parameters):
        self.parameter_updates.append(dict(parameters))

    def set_mouth_open(self, value):
        self.mouth_updates.append(float(value))

    def set_expression(self, name):
        self.expressions.append(name)

    def start_motion(self, group):
        self.motions.append(group)


class CharacterControllerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.clock_patch = patch(
            "character_controller.time.monotonic", self.clock.monotonic
        )
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.widget = FakeLive2DWidget()

    def make_controller(self, **kwargs):
        return CharacterController(
            live2d_widget=self.widget,
            rng=random.Random(7),
            **kwargs,
        )

    def tick(self, controller, seconds=0.04, count=1):
        for _ in range(count):
            self.clock.advance(seconds)
            controller.tick()

    def test_emotion_parameters_transition_and_return_to_neutral(self):
        controller = self.make_controller(
            parameter_map={
                "happy": {"ParamCheek": 1.0, "ParamMouthForm": 0.8},
                "neutral": {"ParamCheek": 0.0, "ParamMouthForm": 0.0},
            }
        )

        controller.on_emotion_changed({"mood": "happy"})
        self.tick(controller, count=5)
        happy_cheek = self.widget.parameter_updates[-1]["ParamCheek"]
        self.assertGreater(happy_cheek, 0.5)

        controller.on_emotion_changed({"mood": "neutral"})
        self.tick(controller, count=8)
        neutral_cheek = self.widget.parameter_updates[-1]["ParamCheek"]
        self.assertLess(neutral_cheek, happy_cheek)
        self.assertLess(neutral_cheek, 0.1)

    def test_expression_intensity_moves_parameters_away_from_neutral(self):
        controller = self.make_controller(
            parameter_map={
                "sad": {
                    "ParamEyeLOpen": 0.65,
                    "ParamBrowLY": -0.65,
                    "ParamCheek": 0.4,
                }
            },
            expression_intensity=1.25,
        )

        controller.on_emotion_changed({"mood": "sad"})

        self.assertAlmostEqual(controller._emotion_targets["ParamEyeLOpen"], 0.5625)
        self.assertAlmostEqual(controller._emotion_targets["ParamBrowLY"], -0.8125)
        self.assertAlmostEqual(controller._emotion_targets["ParamCheek"], 0.5)

    def test_programmatic_blink_closes_both_eyes(self):
        controller = self.make_controller()
        controller._next_blink_at = self.clock.value

        self.tick(controller, seconds=0.04)
        before = self.widget.parameter_updates[-1]["ParamEyeLOpen"]
        self.tick(controller, seconds=0.05)
        during = self.widget.parameter_updates[-1]["ParamEyeLOpen"]

        self.assertLess(during, before)
        self.assertAlmostEqual(
            during,
            self.widget.parameter_updates[-1]["ParamEyeROpen"],
            places=6,
        )

    def test_parameters_are_written_on_consecutive_33ms_render_frames(self):
        controller = self.make_controller()

        self.tick(controller, seconds=0.033, count=2)

        self.assertEqual(len(self.widget.parameter_updates), 2)
        self.assertEqual(len(self.widget.mouth_updates), 2)

    def test_extra_startup_render_frames_are_never_left_uncontrolled(self):
        controller = self.make_controller()

        self.tick(controller, seconds=0.001, count=4)

        self.assertEqual(len(self.widget.parameter_updates), 4)
        self.assertEqual(len(self.widget.mouth_updates), 4)

    def test_manual_preview_overrides_and_then_releases_parameters(self):
        controller = self.make_controller(
            parameter_map={"neutral": {"ParamMouthForm": 0.0}},
            expression_intensity=1.25,
        )
        controller.on_emotion_changed({"mood": "neutral"})
        controller.preview_parameters("happy", {"ParamMouthForm": 0.4})
        self.tick(controller, count=20)
        previewed = self.widget.parameter_updates[-1]["ParamMouthForm"]

        controller.clear_parameter_preview()
        self.tick(controller, count=20)
        released = self.widget.parameter_updates[-1]["ParamMouthForm"]

        self.assertGreater(previewed, 0.45)
        self.assertLess(released, 0.05)

    def test_updating_active_preset_refreshes_emotion_target(self):
        controller = self.make_controller(
            parameter_map={"happy": {"ParamCheek": 0.2}}
        )
        controller.on_emotion_changed({"mood": "happy"})

        controller.update_parameter_preset("happy", {"ParamCheek": 0.6})

        self.assertAlmostEqual(controller._emotion_targets["ParamCheek"], 0.6)

    def test_question_mark_adds_temporary_head_tilt(self):
        controller = self.make_controller()
        controller.on_reply_started()
        controller.on_reply_chunk("真的吗？")
        self.tick(controller)

        self.assertGreater(
            self.widget.parameter_updates[-1]["ParamAngleZ"], 0.0
        )

    def test_text_rhythm_moves_mouth_and_finish_closes_it_smoothly(self):
        controller = self.make_controller()
        controller.on_reply_started()
        controller.on_reply_chunk("你好，今天很开心！")
        self.tick(controller, count=8)

        peak = max(self.widget.mouth_updates)
        self.assertGreater(peak, 0.15)
        self.assertGreater(len(set(round(v, 3) for v in self.widget.mouth_updates)), 2)

        controller.on_reply_finished()
        self.tick(controller, count=2)
        self.assertTrue(controller.is_speaking)

        self.tick(controller, count=120)
        self.assertFalse(controller.is_speaking)
        self.assertLess(self.widget.mouth_updates[-1], 0.01)

    def test_static_mouth_open_is_used_as_resting_shape(self):
        controller = self.make_controller(
            parameter_map={"shy": {"ParamMouthOpenY": 0.12}},
        )
        controller.on_emotion_changed({"mood": "shy"})

        self.tick(controller, count=12)

        self.assertGreater(self.widget.mouth_updates[-1], 0.1)

    def test_speech_mouth_is_combined_with_static_opening(self):
        controller = self.make_controller(
            parameter_map={"happy": {"ParamMouthOpenY": 0.1}},
        )
        controller.on_emotion_changed({"mood": "happy"})
        self.tick(controller, count=12)
        resting = self.widget.mouth_updates[-1]

        controller.on_reply_started()
        controller.on_reply_chunk("你好")
        self.tick(controller, count=5)

        self.assertGreater(max(self.widget.mouth_updates[-5:]), resting)

    def test_unknown_model_parameters_are_filtered(self):
        controller = self.make_controller(
            parameter_map={"happy": {"ParamCheek": 1.0, "NotInModel": 1.0}},
            available_parameters={"ParamCheek", "ParamMouthOpenY"},
        )
        controller.on_emotion_changed({"mood": "happy"})
        self.tick(controller)

        update = self.widget.parameter_updates[-1]
        self.assertIn("ParamCheek", update)
        self.assertNotIn("NotInModel", update)


if __name__ == "__main__":
    unittest.main()
