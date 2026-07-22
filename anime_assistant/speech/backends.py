"""Concrete HTTP and local-process speech backend adapters."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from anime_assistant.infrastructure.paths import resolve_project_path
from anime_assistant.infrastructure.logging import get_logger
from anime_assistant.speech.config import (
    DEFAULT_AIVIS_ENDPOINT,
    DEFAULT_AIVIS_TIMEOUT_SECONDS,
    DEFAULT_MIO_GPT_SOVITS_GPT_WEIGHTS,
    DEFAULT_MIO_GPT_SOVITS_PYTHON,
    DEFAULT_MIO_GPT_SOVITS_REFERENCES,
    DEFAULT_MIO_GPT_SOVITS_REPO,
    DEFAULT_MIO_GPT_SOVITS_SOVITS_WEIGHTS,
    DEFAULT_MIO_GPT_SOVITS_WORKER,
    DEFAULT_MIO_TTS_CONFIG,
    DEFAULT_MIO_TTS_MODEL,
    DEFAULT_MIO_TTS_PYTHON,
    DEFAULT_MIO_TTS_REPO,
    DEFAULT_MIO_TTS_STYLE_VECTORS,
    DEFAULT_MIO_TTS_WORKER,
    MIO_GPT_SOVITS_BACKEND,
    MIO_TTS_BACKEND,
)


logger = get_logger(__name__)

_MIO_EVENT_PREFIX = "MIO_TTS_EVENT\t"


class AivisSpeechError(RuntimeError):
    """AivisSpeech 无法完成请求。"""


class MioStyleBertError(RuntimeError):
    """本地 Mio Style-Bert-VITS2 进程无法完成请求。"""


class MioGPTSoVITSError(RuntimeError):
    """本地 Mio GPT-SoVITS V2ProPlus 进程无法完成请求。"""


class AivisSpeechClient:
    """VOICEVOX 兼容的 AivisSpeech 本地 HTTP API 客户端。"""

    def __init__(
        self,
        endpoint=DEFAULT_AIVIS_ENDPOINT,
        timeout_seconds=DEFAULT_AIVIS_TIMEOUT_SECONDS,
    ):
        self.endpoint = str(endpoint or DEFAULT_AIVIS_ENDPOINT).rstrip("/")
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    def is_available(self):
        try:
            request = urllib.request.Request(f"{self.endpoint}/version")
            with urllib.request.urlopen(request, timeout=min(self.timeout_seconds, 2.0)) as response:
                return 200 <= response.status < 300
        except (OSError, urllib.error.URLError, ValueError):
            return False

    def synthesize(self, text, speaker_id, speed_scale=1.0, volume_scale=1.0):
        query_params = urllib.parse.urlencode({"text": text, "speaker": int(speaker_id)})
        query = self._post_json(f"/audio_query?{query_params}")
        query["speedScale"] = max(0.5, min(2.0, float(speed_scale)))
        query["volumeScale"] = max(0.0, min(2.0, float(volume_scale)))

        synthesis_params = urllib.parse.urlencode({"speaker": int(speaker_id)})
        body = json.dumps(query, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.endpoint}/synthesis?{synthesis_params}",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "audio/wav"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read()
        except (OSError, urllib.error.URLError, ValueError) as exc:
            raise AivisSpeechError(f"AivisSpeech synthesis failed: {exc}") from exc

    def _post_json(self, path):
        request = urllib.request.Request(
            f"{self.endpoint}{path}",
            data=b"",
            headers={"Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
            raise AivisSpeechError(f"AivisSpeech audio query failed: {exc}") from exc


class MioStyleBertClient:
    """通过独立 Python 3.10 常驻进程调用本地 Mio 声线模型。"""

    backend_name = MIO_TTS_BACKEND
    backend_display_name = "Mio TTS"
    supports_prewarm = True

    def __init__(self, config):
        self.python_path = resolve_project_path(
            config.get("mio_tts_python", DEFAULT_MIO_TTS_PYTHON)
        )
        self.worker_path = resolve_project_path(
            config.get("mio_tts_worker", DEFAULT_MIO_TTS_WORKER)
        )
        self.repo_path = resolve_project_path(
            config.get("mio_tts_repo", DEFAULT_MIO_TTS_REPO)
        )
        self.model_path = resolve_project_path(
            config.get("mio_tts_model", DEFAULT_MIO_TTS_MODEL)
        )
        self.config_path = resolve_project_path(
            config.get("mio_tts_config", DEFAULT_MIO_TTS_CONFIG)
        )
        self.style_vectors_path = resolve_project_path(
            config.get("mio_tts_style_vectors", DEFAULT_MIO_TTS_STYLE_VECTORS)
        )
        self.output_dir = resolve_project_path(
            config.get("mio_tts_output_dir", "data/mio_tts_runtime")
        )
        self.device = str(config.get("mio_tts_device", "cuda") or "cuda")
        self.startup_timeout = max(
            5.0, float(config.get("mio_tts_startup_timeout_seconds", 45.0))
        )
        self.synthesis_timeout = max(
            5.0, float(config.get("mio_tts_timeout_seconds", 120.0))
        )
        self.sdp_ratio = max(0.0, min(1.0, float(config.get("mio_tts_sdp_ratio", 0.35))))
        self.noise = max(0.0, min(2.0, float(config.get("mio_tts_noise", 0.5))))
        self.noise_w = max(0.0, min(2.0, float(config.get("mio_tts_noise_w", 0.7))))
        self.style_weight = max(
            0.0, min(100.0, float(config.get("mio_tts_style_weight", 1.0)))
        )
        self.endpoint = f"local model {self.model_path}"
        self._process = None
        self._events = queue.Queue()
        self._reader_thread = None
        self._lock = threading.RLock()
        self._startup_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self.last_error = ""

    def is_available(self):
        try:
            self._ensure_process()
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("Mio 本地语音模型不可用：%s", exc)
            return False

    def synthesize(self, text, _speaker_id=0, speed_scale=1.0, volume_scale=1.0):
        with self._request_lock:
            self._ensure_process()
            request_id = uuid.uuid4().hex
            request = {
                "id": request_id,
                "text": text,
                "speed_scale": speed_scale,
                "volume_scale": volume_scale,
            }
            with self._lock:
                try:
                    self._process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                    self._process.stdin.flush()
                except (AttributeError, BrokenPipeError, OSError) as exc:
                    self.close()
                    raise MioStyleBertError(f"Mio TTS request failed: {exc}") from exc

            try:
                event = self._wait_for_event(
                    request_id,
                    self.synthesis_timeout,
                    phase="synthesis",
                )
            except Exception:
                self.close()
                raise
            if event.get("type") == "error":
                raise MioStyleBertError(event.get("message") or "Mio TTS failed")
            output_path = Path(event.get("path", "")).resolve(strict=False)
            output_root = Path(self.output_dir).resolve(strict=False)
            if output_root not in output_path.parents:
                raise MioStyleBertError("Mio TTS returned an unsafe output path")
            try:
                return output_path.read_bytes()
            except OSError as exc:
                raise MioStyleBertError(f"Cannot read Mio TTS audio: {exc}") from exc
            finally:
                try:
                    output_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def close(self, force=False):
        with self._lock:
            process = self._process
            self._process = None
        if process is None:
            return
        if force:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.75)
                except subprocess.TimeoutExpired:
                    process.kill()
            return
        try:
            if process.poll() is None and process.stdin is not None:
                process.stdin.write('{"command":"shutdown"}\n')
                process.stdin.flush()
                process.wait(timeout=1.5)
        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                process.kill()

    def cancel(self):
        """Immediately stop a loading or synthesizing local worker."""
        self.close(force=True)

    def _required_paths(self):
        return {
            "Python 3.10": self.python_path,
            "worker": self.worker_path,
            "Style-Bert-VITS2": self.repo_path,
            "model": self.model_path,
            "config": self.config_path,
            "style vectors": self.style_vectors_path,
        }

    def _worker_environment(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["TOKENIZERS_PARALLELISM"] = "false"
        return env

    def _worker_command(self):
        return [
            str(self.python_path),
            str(self.worker_path),
            "--repo", str(self.repo_path),
            "--model", str(self.model_path),
            "--config", str(self.config_path),
            "--style-vectors", str(self.style_vectors_path),
            "--output-dir", str(self.output_dir),
            "--device", self.device,
            "--sdp-ratio", str(self.sdp_ratio),
            "--noise", str(self.noise),
            "--noise-w", str(self.noise_w),
            "--style-weight", str(self.style_weight),
        ]

    def _missing_files_error(self, missing):
        return MioStyleBertError("Missing Mio TTS files: " + ", ".join(missing))

    def _startup_error(self, message):
        return MioStyleBertError(message)

    def _startup_log(self):
        logger.info("Mio 本地语音模型已加载：%s", self.model_path.name)

    def _reader_thread_name(self):
        return "mio-tts-output"

    def _ensure_process(self):
        with self._startup_lock:
            with self._lock:
                if self._process is not None and self._process.poll() is None:
                    return
                missing = [
                    label
                    for label, path in self._required_paths().items()
                    if path is None or not Path(path).exists()
                ]
                if missing:
                    raise self._missing_files_error(missing)

                Path(self.output_dir).mkdir(parents=True, exist_ok=True)
                event_queue = queue.Queue()
                self._events = event_queue
                try:
                    process = subprocess.Popen(
                        self._worker_command(),
                        cwd=str(self.repo_path),
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                        env=self._worker_environment(),
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except OSError as exc:
                    raise self._startup_error(
                        f"Cannot start {self.backend_display_name} worker: {exc}"
                    ) from exc

                self._process = process
                self._reader_thread = threading.Thread(
                    target=self._read_worker_output,
                    args=(process, event_queue),
                    name=self._reader_thread_name(),
                    daemon=True,
                )
                self._reader_thread.start()

            try:
                event = self._wait_for_event(
                    None,
                    self.startup_timeout,
                    phase="startup",
                    event_queue=event_queue,
                )
            except Exception:
                self.close()
                raise
            with self._lock:
                process_is_current = self._process is process
            if not process_is_current or process.poll() is not None:
                raise self._startup_error(
                    f"{self.backend_display_name} worker stopped during startup"
                )
            if event.get("type") != "ready":
                message = event.get("message") or f"{self.backend_display_name} worker exited during startup"
                self.close()
                raise self._startup_error(message)
            self._startup_log()

    def _read_worker_output(self, process, event_queue):
        stdout = process.stdout
        if stdout is None:
            event_queue.put({"type": "eof", "message": "Mio TTS has no stdout"})
            return
        for line in stdout:
            line = line.rstrip()
            if line.startswith(_MIO_EVENT_PREFIX):
                try:
                    event = json.loads(line[len(_MIO_EVENT_PREFIX):])
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "status":
                    logger.info(
                        "[%s] %s",
                        self.backend_display_name,
                        event.get("message") or event.get("stage") or "loading",
                    )
                event_queue.put(event)
            elif line:
                logger.debug("[Mio TTS] %s", line)
        event_queue.put({"type": "eof", "message": "Mio TTS worker stopped"})

    def _wait_for_event(
        self,
        request_id,
        timeout,
        phase="operation",
        event_queue=None,
    ):
        events = event_queue if event_queue is not None else self._events
        deadline = time.monotonic() + timeout
        timeout_message = (
            f"{self.backend_display_name} {phase} timed out after {timeout:.0f}s"
        )
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise self._startup_error(timeout_message)
            try:
                event = events.get(timeout=remaining)
            except queue.Empty as exc:
                raise self._startup_error(timeout_message) from exc
            event_id = event.get("id")
            if event.get("type") in {"fatal", "eof"}:
                raise self._startup_error(event.get("message") or "Mio TTS worker stopped")
            if request_id is None and event.get("type") == "ready":
                return event
            if request_id is not None and event_id == request_id:
                return event


class MioGPTSoVITSClient(MioStyleBertClient):
    """通过独立 Python 3.10 常驻进程调用 Mio V2ProPlus e15。"""

    backend_name = MIO_GPT_SOVITS_BACKEND
    backend_display_name = "GPT-SoVITS"
    supports_mood_reference = True
    supports_voice_style = True

    def __init__(self, config):
        super().__init__(config)
        self.startup_timeout = max(
            5.0,
            float(config.get("mio_gpt_sovits_startup_timeout_seconds", 180.0)),
        )
        self.python_path = resolve_project_path(
            config.get("mio_gpt_sovits_python", DEFAULT_MIO_GPT_SOVITS_PYTHON)
        )
        self.worker_path = resolve_project_path(
            config.get("mio_gpt_sovits_worker", DEFAULT_MIO_GPT_SOVITS_WORKER)
        )
        self.repo_path = resolve_project_path(
            config.get("mio_gpt_sovits_repo", DEFAULT_MIO_GPT_SOVITS_REPO)
        )
        self.gpt_weights_path = resolve_project_path(
            config.get(
                "mio_gpt_sovits_gpt_weights",
                DEFAULT_MIO_GPT_SOVITS_GPT_WEIGHTS,
            )
        )
        self.sovits_weights_path = resolve_project_path(
            config.get(
                "mio_gpt_sovits_sovits_weights",
                DEFAULT_MIO_GPT_SOVITS_SOVITS_WEIGHTS,
            )
        )
        configured_references = config.get("mio_gpt_sovits_references")
        if not isinstance(configured_references, dict):
            configured_references = DEFAULT_MIO_GPT_SOVITS_REFERENCES
        self.references = {}
        for mood, fallback in DEFAULT_MIO_GPT_SOVITS_REFERENCES.items():
            configured = configured_references.get(mood)
            if not isinstance(configured, dict):
                configured = fallback
            audio_path = resolve_project_path(
                configured.get("audio", fallback["audio"])
            )
            prompt = str(configured.get("prompt", fallback["prompt"]) or "").strip()
            self.references[mood] = {"audio": str(audio_path), "prompt": prompt}
        self.endpoint = (
            f"local GPT-SoVITS {self.gpt_weights_path.name} / "
            f"{self.sovits_weights_path.name}"
        )

    def synthesize(
        self,
        text,
        _speaker_id=0,
        speed_scale=1.0,
        volume_scale=1.0,
        mood="neutral",
        voice_style="conversational",
    ):
        with self._request_lock:
            self._ensure_process()
            request_id = uuid.uuid4().hex
            request = {
                "id": request_id,
                "text": text,
                "mood": mood,
                "voice_style": voice_style,
                "speed_scale": speed_scale,
                "volume_scale": volume_scale,
            }
            with self._lock:
                try:
                    self._process.stdin.write(
                        json.dumps(request, ensure_ascii=False) + "\n"
                    )
                    self._process.stdin.flush()
                except (AttributeError, BrokenPipeError, OSError) as exc:
                    self.close()
                    raise MioGPTSoVITSError(
                        f"GPT-SoVITS request failed: {exc}"
                    ) from exc

            try:
                event = self._wait_for_event(
                    request_id,
                    self.synthesis_timeout,
                    phase="synthesis",
                )
            except Exception:
                self.close()
                raise
            if event.get("type") == "error":
                raise MioGPTSoVITSError(
                    event.get("message") or "GPT-SoVITS synthesis failed"
                )
            output_path = Path(event.get("path", "")).resolve(strict=False)
            output_root = Path(self.output_dir).resolve(strict=False)
            if output_root not in output_path.parents:
                raise MioGPTSoVITSError("GPT-SoVITS returned an unsafe output path")
            try:
                return output_path.read_bytes()
            except OSError as exc:
                raise MioGPTSoVITSError(
                    f"Cannot read GPT-SoVITS audio: {exc}"
                ) from exc
            finally:
                try:
                    output_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _required_paths(self):
        required = {
            "Python 3.10": self.python_path,
            "worker": self.worker_path,
            "GPT-SoVITS": self.repo_path,
            "GPT e15 weights": self.gpt_weights_path,
            "SoVITS e8 weights": self.sovits_weights_path,
        }
        for mood, reference in self.references.items():
            required[f"{mood} reference"] = Path(reference["audio"])
        return required

    def _worker_environment(self):
        env = super()._worker_environment()
        env["PYTHONUTF8"] = "1"
        return env

    def _worker_command(self):
        return [
            str(self.python_path),
            str(self.worker_path),
            "--repo", str(self.repo_path),
            "--gpt-weights", str(self.gpt_weights_path),
            "--sovits-weights", str(self.sovits_weights_path),
            "--references", json.dumps(self.references, ensure_ascii=False),
            "--output-dir", str(self.output_dir),
            "--device", self.device,
        ]

    def _missing_files_error(self, missing):
        return MioGPTSoVITSError(
            "Missing GPT-SoVITS files: " + ", ".join(missing)
        )

    def _startup_error(self, message):
        return MioGPTSoVITSError(message)

    def _startup_log(self):
        logger.info(
            "Mio GPT-SoVITS 已加载：%s / %s",
            self.gpt_weights_path.name,
            self.sovits_weights_path.name,
        )

    def _reader_thread_name(self):
        return "mio-gpt-sovits-output"
