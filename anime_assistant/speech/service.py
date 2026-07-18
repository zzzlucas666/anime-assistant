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

from anime_assistant.ai.client import create_ai_client
from anime_assistant.infrastructure.paths import resolve_project_path
from anime_assistant.infrastructure.logging import get_logger


logger = get_logger(__name__)

DEFAULT_AIVIS_ENDPOINT = "http://127.0.0.1:10101"
DEFAULT_AIVIS_TIMEOUT_SECONDS = 60.0
DEFAULT_AIVIS_MAX_CHARS = 56
DEFAULT_LOCAL_TTS_RETRY_ATTEMPTS = 1
DEFAULT_TTS_BACKEND = "aivis"
MIO_TTS_BACKEND = "mio_style_bert_vits2"
MIO_GPT_SOVITS_BACKEND = "mio_gpt_sovits_v2proplus"
DEFAULT_MIO_TTS_PYTHON = (
    "data/training_tools/Style-Bert-VITS2/venv/Scripts/python.exe"
)
DEFAULT_MIO_TTS_WORKER = "anime_assistant/speech/style_bert_worker.py"
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
DEFAULT_MIO_GPT_SOVITS_PYTHON = (
    "data/training_tools/GPT-SoVITS/.venv/Scripts/python.exe"
)
DEFAULT_MIO_GPT_SOVITS_WORKER = "anime_assistant/speech/gpt_sovits_worker.py"
DEFAULT_MIO_GPT_SOVITS_REPO = "data/training_tools/GPT-SoVITS"
DEFAULT_MIO_GPT_SOVITS_GPT_WEIGHTS = (
    "data/mio_voice_dataset/gpt_sovits/v2proplus_v1/weights/gpt/"
    "mio_v2proplus_v1-e15.ckpt"
)
DEFAULT_MIO_GPT_SOVITS_SOVITS_WEIGHTS = (
    "data/mio_voice_dataset/gpt_sovits/v2proplus_v1/weights/sovits/"
    "mio_v2proplus_v1_e8_s768.pth"
)
DEFAULT_MIO_GPT_SOVITS_REFERENCES = {
    "neutral": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0002.wav"
        ),
        "prompt": "今何時だ。おはよう。こんにちは。お昼だぞ。おやつ。",
    },
    "happy": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0045.wav"
        ),
        "prompt": "うまく演奏できた。ちょっと満足かも。今日は調子いいな。",
    },
    "shy": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0021.wav"
        ),
        "prompt": "見られてる？夢みたいだ。うまくできたかな。楽しんで。",
    },
    "sad": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0046.wav"
        ),
        "prompt": "うまく弾けなかった。今日はダメみたいだ。",
    },
    "tired": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0047.wav"
        ),
        "prompt": "食べ過ぎちゃった。眠くなってきた。",
    },
    # 以下是“本句说话方式”，与角色持续 mood 分离。一个音频可以服务于
    # 相近语气，但每个键都可由用户配置单独替换。
    "conversational": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0014.wav"
        ),
        "prompt": "よし、うまくいったな。うん、ありがとう。じゃあな、また。",
    },
    "thoughtful": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0011.wav"
        ),
        "prompt": "いろいろあるなぁ。どれにしよう。迷うなぁ。これなんかどうかな。",
    },
    "warm": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0014.wav"
        ),
        "prompt": "よし、うまくいったな。うん、ありがとう。じゃあな、また。",
    },
    "cheerful": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0045.wav"
        ),
        "prompt": "うまく演奏できた。ちょっと満足かも。今日は調子いいな。",
    },
    "excited": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0026.wav"
        ),
        "prompt": "行ってね。ノリノリで、ハイテンションでゴー。飛ばすぞ。全力でついてこい。",
    },
    "bashful": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0021.wav"
        ),
        "prompt": "見られてる？夢みたいだ。うまくできたかな。楽しんで。",
    },
    "embarrassed": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0029.wav"
        ),
        "prompt": "恥ずかしい。もう今日は帰ろうかな。こんなんじゃ武道館なんて。",
    },
    "concerned": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0022.wav"
        ),
        "prompt": "きっとやれるよな。怖くない。怖くない。フジツボは嫌いだ。",
    },
    "reassuring": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0022.wav"
        ),
        "prompt": "きっとやれるよな。怖くない。怖くない。フジツボは嫌いだ。",
    },
    "curious": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0011.wav"
        ),
        "prompt": "いろいろあるなぁ。どれにしよう。迷うなぁ。これなんかどうかな。",
    },
    "surprised": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0033.wav"
        ),
        "prompt": "大凶だ。なんだかドキドキすることがあるかも。テストがうまくいきそう。",
    },
    "mild_annoyed": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0030.wav"
        ),
        "prompt": "まだまだだな。もうダメかも。なんでだよ。",
    },
    "serious": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0030.wav"
        ),
        "prompt": "まだまだだな。もうダメかも。なんでだよ。",
    },
    "disappointed": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0046.wav"
        ),
        "prompt": "うまく弾けなかった。今日はダメみたいだ。",
    },
}
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


