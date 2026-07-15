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

    def test_mood_strength_scales_expression_without_changing_preset(self):
        controller = self.make_controller(
            parameter_map={"happy": {"ParamCheek": 1.0}},
        )

        controller.on_emotion_changed({"mood": "happy", "mood_strength": 0.5})

        self.assertAlmostEqual(controller._emotion_targets["ParamCheek"], 0.5)

    def test_same_mood_reacts_to_strength_changes(self):
        controller = self.make_controller(
            parameter_map={"happy": {"ParamCheek": 1.0}},
        )
        controller.on_emotion_changed({"mood": "happy", "mood_strength": 0.4})
        first = controller._emotion_targets["ParamCheek"]

        controller.on_emotion_changed({"mood": "happy", "mood_strength": 0.8})

        self.assertGreater(controller._emotion_targets["ParamCheek"], first)

    def test_transient_modifier_overlays_primary_expression(self):
        controller = self.make_controller(
            parameter_map={"neutral": {"ParamBrowLY": 0.0}},
        )

        controller.on_emotion_changed({
            "mood": "neutral",
            "modifier": "worried",
            "modifier_strength": 0.8,
        })

        self.assertLess(controller._emotion_targets["ParamBrowLY"], 0.0)

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

    def test_audio_amplitude_overrides_text_rhythm_until_playback_finishes(self):
        controller = self.make_controller()
        controller.on_reply_started()
        controller.on_reply_chunk("这段文字不应继续控制嘴型")
        controller.on_audio_started()
        controller.on_audio_amplitude(0.8)

        self.tick(controller, count=4)

        self.assertTrue(controller.is_speaking)
        self.assertGreater(self.widget.mouth_updates[-1], 0.5)

        controller.on_audio_finished()
        self.tick(controller, count=12)
        self.assertFalse(controller.is_speaking)
        self.assertLess(self.widget.mouth_updates[-1], 0.05)

    def test_speech_preparing_adds_smooth_idle_gaze_head_and_brow_motion(self):
        controller = self.make_controller()
        controller.on_speech_preparing()

        self.tick(controller, count=90)

        angle_x = [update["ParamAngleX"] for update in self.widget.parameter_updates]
        angle_z = [update["ParamAngleZ"] for update in self.widget.parameter_updates]
        brow_y = [update["ParamBrowLY"] for update in self.widget.parameter_updates]
        gaze_x = [update["ParamEyeBallX"] for update in self.widget.parameter_updates]
        consecutive_head_steps = [
            abs(current - previous)
            for previous, current in zip(angle_x, angle_x[1:])
        ]

        self.assertTrue(controller.is_preparing_speech)
        self.assertFalse(controller.is_speaking)
        self.assertGreater(max(angle_x) - min(angle_x), 1.4)
        self.assertGreater(max(angle_z) - min(angle_z), 0.28)
        self.assertGreater(max(brow_y) - min(brow_y), 0.005)
        self.assertGreater(max(gaze_x) - min(gaze_x), 0.05)
        self.assertLess(max(consecutive_head_steps), 0.7)
        self.assertLess(max(self.widget.mouth_updates), 0.01)

    def test_audio_start_replaces_speech_preparing_state(self):
        controller = self.make_controller()
        controller.on_speech_preparing()

        controller.on_audio_started()

        self.assertFalse(controller.is_preparing_speech)
        self.assertTrue(controller.is_speaking)

    def test_waiting_motion_intensity_scales_and_clamps_motion(self):
        controller = self.make_controller()
        controller.is_preparing_speech = True
        controller._preparing_blend = 1.0
        controller._created_at = 0.0
        now = self.clock.value

        controller.set_waiting_motion_intensity(0.0)
        no_waiting_motion = controller._build_desired_parameters(now, 0.033)[
            "ParamAngleX"
        ]
        controller.set_waiting_motion_intensity(2.0)
        strong_waiting_motion = controller._build_desired_parameters(now, 0.033)[
            "ParamAngleX"
        ]

        self.assertGreater(abs(strong_waiting_motion - no_waiting_motion), 1.0)
        self.assertEqual(controller.set_waiting_motion_intensity(99), 2.0)
        self.assertEqual(controller.set_waiting_motion_intensity(-5), 0.0)

    def test_waiting_motion_preview_does_not_fake_tts_state(self):
        controller = self.make_controller()

        controller.set_waiting_motion_preview(True)
        self.tick(controller, count=10)

        self.assertFalse(controller.is_preparing_speech)
        self.assertGreater(controller._preparing_blend, 0.0)

        controller.set_waiting_motion_preview(False)
        self.tick(controller, count=20)
        self.assertLess(controller._preparing_blend, 0.2)

    def test_waiting_gaze_intensity_scales_and_clamps_targets(self):
        class MaximumRng:
            @staticmethod
            def uniform(_lower, upper):
                return upper

        controller = self.make_controller()
        controller._rng = MaximumRng()
        controller.set_waiting_motion_preview(True)

        controller.set_waiting_gaze_intensity(0.5)
        controller._update_gaze(self.clock.value, 0.033)
        low_target = controller._gaze_target_x

        controller.set_waiting_gaze_intensity(2.0)
        controller._update_gaze(self.clock.value, 0.033)
        high_target = controller._gaze_target_x

        self.assertAlmostEqual(low_target, 0.21)
        self.assertAlmostEqual(high_target, 0.84)
        self.assertEqual(controller.set_waiting_gaze_intensity(99), 2.0)
        self.assertEqual(controller.set_waiting_gaze_intensity(-5), 0.0)
        self.assertEqual(controller._gaze_target_x, 0.0)

    def test_waiting_motion_speed_changes_phase_rate_without_phase_jump(self):
        controller = self.make_controller()
        controller.set_waiting_motion_preview(True)
        self.tick(controller, seconds=0.04)
        controller._waiting_motion_phase = 3.0

        applied = controller.set_waiting_motion_speed(2.0)
        phase_before_tick = controller._waiting_motion_phase
        self.tick(controller, seconds=0.04)

        self.assertEqual(applied, 2.0)
        self.assertEqual(phase_before_tick, 3.0)
        self.assertAlmostEqual(controller._waiting_motion_phase, 3.08)
        self.assertEqual(controller.set_waiting_motion_speed(99), 2.0)
        self.assertEqual(controller.set_waiting_motion_speed(0), 0.5)

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
