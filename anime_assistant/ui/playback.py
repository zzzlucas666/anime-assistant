"""Sequential in-memory speech playback for the desktop interface."""

from collections import deque

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from anime_assistant.infrastructure.logging import get_logger
from anime_assistant.speech.audio import SpeechAudio


logger = get_logger(__name__)


class SpeechPlaybackController(QObject):
    """Play WAV responses in order and drive the Live2D mouth envelope."""

    def __init__(self, character_controller, parent=None):
        super().__init__(parent)
        self.character_controller = character_controller
        self.audio_output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_player_error)
        self._queue = deque()
        self._current = None
        self._buffer = None
        self._transition_pending = False

    def enqueue(self, audio):
        if not isinstance(audio, SpeechAudio) or not audio.wav_data:
            return
        self._queue.append(audio)
        if self._current is None:
            self._play_next()

    def stop(self):
        self._queue.clear()
        self._transition_pending = False
        self.player.stop()
        self.player.setSource(QUrl())
        self._release_current()
        self.character_controller.on_audio_finished()

    def _play_next(self):
        self._transition_pending = False
        if self._buffer is not None:
            self.player.setSource(QUrl())
        self._release_current()
        if not self._queue:
            self.character_controller.on_audio_finished()
            return

        self._current = self._queue.popleft()
        self._buffer = QBuffer(self)
        self._buffer.setData(QByteArray(self._current.wav_data))
        self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.character_controller.on_audio_started()
        self.player.setSourceDevice(self._buffer, QUrl())
        self.player.play()

    def _on_position_changed(self, position_ms):
        if self._current is None or not self._current.mouth_envelope:
            return
        index = int(position_ms // self._current.envelope_window_ms)
        index = max(0, min(index, len(self._current.mouth_envelope) - 1))
        self.character_controller.on_audio_amplitude(
            self._current.mouth_envelope[index]
        )

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._schedule_play_next()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            logger.warning("Qt 无法播放 TTS 返回的音频，已跳过当前句")
            self._schedule_play_next()

    def _schedule_play_next(self):
        if self._transition_pending:
            return
        self._transition_pending = True
        QTimer.singleShot(0, self._play_next)

    def _on_player_error(self, _error, error_string):
        if error_string:
            logger.warning("TTS 音频播放失败：%s", error_string)

    def _release_current(self):
        self._current = None
        if self._buffer is not None:
            self._buffer.close()
            self._buffer.deleteLater()
            self._buffer = None