class MioGPTSoVITSError(RuntimeError):
    """本地 Mio GPT-SoVITS V2ProPlus 进程无法完成请求。"""


@dataclass(frozen=True)
class SpeechAudio:
    wav_data: bytes
    mouth_envelope: tuple[float, ...]
    envelope_window_ms: int
    spoken_text: str


@dataclass(frozen=True)
class _WarmupJob:
    """在正式语音之前加载本地模型，并在结束后继续其他启动任务。"""

    on_complete: object = None


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
                        "说话人名称或引号，只输出日语台词。英文人名、乐队名、"
                        "歌名和缩写也要转写成自然的日语片假名，不保留拉丁字母。"
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
                event = self._wait_for_event(
                    None,
                    self.startup_timeout,
                    phase="startup",
                )
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

    def _wait_for_event(self, request_id, timeout, phase="operation"):
        deadline = time.monotonic() + timeout
        timeout_message = (
            f"{self.backend_display_name} {phase} timed out after {timeout:.0f}s"
        )
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MioStyleBertError(timeout_message)
            try:
                event = self._events.get(timeout=remaining)
            except queue.Empty as exc:
                raise MioStyleBertError(timeout_message) from exc
            event_id = event.get("id")
            if event.get("type") in {"fatal", "eof"}:
                raise MioStyleBertError(event.get("message") or "Mio TTS worker stopped")
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

    def _ensure_process(self):
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return
            required = {
                "Python 3.10": self.python_path,
                "worker": self.worker_path,
                "GPT-SoVITS": self.repo_path,
                "GPT e15 weights": self.gpt_weights_path,
                "SoVITS e8 weights": self.sovits_weights_path,
            }
            for mood, reference in self.references.items():
                required[f"{mood} reference"] = Path(reference["audio"])
            missing = [
                label
                for label, path in required.items()
                if path is None or not Path(path).exists()
            ]
            if missing:
                raise MioGPTSoVITSError(
                    "Missing GPT-SoVITS files: " + ", ".join(missing)
                )

            Path(self.output_dir).mkdir(parents=True, exist_ok=True)
            event_queue = queue.Queue()
            self._events = event_queue
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            env["TOKENIZERS_PARALLELISM"] = "false"
            command = [
                str(self.python_path),
                str(self.worker_path),
                "--repo",
                str(self.repo_path),
                "--gpt-weights",
                str(self.gpt_weights_path),
                "--sovits-weights",
                str(self.sovits_weights_path),
                "--references",
                json.dumps(self.references, ensure_ascii=False),
                "--output-dir",
                str(self.output_dir),
                "--device",
                self.device,
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
                raise MioGPTSoVITSError(
                    f"Cannot start GPT-SoVITS worker: {exc}"
                ) from exc

            self._reader_thread = threading.Thread(
                target=self._read_worker_output,
                args=(self._process, event_queue),
                name="mio-gpt-sovits-output",
                daemon=True,
            )
            self._reader_thread.start()
            try:
                event = self._wait_for_event(
                    None,
                    self.startup_timeout,
                    phase="startup",
                )
            except Exception:
                self.close()
                raise
            if event.get("type") != "ready":
                message = event.get("message") or "GPT-SoVITS worker failed to start"
                self.close()
                raise MioGPTSoVITSError(message)
            logger.info(
                "Mio GPT-SoVITS 已加载：%s / %s",
                self.gpt_weights_path.name,
                self.sovits_weights_path.name,
            )


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

    def __init__(self, config, on_audio_ready, on_error=None, on_status=None):
        self.config = config
        self.on_audio_ready = on_audio_ready
        self.on_error = on_error or (lambda _message: None)
        self.on_status = on_status or (lambda _status: None)
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
        elif backend == MIO_GPT_SOVITS_BACKEND:
            self.client = MioGPTSoVITSClient(config)
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
        try:
            retry_attempts = int(
                config.get(
                    "mio_tts_retry_attempts",
                    DEFAULT_LOCAL_TTS_RETRY_ATTEMPTS,
                )
            )
        except (TypeError, ValueError):
            retry_attempts = DEFAULT_LOCAL_TTS_RETRY_ATTEMPTS
        self.local_retry_attempts = max(0, min(2, retry_attempts))
        self._jobs = queue.Queue(maxsize=4)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="speech-tts", daemon=True)
        self._thread.start()

    def prewarm(self, on_complete=None):
        """把本地模型预热排在第一条语音之前；非本地后端无需预热。"""
        if self._stop_event.is_set() or not getattr(
            self.client, "supports_prewarm", False
        ):
            return False
        try:
            self._jobs.put_nowait(_WarmupJob(on_complete=on_complete))
            return True
        except queue.Full:
            logger.warning("TTS 队列已满，无法安排本地模型预热")
            return False

    def _notify_status(self, status):
        """兼容旧调用方和最小化测试对象：没有状态回调时静默跳过。"""
        callback = getattr(self, "on_status", None)
        if callable(callback):
            callback(status)

    def speak(
        self,
        text,
        mood="neutral",
        emotion_strength=1.0,
        modifier="none",
        fatigue_strength=0.0,
        voice_style=None,
        voice_style_strength=0.6,
    ):
        if self._stop_event.is_set() or not prepare_spoken_text(text):
            return False
        try:
            self._jobs.put_nowait(
                (
                    text,
                    mood,
                    emotion_strength,
                    modifier,
                    fatigue_strength,
                    voice_style,
                    voice_style_strength,
                )
            )
            return True
        except queue.Full:
            logger.warning("TTS 队列已满，本条语音已跳过")
            return False

    def shutdown(self):
        self._stop_event.set()
        # 窗口销毁后后台请求可能仍在超时收尾，避免再触碰已销毁的 Qt 信号。
        self.on_audio_ready = lambda _audio: None
        self.on_error = lambda _message: None
        self.on_status = lambda _status: None
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
            if isinstance(job, _WarmupJob):
                self._run_warmup(job)
                continue
            if len(job) >= 7:
                (
                    text,
                    mood,
                    emotion_strength,
                    modifier,
                    fatigue_strength,
                    voice_style,
                    voice_style_strength,
                ) = job[:7]
            elif len(job) >= 6:
                text, mood, emotion_strength, modifier, fatigue_strength, voice_style = job[:6]
                voice_style_strength = 0.6
            elif len(job) >= 5:
                text, mood, emotion_strength, modifier, fatigue_strength = job[:5]
                voice_style = None
                voice_style_strength = 0.6
            else:
                # 兼容旧测试、旧队列和可能仍在运行的调用方。
                text, mood = job
                emotion_strength = 1.0
                modifier = "none"
                fatigue_strength = 0.0
                voice_style = None
                voice_style_strength = 0.6
            voice_style = self._effective_voice_style(
                mood,
                emotion_strength,
                modifier,
                fatigue_strength,
                voice_style,
            )
            speed_multiplier = self._emotion_speed_multiplier(
                mood,
                emotion_strength,
                modifier,
                fatigue_strength,
                voice_style,
                voice_style_strength,
            )
            mood = self._effective_mood(
                mood,
                emotion_strength,
                modifier,
                fatigue_strength,
            )
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
                backend_failures = []
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
                        audio_batch = self._synthesize_sentences_with_recovery(
                            client,
                            sentences,
                            speaker_id,
                            mood,
                            voice_style=voice_style,
                            speed_multiplier=speed_multiplier,
                        )
                        if client_index:
                            logger.warning(
                                "Mio 本地语音不可用，本条回复已完整回退到 AivisSpeech"
                            )
                        break
                    except Exception as exc:
                        last_error = exc
                        audio_batch = None
                        backend_failures.append(
                            (
                                getattr(client, "backend_name", client.endpoint),
                                exc,
                            )
                        )
                        logger.warning(
                            "TTS 后端 %s 合成失败：%s",
                            getattr(client, "backend_name", client.endpoint),
                            exc,
                        )
                if audio_batch is None:
                    if len(backend_failures) > 1:
                        details = "；".join(
                            f"{backend}: {error}"
                            for backend, error in backend_failures
                        )
                        raise AivisSpeechError(
                            f"所有 TTS 后端均失败（{details}）"
                        )
                    raise last_error or AivisSpeechError("No TTS backend is available")

                # 所有片段都合成完毕后合并为一个 WAV。Qt/FFmpeg 只接触一个
                # 音频源，不再需要在 EndOfMedia 回调中连续切换 QBuffer。
                combined_audio = combine_speech_audio(audio_batch)
                if combined_audio is not None and not self._stop_event.is_set():
                    self._notify_status("ready")
                    self.on_audio_ready(combined_audio)
            except Exception as exc:
                logger.warning("TTS 生成失败，已降级为文字回复：%s", exc)
                self._notify_status("error")
                self.on_error(str(exc))

    def _run_warmup(self, job):
        """在语音线程中完成冷启动，始终放行后续语义模型预热。"""
        self._notify_status("loading")
        started_at = time.perf_counter()
        try:
            if not self.client.is_available():
                detail = getattr(self.client, "last_error", "")
                raise AivisSpeechError(detail or "Mio local TTS is unavailable")
        except Exception as exc:
            logger.warning("Mio 本地语音预热失败：%s", exc)
            self._notify_status("error")
        else:
            logger.info(
                "Mio 本地语音预热完成 duration=%.3fs",
                time.perf_counter() - started_at,
            )
            self._notify_status("ready")
        finally:
            if callable(job.on_complete):
                try:
                    job.on_complete()
                except Exception as exc:
                    logger.warning("TTS 预热完成回调失败：%s", exc)

    def _synthesize_sentences(
        self,
        client,
        sentences,
        speaker_id,
        mood="neutral",
        voice_style="conversational",
        speed_multiplier=1.0,
    ):
        """完整合成所有片段；任一失败时由调用方整条回退或取消。"""
        audio_batch = []
        for sentence in sentences:
            if self._stop_event.is_set():
                raise AivisSpeechError("TTS service is shutting down")
            synthesis_args = (
                sentence,
                speaker_id,
                self.config.get("tts_speed_scale", 1.0) * speed_multiplier,
                self.config.get("tts_volume_scale", 1.0),
            )
            if getattr(client, "supports_voice_style", False):
                wav_data = client.synthesize(
                    *synthesis_args,
                    mood=mood,
                    voice_style=voice_style,
                )
            elif getattr(client, "supports_mood_reference", False):
                wav_data = client.synthesize(*synthesis_args, mood=mood)
            else:
                wav_data = client.synthesize(*synthesis_args)
            audio_batch.append(
                SpeechAudio(
                    wav_data=wav_data,
                    mouth_envelope=build_mouth_envelope(wav_data),
                    envelope_window_ms=33,
                    spoken_text=sentence,
                )
            )
        return audio_batch

    def _synthesize_sentences_with_recovery(
        self,
        client,
        sentences,
        speaker_id,
        mood="neutral",
        voice_style="conversational",
        speed_multiplier=1.0,
    ):
        """本地常驻进程偶发失步时，重启后重新合成完整回复。"""
        backend_name = getattr(client, "backend_name", "")
        is_local_client = backend_name in {
            MIO_TTS_BACKEND,
            MIO_GPT_SOVITS_BACKEND,
        }
        retry_attempts = (
            getattr(self, "local_retry_attempts", 0) if is_local_client else 0
        )
        for attempt in range(retry_attempts + 1):
            try:
                return self._synthesize_sentences(
                    client,
                    sentences,
                    speaker_id,
                    mood,
                    voice_style=voice_style,
                    speed_multiplier=speed_multiplier,
                )
            except Exception as exc:
                if attempt >= retry_attempts or self._stop_event.is_set():
                    raise
                logger.warning(
                    "本地 TTS 推理失败，将重启后重试完整回复（%d/%d）：%s",
                    attempt + 1,
                    retry_attempts,
                    exc,
                )
                close = getattr(client, "close", None)
                if callable(close):
                    close()

        raise AivisSpeechError("Local TTS retry loop ended unexpectedly")

    def _speaker_for_mood(self, mood):
        mapping = self.config.get("aivis_mood_speakers") or DEFAULT_MOOD_SPEAKERS
        value = mapping.get(mood, mapping.get("neutral", DEFAULT_MOOD_SPEAKERS["neutral"]))
        try:
            return int(value)
        except (TypeError, ValueError):
            return DEFAULT_MOOD_SPEAKERS["neutral"]

    @staticmethod
    def _effective_mood(mood, emotion_strength, modifier, fatigue_strength):
        """把连续情绪强度压到现有五组语音参考，避免轻微情绪直接满强度。"""
        try:
            strength = max(0.0, min(1.0, float(emotion_strength)))
        except (TypeError, ValueError):
            strength = 1.0
        try:
            fatigue = max(0.0, min(1.0, float(fatigue_strength)))
        except (TypeError, ValueError):
            fatigue = 0.0

        if mood == "tired" or fatigue >= 0.65:
            return "tired"
        if mood in {"happy", "shy", "sad"} and strength < 0.38:
            return "neutral"
        # touched 只增强已有开心，不把“关心用户”误读成 Mio 自己悲伤。
        if mood == "neutral" and modifier == "touched" and strength >= 0.5:
            return "happy"
        return mood if mood in {"neutral", "happy", "shy", "sad", "tired"} else "neutral"

    @staticmethod
    def _effective_voice_style(
        mood,
        emotion_strength,
        modifier,
        fatigue_strength,
        voice_style=None,
    ):
        """选择本句语气；显式 voice_style 优先，mood 仅用于兼容旧调用方。"""
        try:
            fatigue = max(0.0, min(1.0, float(fatigue_strength)))
        except (TypeError, ValueError):
            fatigue = 0.0
        if mood == "tired" or fatigue >= 0.65:
            return "tired"

        allowed = set(DEFAULT_MIO_GPT_SOVITS_REFERENCES) - {
            "neutral", "happy", "shy", "sad"
        }
        if isinstance(voice_style, str) and voice_style in allowed:
            return voice_style

        modifier_styles = {
            "worried": "concerned",
            "touched": "warm",
            "curious": "curious",
            "surprised": "surprised",
            "annoyed": "mild_annoyed",
        }
        if modifier in modifier_styles:
            return modifier_styles[modifier]
        return {
            "happy": "cheerful",
            "shy": "bashful",
            "sad": "disappointed",
            "tired": "tired",
        }.get(mood, "conversational")

    @staticmethod
    def _emotion_speed_multiplier(
        mood,
        emotion_strength,
        modifier,
        fatigue_strength,
        voice_style=None,
        voice_style_strength=0.6,
    ):
        """按本句语气微调语速；保留旧 mood 路径以兼容其他后端。"""
        try:
            strength = max(0.0, min(1.0, float(emotion_strength)))
        except (TypeError, ValueError):
            strength = 0.0
        try:
            fatigue = max(0.0, min(1.0, float(fatigue_strength)))
        except (TypeError, ValueError):
            fatigue = 0.0
        try:
            style_strength = max(0.0, min(1.0, float(voice_style_strength)))
        except (TypeError, ValueError):
            style_strength = 0.6

        multiplier = 1.0
        style_deltas = {
            "conversational": 0.0,
            "thoughtful": -0.03,
            "warm": -0.01,
            "cheerful": 0.03,
            "excited": 0.07,
            "bashful": -0.04,
            "embarrassed": -0.07,
            "concerned": -0.06,
            "reassuring": -0.04,
            "curious": 0.01,
            "surprised": 0.05,
            "mild_annoyed": -0.02,
            "serious": -0.05,
            "disappointed": -0.07,
            "tired": -0.10,
        }
        if voice_style in style_deltas:
            multiplier += style_deltas[voice_style] * (0.55 + 0.45 * style_strength)
        else:
            if mood == "happy":
                multiplier += 0.05 * strength
            elif mood == "shy":
                multiplier -= 0.035 * strength
            elif mood == "sad":
                multiplier -= 0.06 * strength
            if modifier == "worried":
                multiplier -= 0.035
            elif modifier == "surprised":
                multiplier += 0.035
            elif modifier == "annoyed":
                multiplier -= 0.02
        multiplier -= 0.08 * fatigue
        return max(0.86, min(1.09, multiplier))
