from io import BytesIO
import math
import queue
import struct
import threading
import unittest
import wave

from anime_assistant.speech.service import (
    AivisSpeechError,
    MioStyleBertClient,
    MioStyleBertError,
    SpeechSynthesisService,
    build_mouth_envelope,
    combine_speech_audio,
    contains_japanese_kana,
    prepare_spoken_text,
    split_sentences,
)
from anime_assistant.speech.gpt_sovits_worker import force_all_japanese_segments


def make_test_wav(sample_rate=8000, duration=0.3):
    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = []
        for index in range(int(sample_rate * duration)):
            gain = 0.0 if index < sample_rate * 0.1 else 0.6
            value = int(32767 * gain * math.sin(2 * math.pi * 220 * index / sample_rate))
            frames.append(struct.pack("<h", value))
        wav_file.writeframes(b"".join(frames))
    return output.getvalue()


class TTSServiceTests(unittest.TestCase):
    def test_all_ja_forces_latin_names_through_japanese_frontend(self):
        class FakeLangSegmenter:
            @staticmethod
            def getTexts(_text, _default_lang=""):
                return [
                    {"lang": "ja", "text": "最近は"},
                    {"lang": "en", "text": "Radiohead"},
                ]

        force_all_japanese_segments(FakeLangSegmenter)

        segments = FakeLangSegmenter.getTexts("最近はRadiohead", "ja")

        self.assertEqual([item["lang"] for item in segments], ["ja", "ja"])

    def test_local_model_prewarm_finishes_before_followup_callback(self):
        trace = []

        class FakeLocalClient:
            supports_prewarm = True
            last_error = ""

            def is_available(self):
                trace.append("model-ready")
                return True

        service = SpeechSynthesisService.__new__(SpeechSynthesisService)
        service.client = FakeLocalClient()
        service._stop_event = threading.Event()
        service._jobs = queue.Queue()
        service.on_status = lambda status: trace.append(f"status:{status}")

        self.assertTrue(service.prewarm(lambda: trace.append("semantic-warmup")))
        service._jobs.put(None)
        service._run()

        self.assertEqual(
            trace,
            [
                "status:loading",
                "model-ready",
                "status:ready",
                "semantic-warmup",
            ],
        )

    def test_failed_local_prewarm_still_releases_followup_callback(self):
        trace = []

        class UnavailableLocalClient:
            supports_prewarm = True
            last_error = "startup failed"

            def is_available(self):
                return False

        service = SpeechSynthesisService.__new__(SpeechSynthesisService)
        service.client = UnavailableLocalClient()
        service._stop_event = threading.Event()
        service._jobs = queue.Queue()
        service.on_status = lambda status: trace.append(status)

        self.assertTrue(service.prewarm(lambda: trace.append("semantic-warmup")))
        service._jobs.put(None)
        service._run()

        self.assertEqual(trace, ["loading", "error", "semantic-warmup"])

    def test_local_worker_timeout_identifies_startup_phase(self):
        client = MioStyleBertClient.__new__(MioStyleBertClient)
        client._events = queue.Queue()

        with self.assertRaisesRegex(MioStyleBertError, "startup timed out"):
            client._wait_for_event(None, 0.01, phase="startup")

    def test_stage_direction_is_not_spoken(self):
        self.assertEqual(
            prepare_spoken_text("（轻轻点头）嗯，今天也一起练习吧。"),
            "嗯，今天也一起练习吧。",
        )

    def test_japanese_text_detection_uses_kana(self):
        self.assertTrue(contains_japanese_kana("今日は一緒に練習しよう。"))
        self.assertFalse(contains_japanese_kana("今天一起练习吧。"))

    def test_sentences_are_split_for_incremental_synthesis(self):
        self.assertEqual(
            split_sentences("うん、分かった。今日も頑張ろう！"),
            ["うん、分かった。", "今日も頑張ろう！"],
        )

    def test_long_sentence_is_bounded_for_aivis_requests(self):
        sentences = split_sentences("あ" * 130, maximum_chars=56)
        self.assertEqual("".join(sentences), "あ" * 130)
        self.assertTrue(all(len(sentence) <= 56 for sentence in sentences))

    def test_mouth_envelope_follows_actual_audio_energy(self):
        envelope = build_mouth_envelope(make_test_wav(), window_ms=25)
        self.assertGreater(len(envelope), 5)
        self.assertLess(max(envelope[:3]), 0.05)
        self.assertGreater(max(envelope[-5:]), 0.5)

    def test_audio_segments_are_combined_into_one_wav_and_envelope(self):
        first = make_test_wav(duration=0.2)
        second = make_test_wav(duration=0.3)
        combined = combine_speech_audio([
            type("Audio", (), {
                "wav_data": first,
                "spoken_text": "第一句。",
            })(),
            type("Audio", (), {
                "wav_data": second,
                "spoken_text": "第二句。",
            })(),
        ], pause_ms=100)

        with wave.open(BytesIO(combined.wav_data), "rb") as wav_file:
            duration = wav_file.getnframes() / wav_file.getframerate()

        self.assertAlmostEqual(duration, 0.6, places=2)
        self.assertEqual(combined.spoken_text, "第一句。第二句。")
        self.assertGreater(len(combined.mouth_envelope), 10)

    def test_failed_sentence_cancels_entire_audio_batch(self):
        class FakeClient:
            def __init__(self):
                self.endpoint = "fake"
                self.calls = 0

            def is_available(self):
                return True

            def synthesize(self, *_args):
                self.calls += 1
                raise AivisSpeechError("timed out")

        ready = []
        errors = []
        service = SpeechSynthesisService.__new__(SpeechSynthesisService)
        service.config = {
            "aivis_mood_speakers": {"neutral": 1},
            "aivis_max_chars_per_request": 56,
        }
        service.client = FakeClient()
        service.translator = None
        service.on_audio_ready = ready.append
        service.on_error = errors.append
        service._stop_event = threading.Event()
        service._jobs = queue.Queue()
        service._jobs.put(("第一句。第二句。", "neutral"))
        service._jobs.put(None)

        service._run()

        self.assertEqual(service.client.calls, 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(ready, [])

    def test_complete_audio_batch_is_emitted_only_after_all_synthesis(self):
        class FakeClient:
            endpoint = "fake"

            def __init__(self):
                self.calls = []

            def is_available(self):
                return True

            def synthesize(self, text, *_args):
                self.calls.append(text)
                return make_test_wav(duration=0.1)

        events = []
        service = SpeechSynthesisService.__new__(SpeechSynthesisService)
        service.config = {
            "aivis_mood_speakers": {"neutral": 1},
            "aivis_max_chars_per_request": 56,
        }
        service.client = FakeClient()
        service.translator = None
        service.on_audio_ready = lambda audio: events.append(
            ("ready", audio.spoken_text, len(service.client.calls))
        )
        service.on_error = lambda message: events.append(("error", message))
        service._stop_event = threading.Event()
        service._jobs = queue.Queue()
        service._jobs.put(("第一句。第二句。", "neutral"))
        service._jobs.put(None)

        service._run()

        self.assertEqual(service.client.calls, ["第一句。", "第二句。"])
        self.assertEqual(
            events,
            [("ready", "第一句。第二句。", 2)],
        )

    def test_mood_reference_is_forwarded_only_to_capable_backend(self):
        class MoodClient:
            supports_mood_reference = True

            def __init__(self):
                self.moods = []

            def synthesize(self, _text, *_args, mood="neutral"):
                self.moods.append(mood)
                return make_test_wav(duration=0.1)

        service = SpeechSynthesisService.__new__(SpeechSynthesisService)
        service.config = {"tts_speed_scale": 1.0, "tts_volume_scale": 1.0}
        service._stop_event = threading.Event()
        client = MoodClient()

        service._synthesize_sentences(client, ["恥ずかしい。"], 0, "shy")

        self.assertEqual(client.moods, ["shy"])

    def test_voice_style_is_forwarded_independently_from_mood(self):
        class VoiceStyleClient:
            supports_mood_reference = True
            supports_voice_style = True

            def __init__(self):
                self.calls = []

            def synthesize(
                self,
                _text,
                *_args,
                mood="neutral",
                voice_style="conversational",
            ):
                self.calls.append((mood, voice_style))
                return make_test_wav(duration=0.1)

        service = SpeechSynthesisService.__new__(SpeechSynthesisService)
        service.config = {"tts_speed_scale": 1.0, "tts_volume_scale": 1.0}
        service._stop_event = threading.Event()
        client = VoiceStyleClient()

        service._synthesize_sentences(
            client,
            ["大丈夫。"],
            0,
            "happy",
            voice_style="concerned",
        )

        self.assertEqual(client.calls, [("happy", "concerned")])

    def test_subtle_mood_uses_neutral_reference_and_fatigue_can_override(self):
        self.assertEqual(
            SpeechSynthesisService._effective_mood("happy", 0.2, "none", 0.0),
            "neutral",
        )
        self.assertEqual(
            SpeechSynthesisService._effective_mood("happy", 0.8, "none", 0.8),
            "tired",
        )
        self.assertGreater(
            SpeechSynthesisService._emotion_speed_multiplier("happy", 0.8, "none", 0.0),
            1.0,
        )
        self.assertLess(
            SpeechSynthesisService._emotion_speed_multiplier("neutral", 0.0, "worried", 0.5),
            1.0,
        )

    def test_explicit_voice_style_replaces_base_mood_for_gpt_sovits(self):
        self.assertEqual(
            SpeechSynthesisService._effective_voice_style(
                "happy", 0.8, "none", 0.0, "concerned"
            ),
            "concerned",
        )
        self.assertEqual(
            SpeechSynthesisService._effective_voice_style(
                "happy", 0.8, "none", 0.8, "cheerful"
            ),
            "tired",
        )
        self.assertLess(
            SpeechSynthesisService._emotion_speed_multiplier(
                "happy", 0.8, "none", 0.0, "concerned", 0.8
            ),
            1.0,
        )

    def test_unavailable_primary_backend_falls_back_for_the_complete_reply(self):
        class UnavailablePrimary:
            endpoint = "local Mio model"
            backend_name = "mio_style_bert_vits2"
            last_error = "model unavailable"

            def is_available(self):
                return False

        class FakeAivis:
            endpoint = "fake Aivis"

            def __init__(self):
                self.calls = []

            def is_available(self):
                return True

            def synthesize(self, text, *_args):
                self.calls.append(text)
                return make_test_wav(duration=0.1)

        fallback = FakeAivis()
        ready = []
        errors = []
        service = SpeechSynthesisService.__new__(SpeechSynthesisService)
        service.config = {"aivis_max_chars_per_request": 56}
        service.client = UnavailablePrimary()
        service.fallback_client = fallback
        service.translator = None
        service.on_audio_ready = ready.append
        service.on_error = errors.append
        service._stop_event = threading.Event()
        service._jobs = queue.Queue()
        service._jobs.put(("第一句。第二句。", "neutral"))
        service._jobs.put(None)

        service._run()

        self.assertEqual(fallback.calls, ["第一句。", "第二句。"])
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].spoken_text, "第一句。第二句。")
        self.assertEqual(errors, [])

    def test_local_backend_restarts_once_after_transient_synthesis_failure(self):
        class FlakyLocalClient:
            endpoint = "local GPT-SoVITS"
            backend_name = "mio_gpt_sovits_v2proplus"
            supports_voice_style = True
            last_error = ""

            def __init__(self):
                self.calls = 0
                self.closes = 0

            def is_available(self):
                return True

            def synthesize(self, *_args, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("worker pipe lost")
                return make_test_wav(duration=0.1)

            def close(self):
                self.closes += 1

        client = FlakyLocalClient()
        ready = []
        errors = []
        service = SpeechSynthesisService.__new__(SpeechSynthesisService)
        service.config = {"aivis_max_chars_per_request": 56}
        service.client = client
        service.fallback_client = None
        service.translator = None
        service.local_retry_attempts = 1
        service.on_audio_ready = ready.append
        service.on_error = errors.append
        service._stop_event = threading.Event()
        service._jobs = queue.Queue()
        service._jobs.put(("一度だけ再試行する。", "neutral"))
        service._jobs.put(None)

        service._run()

        self.assertEqual(client.calls, 2)
        self.assertEqual(client.closes, 1)
        self.assertEqual(len(ready), 1)
        self.assertEqual(errors, [])

    def test_final_error_keeps_primary_and_fallback_causes(self):
        class BrokenPrimary:
            endpoint = "local GPT-SoVITS"
            backend_name = "mio_gpt_sovits_v2proplus"
            supports_voice_style = True
            last_error = ""

            def is_available(self):
                return True

            def synthesize(self, *_args, **_kwargs):
                raise RuntimeError("primary text frontend failed")

        class UnavailableFallback:
            endpoint = "http://127.0.0.1:10101"
            backend_name = "aivis"
            last_error = "fallback server is not running"

            def is_available(self):
                return False

        errors = []
        service = SpeechSynthesisService.__new__(SpeechSynthesisService)
        service.config = {"aivis_max_chars_per_request": 56}
        service.client = BrokenPrimary()
        service.fallback_client = UnavailableFallback()
        service.translator = None
        service.local_retry_attempts = 0
        service.on_audio_ready = lambda _audio: None
        service.on_error = errors.append
        service._stop_event = threading.Event()
        service._jobs = queue.Queue()
        service._jobs.put(("原因を残す。", "neutral"))
        service._jobs.put(None)

        service._run()

        self.assertEqual(len(errors), 1)
        self.assertIn("primary text frontend failed", errors[0])
        self.assertIn("fallback server is not running", errors[0])


if __name__ == "__main__":
    unittest.main()
