"""Speech queue orchestration and compatibility exports for TTS backends."""

from __future__ import annotations

import queue
import threading
import time
from contextlib import nullcontext

from anime_assistant.infrastructure.logging import get_logger
from anime_assistant.runtime.supervisor import TaskSupervisor
from anime_assistant.speech.audio import (
    SpeechAudio,
    build_mouth_envelope,
    combine_speech_audio,
)
from anime_assistant.speech.backends import (
    AivisSpeechClient,
    AivisSpeechError,
    MioGPTSoVITSClient,
    MioGPTSoVITSError,
    MioStyleBertClient,
    MioStyleBertError,
)
from anime_assistant.speech.config import (
    DEFAULT_AIVIS_ENDPOINT,
    DEFAULT_AIVIS_MAX_CHARS,
    DEFAULT_AIVIS_TIMEOUT_SECONDS,
    DEFAULT_LOCAL_TTS_RETRY_ATTEMPTS,
    DEFAULT_MIO_GPT_SOVITS_REFERENCES,
    DEFAULT_MIO_GPT_SOVITS_WORKER,
    DEFAULT_MIO_TTS_WORKER,
    DEFAULT_MOOD_SPEAKERS,
    DEFAULT_TTS_BACKEND,
    MIO_GPT_SOVITS_BACKEND,
    MIO_TTS_BACKEND,
)
from anime_assistant.speech.jobs import SpeechJob, WarmupJob
from anime_assistant.speech.style import (
    effective_mood,
    effective_voice_style,
    emotion_speed_multiplier,
)
from anime_assistant.speech.text import (
    contains_japanese_kana,
    prepare_spoken_text,
    split_sentences,
)
from anime_assistant.speech.translator import JapaneseSpeechTranslator


logger = get_logger(__name__)

_NON_RETRYABLE_TTS_ERROR_MARKERS = (
    "请输入有效文本",
    "empty gpt-sovits request",
    "no speakable text",
)


def _is_non_retryable_tts_error(exc):
    """Return whether restarting the model cannot change this input error."""
    message = str(exc or "").strip().casefold()
    return any(marker.casefold() in message for marker in _NON_RETRYABLE_TTS_ERROR_MARKERS)


_WarmupJob = WarmupJob


class _StaleSpeechTurn(RuntimeError):
    """Internal control flow: synthesis result belongs to an older turn."""


