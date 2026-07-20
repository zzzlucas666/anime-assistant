"""Trust, lifecycle, and rendering rules for persisted memories."""

import datetime
import re


TRUSTED_FACT_SOURCES = {"user_explicit", "user_corrected", "system_observed"}
RETRIEVABLE_STATUSES = {"confirmed", "legacy"}
STATE_MUTATING_STATUSES = {"confirmed"}

DEFAULT_TTL_DAYS = {
    "temporary_context": 1,
    "emotional_episode": 7,
    "plan": 30,
}


def _as_naive_utc(value):
    if isinstance(value, datetime.datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return parsed


def utc_now_iso(now=None):
    current = _as_naive_utc(now) or datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    return current.isoformat(timespec="seconds")


def _normalized_evidence_text(value):
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(value or "").casefold())


def evidence_is_grounded(evidence, user_message):
    """Only an exact, meaningful span of the user's message counts as evidence."""
    evidence_text = _normalized_evidence_text(evidence)
    user_text = _normalized_evidence_text(user_message)
    return len(evidence_text) >= 2 and evidence_text in user_text


def default_expiry(memory_type, created_at=None, now=None):
    ttl_days = DEFAULT_TTL_DAYS.get(memory_type)
    if ttl_days is None:
        return None
    base = (
        _as_naive_utc(created_at)
        or _as_naive_utc(now)
        or datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    )
    return (base + datetime.timedelta(days=ttl_days)).isoformat(timespec="seconds")


def expiry_is_due(expires_at, now=None):
    expiry = _as_naive_utc(expires_at)
    if expiry is None:
        return False
    current = _as_naive_utc(now) or datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    return expiry <= current


def apply_lifecycle_defaults(record, now=None):
    """Return a copy with type-specific expiry and any due status applied."""
    result = dict(record or {})
    if not result.get("expires_at"):
        if result.get("status") == "candidate":
            base = _as_naive_utc(result.get("created_at")) or _as_naive_utc(now)
            base = base or datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            result["expires_at"] = (base + datetime.timedelta(days=7)).isoformat(timespec="seconds")
        else:
            result["expires_at"] = default_expiry(
                result.get("type", "general"), result.get("created_at"), now
            )
    if (
        result.get("status") not in {"superseded", "retracted", "expired"}
        and expiry_is_due(result.get("expires_at"), now)
    ):
        result["status"] = "expired"
        result["updated_at"] = utc_now_iso(now)
    return result


def build_provenance(extraction, user_message, now=None):
    """Convert an AI extraction claim into locally enforced provenance fields."""
    extraction = extraction if isinstance(extraction, dict) else {}
    requested_source = extraction.get("source")
    evidence = str(extraction.get("evidence") or "").strip()
    grounded = (
        requested_source in {"user_explicit", "user_corrected"}
        and evidence_is_grounded(evidence, user_message)
    )
    if grounded:
        source = requested_source
        status = "confirmed"
        confidence = max(0.5, min(1.0, float(extraction.get("confidence", 0.8) or 0.8)))
        evidence_list = [evidence]
    else:
        source = "ai_inferred"
        status = "candidate"
        confidence = min(0.35, max(0.0, float(extraction.get("confidence", 0.0) or 0.0)))
        evidence_list = []

    created_at = utc_now_iso(now)
    memory_type = extraction.get("type", "general")
    if status == "candidate":
        base = _as_naive_utc(created_at)
        expires_at = (base + datetime.timedelta(days=7)).isoformat(timespec="seconds")
    else:
        requested_expiry = extraction.get("expires_at")
        expires_at = (
            requested_expiry
            if _as_naive_utc(requested_expiry) is not None
            else default_expiry(memory_type, created_at, now)
        )
    return {
        "source": source,
        "status": status,
        "confidence": confidence,
        "evidence": evidence_list,
        "created_at": created_at,
        "updated_at": created_at,
        "expires_at": expires_at,
    }


def is_event_retrievable(event, now=None):
    event = apply_lifecycle_defaults(event, now)
    has_required_evidence = (
        event.get("source") not in {"user_explicit", "user_corrected"}
        or any(isinstance(item, str) and item.strip() for item in event.get("evidence", []))
    )
    return (
        event.get("status") in RETRIEVABLE_STATUSES
        and event.get("source") in TRUSTED_FACT_SOURCES | {"legacy_import"}
        and has_required_evidence
    )


def memory_trust_tier(event, now=None):
    """Return the prompt-facing trust tier for a retrievable event.

    Only facts explicitly stated or corrected by the user are rendered as
    high-trust. System observations and migrated legacy records remain useful
    background, but are labelled medium-trust so the model does not present
    them with false certainty. Candidate/inferred records return ``None``.
    """
    event = apply_lifecycle_defaults(event, now)
    if not is_event_retrievable(event, now):
        return None
    if (
        event.get("status") == "confirmed"
        and event.get("source") in {"user_explicit", "user_corrected"}
    ):
        return "high"
    return "medium"


def can_event_affect_state(event, now=None):
    event = apply_lifecycle_defaults(event, now)
    has_required_evidence = (
        event.get("source") not in {"user_explicit", "user_corrected"}
        or any(isinstance(item, str) and item.strip() for item in event.get("evidence", []))
    )
    return (
        event.get("status") in STATE_MUTATING_STATUSES
        and event.get("source") in TRUSTED_FACT_SOURCES
        and has_required_evidence
    )


def event_context_text(event):
    """Prefer verified source evidence over an AI-authored paraphrase."""
    event = event if isinstance(event, dict) else {}
    evidence = event.get("evidence")
    if event.get("source") in TRUSTED_FACT_SOURCES and isinstance(evidence, list):
        grounded = next((item.strip() for item in evidence if isinstance(item, str) and item.strip()), "")
        if grounded:
            return f"对方曾明确说：{grounded}"
    return str(event.get("event") or "").strip()
