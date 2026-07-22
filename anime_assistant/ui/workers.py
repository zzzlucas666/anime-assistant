"""Qt thread and signal adapters used by the desktop interface."""

from PySide6.QtCore import QObject, QThread, Signal

from anime_assistant.infrastructure.logging import get_logger


logger = get_logger(__name__)


class ChatWorker(QThread):
    """Run one complete conversation turn outside the Qt main thread."""

    chunk_received = Signal(str)
    turn_finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, orchestrator, user_message, turn_id=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.user_message = user_message
        self.turn_id = turn_id

    def run(self):
        try:
            prepared = self.orchestrator.prepare_turn(
                self.user_message,
                turn_id=self.turn_id,
            )
            raw_reply = ""
            for chunk in self.orchestrator.stream_reply(prepared):
                raw_reply += chunk
                self.chunk_received.emit(chunk)
            self.orchestrator.finalize_turn(prepared, raw_reply)
        except Exception as exc:
            logger.error("GUI 对话处理出错：%s", exc)
            self.error_occurred.emit(str(exc))
        finally:
            self.turn_finished.emit()


class ProactiveBridge(QObject):
    """Safely relay initiative-engine events to the Qt main thread."""

    message_received = Signal(str, object)
    state_updated = Signal()
    turn_started = Signal(object)


class SpeechBridge(QObject):
    """Safely relay TTS worker events to the Qt main thread."""

    audio_ready = Signal(object)
    error_occurred = Signal(str)
    status_changed = Signal(str)
