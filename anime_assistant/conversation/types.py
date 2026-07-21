"""Typed contracts shared by conversation routing and orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


ProfileStrategy = Literal["none", "local", "deferred_ai"]
RouteSource = Literal["local_rule", "local_chat"]


@dataclass(frozen=True)
class ProfileUpdate:
    """A profile action whose value is directly evidenced by the user text."""

    action: str
    value: str
    confidence: float = 1.0

    def as_result(self) -> dict[str, str]:
        return {"action": self.action, "value": self.value}


@dataclass(frozen=True)
class RouteDecision:
    """Pure local decision for work allowed before the first response token."""

    intent: str = "chat"
    confidence: float = 0.9
    source: RouteSource = "local_chat"
    router_eligible: bool = False
    profile_strategy: ProfileStrategy = "none"
    profile_update: Optional[ProfileUpdate] = None
    reason: str = "ordinary_chat"

    def as_intent_result(self) -> dict[str, object]:
        """Return the legacy intent shape used by older integrations."""
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "slots": {},
        }
