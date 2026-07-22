import unittest

from anime_assistant.emotion import calibration, manager, planning, state
from anime_assistant.speech import backends, service, style, translator


class Day31ArchitectureTests(unittest.TestCase):
    def test_emotion_manager_keeps_compatibility_facade(self):
        self.assertIs(manager.plan_turn_emotion, planning.plan_turn_emotion)
        self.assertIs(
            manager.apply_ai_emotion_control,
            calibration.apply_ai_emotion_control,
        )
        self.assertIs(manager.update_emotion, state.update_emotion)

    def test_speech_service_reexports_backend_adapters(self):
        self.assertIs(service.AivisSpeechClient, backends.AivisSpeechClient)
        self.assertIs(service.MioStyleBertClient, backends.MioStyleBertClient)
        self.assertIs(service.MioGPTSoVITSClient, backends.MioGPTSoVITSClient)
        self.assertIs(
            service.JapaneseSpeechTranslator,
            translator.JapaneseSpeechTranslator,
        )

    def test_speech_style_policy_is_owned_by_style_module(self):
        self.assertIs(
            service.SpeechSynthesisService._effective_voice_style,
            style.effective_voice_style,
        )
        self.assertIs(
            service.SpeechSynthesisService._emotion_speed_multiplier,
            style.emotion_speed_multiplier,
        )


if __name__ == "__main__":
    unittest.main()