class SpeechSynthesisService:
    """单后台线程的语音队列；网络和合成永远不占用 Qt 主线程。"""

    def __init__(
        self,
        config,
        on_audio_ready,
        on_error=None,
        on_status=None,
        task_supervisor=None,
        is_turn_current=None,
    ):
        self.config = config
        self.on_audio_ready = on_audio_ready
        self.on_error = on_error or (lambda _message: None)
        self.on_status = on_status or (lambda _status: None)
        self._turn_checker = is_turn_current or (lambda _turn_id: True)
        self._owns_task_supervisor = task_supervisor is None
        self.task_supervisor = task_supervisor or TaskSupervisor(self._turn_checker)
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
        self._task_handle = self.task_supervisor.start(
            "speech-tts",
            lambda token: self._run(token),
            scope="speech-worker",
            cancel=self._signal_stop,
        )
        # Compatibility for diagnostics and older tests.
        self._thread = self._task_handle.thread

    def prewarm(self, on_complete=None):
        """把本地模型预热排在第一条语音之前；非本地后端无需预热。"""
        if self._stop_event.is_set() or not getattr(
            self.client, "supports_prewarm", False
        ):
            return False
        try:
            self._jobs.put_nowait(WarmupJob(on_complete=on_complete))
            return True
        except queue.Full:
            logger.warning("TTS 队列已满，无法安排本地模型预热")
            return False

    def _notify_status(self, status):
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
        turn_id=None,
    ):
        if self._stop_event.is_set() or not prepare_spoken_text(text):
            return False
        try:
            self._jobs.put_nowait(
                SpeechJob(
                    text=text,
                    mood=mood,
                    emotion_strength=emotion_strength,
                    modifier=modifier,
                    fatigue_strength=fatigue_strength,
                    voice_style=voice_style,
                    voice_style_strength=voice_style_strength,
                    turn_id=turn_id,
                )
            )
            return True
        except queue.Full:
            logger.warning("TTS 队列已满，本条语音已跳过")
            return False

    def _signal_stop(self):
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            pass
        for client in (self.client, getattr(self, "fallback_client", None)):
            cancel = getattr(client, "cancel", None)
            if callable(cancel):
                cancel()
                continue
            close = getattr(client, "close", None)
            if callable(close):
                close()

    def shutdown(self):
        self.on_audio_ready = lambda _audio: None
        self.on_error = lambda _message: None
        self.on_status = lambda _status: None
        self._signal_stop()
        task_handle = getattr(self, "_task_handle", None)
        if task_handle is not None:
            task_handle.cancel()
            task_handle.join(timeout=2.0)
        else:
            thread = getattr(self, "_thread", None)
            if thread is not None:
                thread.join(timeout=2.0)
        if getattr(self, "_owns_task_supervisor", False):
            self.task_supervisor.shutdown(timeout=2.0)

    def _is_turn_current(self, turn_id):
        if turn_id is None:
            return True
        checker = getattr(self, "_turn_checker", None)
        return True if not callable(checker) else bool(checker(turn_id))

    def _track_speech_task(self, turn_id):
        supervisor = getattr(self, "task_supervisor", None)
        if supervisor is None:
            return nullcontext(None)
        return supervisor.track(
            "speech-synthesis",
            turn_id=turn_id,
            scope="speech",
        )

    def _run(self, task_token=None):
        while not self._stop_event.is_set() and (
            task_token is None or not task_token.cancelled
        ):
            job = self._jobs.get()
            if job is None:
                return
            if isinstance(job, WarmupJob):
                self._run_warmup(job)
                continue
            speech_job = SpeechJob.from_legacy(job)
            turn_id = speech_job.turn_id
            if not self._is_turn_current(turn_id):
                logger.info("已跳过过时语音任务 turn_id=%s", turn_id)
                continue
            text = speech_job.text
            mood = speech_job.mood
            emotion_strength = speech_job.emotion_strength
            modifier = speech_job.modifier
            fatigue_strength = speech_job.fatigue_strength
            voice_style = speech_job.voice_style
            voice_style_strength = speech_job.voice_style_strength
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
                        with self._track_speech_task(turn_id) as speech_token:
                            audio_batch = self._synthesize_sentences_with_recovery(
                                client,
                                sentences,
                                speaker_id,
                                mood,
                                voice_style=voice_style,
                                speed_multiplier=speed_multiplier,
                                turn_id=turn_id,
                            )
                            if (
                                speech_token is not None
                                and not speech_token.is_current()
                            ):
                                raise _StaleSpeechTurn(turn_id)
                        if client_index:
                            logger.warning(
                                "Mio 本地语音不可用，本条回复已完整回退到 AivisSpeech"
                            )
                        break
                    except Exception as exc:
                        if isinstance(exc, _StaleSpeechTurn):
                            raise
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

                combined_audio = combine_speech_audio(audio_batch)
                if (
                    combined_audio is not None
                    and not self._stop_event.is_set()
                    and self._is_turn_current(turn_id)
                ):
                    self._notify_status("ready")
                    self.on_audio_ready(combined_audio)
                elif combined_audio is not None:
                    logger.info("语音合成完成但轮次已过时，已丢弃 turn_id=%s", turn_id)
            except Exception as exc:
                if isinstance(exc, _StaleSpeechTurn):
                    logger.info("语音轮次已过时，已静默丢弃 turn_id=%s", turn_id)
                    continue
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
            if not self._stop_event.is_set() and callable(job.on_complete):
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
        turn_id=None,
    ):
        """完整合成所有片段；任一失败时由调用方整条回退或取消。"""
        audio_batch = []
        for sentence in sentences:
            if self._stop_event.is_set():
                raise AivisSpeechError("TTS service is shutting down")
            if not self._is_turn_current(turn_id):
                raise _StaleSpeechTurn(turn_id)
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
                    turn_id=turn_id,
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
        turn_id=None,
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
                    turn_id=turn_id,
                )
            except Exception as exc:
                if isinstance(exc, _StaleSpeechTurn):
                    raise
                if _is_non_retryable_tts_error(exc):
                    raise
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

    _effective_mood = staticmethod(effective_mood)
    _effective_voice_style = staticmethod(effective_voice_style)
    _emotion_speed_multiplier = staticmethod(emotion_speed_multiplier)


__all__ = [
    "AivisSpeechClient",
    "AivisSpeechError",
    "DEFAULT_MIO_GPT_SOVITS_REFERENCES",
    "DEFAULT_MIO_GPT_SOVITS_WORKER",
    "DEFAULT_MIO_TTS_WORKER",
    "JapaneseSpeechTranslator",
    "MioGPTSoVITSClient",
    "MioGPTSoVITSError",
    "MioStyleBertClient",
    "MioStyleBertError",
    "SpeechSynthesisService",
    "build_mouth_envelope",
    "combine_speech_audio",
    "contains_japanese_kana",
    "prepare_spoken_text",
    "split_sentences",
]
