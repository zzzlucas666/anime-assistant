from io import BytesIO
import math
import queue
import struct
import threading
import unittest
import wave

from tts_service import (
    AivisSpeechError,
    SpeechSynthesisService,
    build_mouth_envelope,
    combine_speech_audio,
    contains_japanese_kana,
    prepare_spoken_text,
    split_sentences,
)


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


if __name__ == "__main__":
    unittest.main()
