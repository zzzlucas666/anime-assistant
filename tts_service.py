"""本地语音模型 / AivisSpeech 的后台合成、翻译与嘴型包络计算。"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
import uuid

from ai.client import create_ai_client
from app_paths import resolve_project_path
from logger_utils import get_logger


logger = get_logger(__name__)

DEFAULT_AIVIS_ENDPOINT = "http://127.0.0.1:10101"
DEFAULT_AIVIS_TIMEOUT_SECONDS = 60.0
DEFAULT_AIVIS_MAX_CHARS = 56
DEFAULT_TTS_BACKEND = "aivis"
MIO_TTS_BACKEND = "mio_style_bert_vits2"
DEFAULT_MIO_TTS_PYTHON = (
    "data/training_tools/Style-Bert-VITS2/venv/Scripts/python.exe"
)
DEFAULT_MIO_TTS_WORKER = "tts_style_bert_worker.py"
DEFAULT_MIO_TTS_REPO = "data/training_tools/Style-Bert-VITS2"
DEFAULT_MIO_TTS_MODEL = (
    "data/mio_voice_dataset/style_bert_vits2/model_assets/mio_pilot_v1/"
    "mio_pilot_v1_e43_s2000.safetensors"
)
DEFAULT_MIO_TTS_CONFIG = (
    "data/mio_voice_dataset/style_bert_vits2/model_assets/mio_pilot_v1/config.json"
)
DEFAULT_MIO_TTS_STYLE_VECTORS = (
    "data/mio_voice_dataset/style_bert_vits2/model_assets/mio_pilot_v1/"
    "style_vectors.npy"
)
_MIO_EVENT_PREFIX = "MIO_TTS_EVENT\t"
DEFAULT_MOOD_SPEAKERS = {
    "neutral": 1878365376,  # コハク / ノーマル
    "happy": 1878365377,    # コハク / あまあま
    "shy": 1878365377,
    "sad": 1878365378,      # コハク / せつなめ
    "tired": 1878365379,    # コハク / ねむたい
}

_STAGE_DIRECTION_RE = re.compile(r"\([^()]{1,80}\)|（[^（）]{1,80}）")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。！？!?])")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")


class AivisSpeechError(RuntimeError):
    """AivisSpeech 无法完成请求。"""


class MioStyleBertError(RuntimeError):
    """本地 Mio Style-Bert-VITS2 进程无法完成请求。"""


@dataclass(frozen=True)
class SpeechAudio:
    wav_data: bytes
    mouth_envelope: tuple[float, ...]
    envelope_window_ms: int
    spoken_text: str


def prepare_spoken_text(text):
    """去掉舞台动作和多余空白，只保留真正需要朗读的内容。"""
    if not isinstance(text, str):
        return ""
    cleaned = _STAGE_DIRECTION_RE.sub("", text)
    return " ".join(cleaned.split()).strip()


def contains_japanese_kana(text):
    return bool(_KANA_RE.search(text or ""))


def split_sentences(text, maximum_chars=DEFAULT_AIVIS_MAX_CHARS):
    """按日语/中文句末标点切分，过长句子再按逗号做软切分。"""
    text = prepare_spoken_text(text)
    if not text:
        return []

    sentences = []
    for part in _SENTENCE_BOUNDARY_RE.split(text):
        part = part.strip()
        if not part:
            continue
        if len(part) <= maximum_chars:
            sentences.append(part)
            continue

        current = ""
        for piece in re.split(r"(?<=[、，,；;])", part):
            if current and len(current) + len(piece) > maximum_chars:
                sentences.append(current.strip())
                current = ""
            while len(piece) > maximum_chars:
                available = maximum_chars - len(current)
                current += piece[:available]
                piece = piece[available:]
                if current.strip():
                    sentences.append(current.strip())
                current = ""
            current += piece
        if current.strip():
            sentences.append(current.strip())
    return sentences


class JapaneseSpeechTranslator:
    """把界面中的中文回复转换成仅供语音后端发声的自然日语。"""

    def __init__(self, api_key, model, base_url=None):
        self.model = model
        self.client = create_ai_client(api_key, base_url)

    def translate(self, text):
        cleaned = prepare_spoken_text(text)
        if not cleaned or contains_japanese_kana(cleaned):
            return cleaned

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "把用户提供的角色台词翻译成自然、口语化的日语。"
                        "保持原本的语气、情绪和句子数量，不添加解释、括号动作、"
                        "说话人名称或引号，只输出日语台词。"
                    ),
                },
                {"role": "user", "content": cleaned},
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content if response.choices else ""
        return prepare_spoken_text(content)


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
                event = self._wait_for_event(request_id, self.synthesis_timeout)
            except Exception:
                # 超时通常意味着推理进程仍卡在旧请求中。终止后再由上层整条
                # 回退，避免迟到结果污染下一条回复或遗留临时 WAV。
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

    def close(self):
        with self._lock:
            process = self._process
            self._process = None
            if process is None:
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

    def _ensure_process(self):
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return
            required = {
                "Python 3.10": self.python_path,
                "worker": self.worker_path,
                "Style-Bert-VITS2": self.repo_path,
                "model": self.model_path,
                "config": self.config_path,
                "style vectors": self.style_vectors_path,
            }
            missing = [label for label, path in required.items() if path is None or not Path(path).exists()]
            if missing:
                raise MioStyleBertError("Missing Mio TTS files: " + ", ".join(missing))

            Path(self.output_dir).mkdir(parents=True, exist_ok=True)
            event_queue = queue.Queue()
            self._events = event_queue
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["TOKENIZERS_PARALLELISM"] = "false"
            command = [
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
            try:
                self._process = subprocess.Popen(
                    command,
                    cwd=str(self.repo_path),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=env,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as exc:
                self._process = None
                raise MioStyleBertError(f"Cannot start Mio TTS worker: {exc}") from exc

            self._reader_thread = threading.Thread(
                target=self._read_worker_output,
                args=(self._process, event_queue),
                name="mio-tts-output",
                daemon=True,
            )
            self._reader_thread.start()
            try:
                event = self._wait_for_event(None, self.startup_timeout)
            except Exception:
                self.close()
                raise
            if event.get("type") != "ready":
                message = event.get("message") or "Mio TTS worker exited during startup"
                self.close()
                raise MioStyleBertError(message)
            logger.info("Mio 本地语音模型已加载：%s", self.model_path.name)

    def _read_worker_output(self, process, event_queue):
        stdout = process.stdout
        if stdout is None:
            event_queue.put({"type": "eof", "message": "Mio TTS has no stdout"})
            return
        for line in stdout:
            line = line.rstrip()
            if line.startswith(_MIO_EVENT_PREFIX):
                try:
                    event_queue.put(json.loads(line[len(_MIO_EVENT_PREFIX):]))
                except json.JSONDecodeError:
                    continue
            elif line:
                logger.debug("[Mio TTS] %s", line)
        event_queue.put({"type": "eof", "message": "Mio TTS worker stopped"})

    def _wait_for_event(self, request_id, timeout):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MioStyleBertError("Mio TTS timed out")
            try:
                event = self._events.get(timeout=remaining)
            except queue.Empty as exc:
                raise MioStyleBertError("Mio TTS timed out") from exc
            event_id = event.get("id")
            if event.get("type") in {"fatal", "eof"}:
                raise MioStyleBertError(event.get("message") or "Mio TTS worker stopped")
            if request_id is None and event.get("type") == "ready":
                return event
            if request_id is not None and event_id == request_id:
                return event


def build_mouth_envelope(wav_data, window_ms=33):
    """从 PCM WAV 计算 0..1 的短时响度，供 Live2D 实际音频口型使用。"""
    try:
        import numpy as np

        with wave.open(BytesIO(wav_data), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            raw = wav_file.readframes(wav_file.getnframes())
    except (ImportError, EOFError, wave.Error, ValueError):
        return ()

    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(sample_width)
    if dtype is None or not raw:
        return ()

    samples = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    if sample_width == 1:
        samples -= 128.0
    if channels > 1:
        usable = len(samples) - (len(samples) % channels)
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)

    window_size = max(1, int(sample_rate * window_ms / 1000))
    rms_values = []
    full_scale = float(2 ** (sample_width * 8 - 1))
    for start in range(0, len(samples), window_size):
        chunk = samples[start:start + window_size]
        if len(chunk):
            rms_values.append(math.sqrt(float(np.mean(chunk * chunk))) / full_scale)
    if not rms_values:
        return ()

    rms = np.asarray(rms_values)
    floor = float(np.percentile(rms, 18))
    ceiling = max(float(np.percentile(rms, 92)), floor + 1e-6)
    normalized = np.clip((rms - floor) / (ceiling - floor), 0.0, 1.0)
    # 嘴型比原始响度稍柔和，低声也保留可见开合。
    shaped = np.sqrt(normalized) * 0.9
    return tuple(float(value) for value in shaped)


def combine_speech_audio(audio_batch, pause_ms=90):
    """把一条回复的多个 PCM WAV 合成单一音频源，避免 Qt 分段切换卡死。"""
    audio_batch = list(audio_batch or [])
    if not audio_batch:
        return None
    if len(audio_batch) == 1:
        return audio_batch[0]

    decoded = []
    reference = None
    for audio in audio_batch:
        try:
            with wave.open(BytesIO(audio.wav_data), "rb") as wav_file:
                params = (
                    wav_file.getnchannels(),
                    wav_file.getsampwidth(),
                    wav_file.getframerate(),
                    wav_file.getcomptype(),
                    wav_file.getcompname(),
                )
                frames = wav_file.readframes(wav_file.getnframes())
        except (EOFError, wave.Error) as exc:
            raise AivisSpeechError(f"Invalid WAV returned by TTS backend: {exc}") from exc
        if reference is None:
            reference = params
        elif params[:4] != reference[:4]:
            raise AivisSpeechError("TTS backend returned incompatible WAV formats")
        decoded.append(frames)

    channels, sample_width, sample_rate, compression, compression_name = reference
    pause_frames = max(0, int(sample_rate * max(0, pause_ms) / 1000))
    silence_sample = b"\x80" if sample_width == 1 else b"\x00" * sample_width
    silence = silence_sample * channels * pause_frames

    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.setcomptype(compression, compression_name)
        for index, frames in enumerate(decoded):
            if index:
                wav_file.writeframesraw(silence)
            wav_file.writeframesraw(frames)
    wav_data = output.getvalue()
    return SpeechAudio(
        wav_data=wav_data,
        mouth_envelope=build_mouth_envelope(wav_data),
        envelope_window_ms=33,
        spoken_text="".join(audio.spoken_text for audio in audio_batch),
    )


class SpeechSynthesisService:
    """单后台线程的语音队列；网络和合成永远不占用 Qt 主线程。"""

    def __init__(self, config, on_audio_ready, on_error=None):
        self.config = config
        self.on_audio_ready = on_audio_ready
        self.on_error = on_error or (lambda _message: None)
        aivis_client = AivisSpeechClient(
            config.get("aivis_endpoint", DEFAULT_AIVIS_ENDPOINT),
            config.get("aivis_timeout_seconds", DEFAULT_AIVIS_TIMEOUT_SECONDS),
        )
        backend = str(config.get("tts_backend", DEFAULT_TTS_BACKEND)).strip().lower()
        if backend == MIO_TTS_BACKEND:
            self.client = MioStyleBertClient(config)
            self.fallback_client = (
                aivis_client if config.get("tts_fallback_to_aivis", True) else None
            )
        else:
            self.client = aivis_client
            self.fallback_client = None
        self.translator = None
        if config.get("tts_translate_to_japanese", True):
            self.translator = JapaneseSpeechTranslator(
                config.get("api_key", ""),
                config.get("model", ""),
                config.get("base_url"),
            )
        self._jobs = queue.Queue(maxsize=4)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="speech-tts", daemon=True)
        self._thread.start()

    def speak(self, text, mood="neutral"):
        if self._stop_event.is_set() or not prepare_spoken_text(text):
            return False
        try:
            self._jobs.put_nowait((text, mood))
            return True
        except queue.Full:
            logger.warning("TTS 队列已满，本条语音已跳过")
            return False

    def shutdown(self):
        self._stop_event.set()
        # 窗口销毁后后台请求可能仍在超时收尾，避免再触碰已销毁的 Qt 信号。
        self.on_audio_ready = lambda _audio: None
        self.on_error = lambda _message: None
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            pass
        for client in (self.client, getattr(self, "fallback_client", None)):
            close = getattr(client, "close", None)
            if callable(close):
                close()
        self._thread.join(timeout=2.0)

    def _run(self):
        while not self._stop_event.is_set():
            job = self._jobs.get()
            if job is None:
                return
            text, mood = job
            try:
                spoken_text = self.translator.translate(text) if self.translator else prepare_spoken_text(text)
                speaker_id = self._speaker_for_mood(mood)
                sentences = split_sentences(
                    spoken_text,
                    self.config.get("aivis_max_chars_per_request", DEFAULT_AIVIS_MAX_CHARS),
                )
                if not sentences:
                    raise AivisSpeechError("No speakable text was generated")

                audio_batch = None
                last_error = None
                clients = [self.client]
                fallback_client = getattr(self, "fallback_client", None)
                if fallback_client is not None and fallback_client is not self.client:
                    clients.append(fallback_client)
                for client_index, client in enumerate(clients):
                    try:
                        if not client.is_available():
                            detail = getattr(client, "last_error", "")
                            raise AivisSpeechError(
                                detail or f"TTS backend is unavailable at {client.endpoint}"
                            )
                        audio_batch = self._synthesize_sentences(
                            client, sentences, speaker_id
                        )
                        if client_index:
                            logger.warning(
                                "Mio 本地语音不可用，本条回复已完整回退到 AivisSpeech"
                            )
                        break
                    except Exception as exc:
                        last_error = exc
                        audio_batch = None
                        logger.warning(
                            "TTS 后端 %s 合成失败：%s",
                            getattr(client, "backend_name", client.endpoint),
                            exc,
                        )
                if audio_batch is None:
                    raise last_error or AivisSpeechError("No TTS backend is available")

                # 所有片段都合成完毕后合并为一个 WAV。Qt/FFmpeg 只接触一个
                # 音频源，不再需要在 EndOfMedia 回调中连续切换 QBuffer。
                combined_audio = combine_speech_audio(audio_batch)
                if combined_audio is not None and not self._stop_event.is_set():
                    self.on_audio_ready(combined_audio)
            except Exception as exc:
                logger.warning("TTS 生成失败，已降级为文字回复：%s", exc)
                self.on_error(str(exc))

    def _synthesize_sentences(self, client, sentences, speaker_id):
        """完整合成所有片段；任一失败时由调用方整条回退或取消。"""
        audio_batch = []
        for sentence in sentences:
            if self._stop_event.is_set():
                raise AivisSpeechError("TTS service is shutting down")
            wav_data = client.synthesize(
                sentence,
                speaker_id,
                self.config.get("tts_speed_scale", 1.0),
                self.config.get("tts_volume_scale", 1.0),
            )
            audio_batch.append(
                SpeechAudio(
                    wav_data=wav_data,
                    mouth_envelope=build_mouth_envelope(wav_data),
                    envelope_window_ms=33,
                    spoken_text=sentence,
                )
            )
        return audio_batch

    def _speaker_for_mood(self, mood):
        mapping = self.config.get("aivis_mood_speakers") or DEFAULT_MOOD_SPEAKERS
        value = mapping.get(mood, mapping.get("neutral", DEFAULT_MOOD_SPEAKERS["neutral"]))
        try:
            return int(value)
        except (TypeError, ValueError):
            return DEFAULT_MOOD_SPEAKERS["neutral"]
