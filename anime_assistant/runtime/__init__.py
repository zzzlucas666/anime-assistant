"""Application lifecycle, supervised tasks, and conversation turn identity."""

from anime_assistant.runtime.supervisor import (
    TaskHandle,
    TaskSnapshot,
    TaskSupervisor,
    TaskToken,
)
from anime_assistant.runtime.turns import TurnContext, TurnCoordinator

__all__ = [
    "ApplicationRuntime",
    "RuntimeMessage",
    "TaskHandle",
    "TaskSnapshot",
    "TaskSupervisor",
    "TaskToken",
    "TurnContext",
    "TurnCoordinator",
]


def __getattr__(name):
    """Load the application facade lazily to avoid speech/runtime import cycles."""
    if name in {"ApplicationRuntime", "RuntimeMessage"}:
        from anime_assistant.runtime.application import ApplicationRuntime, RuntimeMessage

        return {
            "ApplicationRuntime": ApplicationRuntime,
            "RuntimeMessage": RuntimeMessage,
        }[name]
    raise AttributeError(name)
