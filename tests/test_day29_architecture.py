from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from anime_assistant.emotion.signals import EmotionSignal, base_turn_signal
from anime_assistant.infrastructure import logging as app_logging
from anime_assistant.speech.jobs import SpeechJob
from anime_assistant.speech.service import (
    MioStyleBertClient,
    MioStyleBertError,
    SpeechSynthesisService,
)


class Day29ArchitectureTests(unittest.TestCase):
    def test_configuration_import_does_not_load_runtime_backends(self):
        project_root = Path(__file__).resolve().parents[1]
        script = (
            "import sys; "
            "import anime_assistant.infrastructure.config; "
            "assert 'anime_assistant.speech.service' not in sys.modules; "
            "assert 'openai' not in sys.modules"
        )

        result = subprocess.run(
            [sys.executable, "-S", "-c", script],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_loggers_share_one_rotating_file_handler(self):
        first = app_logging.get_logger("tests.day29.first")
        second = app_logging.get_logger("tests.day29.second")

        first_handler = next(
            handler
            for handler in first.handlers
            if isinstance(handler, RotatingFileHandler)
        )
        second_handler = next(
            handler
            for handler in second.handlers
            if isinstance(handler, RotatingFileHandler)
        )

        self.assertIs(first_handler, second_handler)
        self.assertEqual(first_handler.maxBytes, app_logging.LOG_MAX_BYTES)
        self.assertEqual(first_handler.backupCount, app_logging.LOG_BACKUP_COUNT)
        self.assertGreater(first_handler.maxBytes, 0)
        self.assertGreater(first_handler.backupCount, 0)

    def test_speech_job_normalizes_legacy_queue_payloads(self):
        minimal = SpeechJob.from_legacy(("こんにちは", "happy"))
        complete = SpeechJob.from_legacy(
            ("大丈夫？", "neutral", 0.8, "worried", 0.1, "concerned", 0.9)
        )

        self.assertEqual(minimal.mood, "happy")
        self.assertEqual(minimal.voice_style_strength, 0.6)
        self.assertEqual(complete.modifier, "worried")
        self.assertEqual(complete.voice_style, "concerned")
        self.assertEqual(complete.voice_style_strength, 0.9)

    def test_speak_enqueues_typed_immutable_job(self):
        service = SpeechSynthesisService.__new__(SpeechSynthesisService)
        service._stop_event = threading.Event()
        service._jobs = queue.Queue()

        accepted = service.speak(
            "今日はどうだった？",
            mood="neutral",
            modifier="curious",
            voice_style="curious",
        )
        queued = service._jobs.get_nowait()

        self.assertTrue(accepted)
        self.assertIsInstance(queued, SpeechJob)
        self.assertEqual(queued.modifier, "curious")
        self.assertEqual(queued.voice_style, "curious")

    def test_emotion_signal_runtime_shape_matches_typed_contract(self):
        signal: EmotionSignal = base_turn_signal("day29_contract")
        required_keys = set(EmotionSignal.__required_keys__)

        self.assertEqual(required_keys, set(signal))
        self.assertEqual(signal["reason"], "day29_contract")
        self.assertEqual(signal["decision_source"], "local_rules")

    def test_shutdown_interrupts_active_model_warmup_without_followup(self):
        trace = []

        class LoadingClient:
            supports_prewarm = True
            last_error = "cancelled"

            def __init__(self):
                self.started = threading.Event()
                self.cancelled = threading.Event()

            def is_available(self):
                self.started.set()
                self.cancelled.wait(timeout=5)
                return False

            def cancel(self):
                trace.append("cancel")
                self.cancelled.set()

        client = LoadingClient()
        service = SpeechSynthesisService.__new__(SpeechSynthesisService)
        service.client = client
        service.fallback_client = None
        service._stop_event = threading.Event()
        service._jobs = queue.Queue()
        service.on_audio_ready = lambda _audio: None
        service.on_error = lambda _message: None
        service.on_status = lambda _status: None
        service._thread = threading.Thread(target=service._run, daemon=True)
        service._thread.start()
        self.assertTrue(service.prewarm(lambda: trace.append("followup")))
        self.assertTrue(client.started.wait(timeout=1))

        started_at = time.perf_counter()
        service.shutdown()
        elapsed = time.perf_counter() - started_at

        self.assertLess(elapsed, 0.5)
        self.assertFalse(service._thread.is_alive())
        self.assertEqual(trace, ["cancel"])

    def test_local_client_startup_wait_does_not_hold_process_lock(self):
        class LoadingProcess:
            def __init__(self):
                self.stdin = None
                self.stdout = object()
                self.terminated = threading.Event()

            def poll(self):
                return 0 if self.terminated.is_set() else None

            def terminate(self):
                self.terminated.set()

            def kill(self):
                self.terminated.set()

            def wait(self, timeout=None):
                if not self.terminated.wait(timeout=timeout):
                    raise subprocess.TimeoutExpired("fake-worker", timeout)
                return 0

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            repo.mkdir()
            paths = {
                "python": root / "python.exe",
                "worker": root / "worker.py",
                "model": root / "model.safetensors",
                "config": root / "config.json",
                "styles": root / "styles.npy",
            }
            for path in paths.values():
                path.touch()
            client = MioStyleBertClient({
                "mio_tts_python": str(paths["python"]),
                "mio_tts_worker": str(paths["worker"]),
                "mio_tts_repo": str(repo),
                "mio_tts_model": str(paths["model"]),
                "mio_tts_config": str(paths["config"]),
                "mio_tts_style_vectors": str(paths["styles"]),
                "mio_tts_output_dir": str(root / "output"),
                "mio_tts_startup_timeout_seconds": 5,
            })
            process = LoadingProcess()

            def reader(_client, _process, event_queue):
                _process.terminated.wait(timeout=2)
                event_queue.put({"type": "eof", "message": "cancelled"})

            startup_errors = []

            def start_client():
                try:
                    client._ensure_process()
                except MioStyleBertError as exc:
                    startup_errors.append(str(exc))

            with patch(
                "anime_assistant.speech.backends.subprocess.Popen",
                return_value=process,
            ), patch.object(MioStyleBertClient, "_read_worker_output", reader):
                startup_thread = threading.Thread(target=start_client, daemon=True)
                startup_thread.start()
                deadline = time.monotonic() + 1
                while client._process is not process and time.monotonic() < deadline:
                    time.sleep(0.005)

                cancel_thread = threading.Thread(target=client.cancel, daemon=True)
                cancel_thread.start()
                cancel_thread.join(timeout=0.5)
                startup_thread.join(timeout=1)

        self.assertFalse(cancel_thread.is_alive())
        self.assertFalse(startup_thread.is_alive())
        self.assertTrue(process.terminated.is_set())
        self.assertTrue(startup_errors)


if __name__ == "__main__":
    unittest.main()
