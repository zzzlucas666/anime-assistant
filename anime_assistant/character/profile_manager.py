"""Stable user profile built from provenance-aware facts.

Legacy top-level fields remain materialized for the rest of the application.  The
``facts`` list is the source of truth for updates, corrections, and audit history.
"""

import datetime
import uuid

from anime_assistant.infrastructure.storage import safe_load_json, safe_save_json
from anime_assistant.infrastructure.paths import DATA_DIR
from anime_assistant.infrastructure.models import (
    MEMORY_SCHEMA_VERSION,
    normalize_profile,
    normalize_profile_fact,
)

PROFILE_PATH = str(DATA_DIR / "user_profile.json")

ACTION_CATEGORIES = {
    "set_name": "identity.name",
    "set_nickname": "identity.nickname",
    "add_like": "preference.like",
    "remove_like": "preference.like",
    "add_dislike": "preference.dislike",
    "remove_dislike": "preference.dislike",
}
SINGLETON_CATEGORIES = {"identity.name", "identity.nickname"}
OPPOSITE_CATEGORIES = {
    "preference.like": "preference.dislike",
    "preference.dislike": "preference.like",
}
ACTIVE_FACT_STATUSES = {"confirmed", "legacy"}
TRUSTED_PROFILE_SOURCES = {"user_explicit", "user_corrected", "system_observed", "legacy_import"}
SOURCE_PRIORITY = {
    "ai_inferred": 0,
    "legacy_import": 1,
    "system_observed": 2,
    "user_explicit": 3,
    "user_corrected": 4,
}


def _now_iso(now=None):
    value = (
        now
        if isinstance(now, datetime.datetime)
        else datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    )
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value.isoformat(timespec="seconds")


def _value_key(value):
    return " ".join(str(value or "").strip().casefold().split())


def _fact_is_active(fact):
    if fact.get("status") not in ACTIVE_FACT_STATUSES:
        return False
    if fact.get("source") in {"user_explicit", "user_corrected"}:
        return any(
            isinstance(item, str) and item.strip()
            for item in fact.get("evidence", [])
        )
    return fact.get("source") in TRUSTED_PROFILE_SOURCES


def _fact_is_auditable(fact):
    if fact.get("source") not in TRUSTED_PROFILE_SOURCES:
        return False
    if fact.get("source") in {"user_explicit", "user_corrected"}:
        return bool(fact.get("evidence"))
    return fact.get("status") != "candidate"


def default_profile():
    return {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "name": "",
        "nickname": "",
        "names": [],
        "nicknames": [],
        "likes": [],
        "dislikes": [],
        "facts": [],
    }


def is_valid_memory(text):
    invalid_words = ["什么", "吗", "呢", "呀", "啊", "啥", "?", "？"]
    return isinstance(text, str) and len(text.strip()) >= 2 and not any(
        word in text for word in invalid_words
    )


def _new_fact(category, value, source, confidence, evidence, now=None, status="confirmed"):
    timestamp = _now_iso(now)
    return {
        "id": uuid.uuid4().hex,
        "category": category,
        "value": value.strip(),
        "status": status,
        "source": source,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "created_at": timestamp,
        "updated_at": timestamp,
        "supersedes": None,
        "evidence": [item.strip() for item in (evidence or []) if isinstance(item, str) and item.strip()],
    }


def _seed_legacy_facts(profile, now=None):
    if profile.get("facts"):
        return profile
    facts = []
    seen = set()

    def add(category, value):
        key = (category, _value_key(value))
        if not key[1] or key in seen:
            return
        seen.add(key)
        facts.append(_new_fact(category, value, "legacy_import", 0.6, [], now, status="legacy"))

    for value in profile.get("names", []):
        add("identity.name", value)
    add("identity.name", profile.get("name"))
    for value in profile.get("nicknames", []):
        add("identity.nickname", value)
    add("identity.nickname", profile.get("nickname"))
    for value in profile.get("likes", []):
        add("preference.like", value)
    for value in profile.get("dislikes", []):
        add("preference.dislike", value)
    profile["facts"] = facts
    return profile


def materialize_profile(profile):
    normalized = normalize_profile(profile)
    _seed_legacy_facts(normalized)
    facts = normalized["facts"]
    active = [fact for fact in facts if _fact_is_active(fact)]

    def latest(category):
        matches = [
            (index, fact)
            for index, fact in enumerate(active)
            if fact.get("category") == category
        ]
        if not matches:
            return ""
        _, winner = max(
            matches,
            key=lambda pair: (
                SOURCE_PRIORITY.get(pair[1].get("source"), 0),
                float(pair[1].get("confidence", 0.0) or 0.0),
                pair[1].get("updated_at") or pair[1].get("created_at") or "",
                pair[0],
            ),
        )
        return winner["value"]

    normalized["name"] = latest("identity.name")
    normalized["nickname"] = latest("identity.nickname")
    normalized["names"] = list(dict.fromkeys(
        [
            fact["value"] for fact in facts
            if fact.get("category") == "identity.name" and _fact_is_auditable(fact)
        ]
        + ([normalized["name"]] if normalized["name"] else [])
    ))
    normalized["nicknames"] = list(dict.fromkeys(
        [
            fact["value"] for fact in facts
            if fact.get("category") == "identity.nickname" and _fact_is_auditable(fact)
        ]
        + ([normalized["nickname"]] if normalized["nickname"] else [])
    ))
    preference_winners = {}
    for index, fact in enumerate(active):
        if fact.get("category") not in {"preference.like", "preference.dislike"}:
            continue
        key = _value_key(fact.get("value"))
        rank = (
            SOURCE_PRIORITY.get(fact.get("source"), 0),
            float(fact.get("confidence", 0.0) or 0.0),
            fact.get("updated_at") or fact.get("created_at") or "",
            index,
        )
        if key not in preference_winners or rank > preference_winners[key][0]:
            preference_winners[key] = (rank, fact)
    normalized["likes"] = list(dict.fromkeys(
        fact["value"] for _, fact in preference_winners.values()
        if fact.get("category") == "preference.like"
    ))
    normalized["dislikes"] = list(dict.fromkeys(
        fact["value"] for _, fact in preference_winners.values()
        if fact.get("category") == "preference.dislike"
    ))
    profile.clear()
    profile.update(normalized)
    return profile


def _supersede(fact, replacement_id, now=None, status="superseded"):
    fact["status"] = status
    fact["updated_at"] = _now_iso(now)
    fact["superseded_by"] = replacement_id


def apply_profile_action(
    profile,
    action,
    value,
    *,
    source="user_explicit",
    confidence=1.0,
    evidence=None,
    now=None,
):
    """Apply a trusted profile update and preserve any displaced facts."""
    category = ACTION_CATEGORIES.get(action)
    value = str(value or "").strip()
    if not category or not is_valid_memory(value) or source not in TRUSTED_PROFILE_SOURCES:
        return False
    if source in {"user_explicit", "user_corrected"} and not any(
        isinstance(item, str) and item.strip() for item in (evidence or [])
    ):
        return False

    materialize_profile(profile)
    facts = profile["facts"]
    active = [fact for fact in facts if _fact_is_active(fact)]
    target_key = _value_key(value)

    if action.startswith("remove_"):
        changed = False
        for fact in active:
            if fact.get("category") == category and _value_key(fact.get("value")) == target_key:
                _supersede(fact, None, now, status="retracted")
                changed = True
        if changed:
            materialize_profile(profile)
        return changed

    for fact in active:
        if fact.get("category") == category and _value_key(fact.get("value")) == target_key:
            if SOURCE_PRIORITY.get(source, 0) >= SOURCE_PRIORITY.get(fact.get("source"), 0):
                before = dict(fact)
                fact["source"] = source
                fact["confidence"] = max(float(fact.get("confidence", 0.0)), float(confidence))
                fact["updated_at"] = _now_iso(now)
                fact["evidence"] = list(dict.fromkeys((fact.get("evidence") or []) + (evidence or [])))
                materialize_profile(profile)
                return fact != before
            return False

    new_fact = _new_fact(category, value, source, confidence, evidence, now)
    displaced = []
    for fact in active:
        same_singleton = category in SINGLETON_CATEGORIES and fact.get("category") == category
        opposite_preference = (
            fact.get("category") == OPPOSITE_CATEGORIES.get(category)
            and _value_key(fact.get("value")) == target_key
        )
        if same_singleton or opposite_preference:
            displaced.append(fact)
    if displaced:
        new_fact["supersedes"] = displaced[-1].get("id")
        for fact in displaced:
            _supersede(fact, new_fact["id"], now)
    facts.append(new_fact)
    materialize_profile(profile)
    return True


def merge_profile_facts(profile, incoming_facts, now=None):
    """Merge records by source priority while retaining losing conflicts for audit."""
    materialize_profile(profile)
    changed = False
    for raw_fact in incoming_facts or []:
        fact = normalize_profile_fact(raw_fact)
        if fact is None or fact["status"] not in ACTIVE_FACT_STATUSES:
            continue
        source = fact.get("source")
        if source not in TRUSTED_PROFILE_SOURCES:
            continue
        action = {
            "identity.name": "set_name",
            "identity.nickname": "set_nickname",
            "preference.like": "add_like",
            "preference.dislike": "add_dislike",
        }[fact["category"]]

        current = [
            item for item in profile.get("facts", [])
            if _fact_is_active(item)
            and (
                item.get("category") == fact["category"]
                if fact["category"] in SINGLETON_CATEGORIES
                else _value_key(item.get("value")) == _value_key(fact["value"])
            )
        ]
        if current and max(SOURCE_PRIORITY.get(item.get("source"), 0) for item in current) > SOURCE_PRIORITY.get(source, 0):
            continue
        changed = apply_profile_action(
            profile,
            action,
            fact["value"],
            source=source,
            confidence=fact["confidence"],
            evidence=fact["evidence"],
            now=now,
        ) or changed
    return changed


def update_profile(profile, user_message):
    """Compatibility parser for simple explicit statements."""
    rules = (
        ("你可以叫我", "set_nickname"),
        ("我叫", "set_name"),
        ("我不再喜欢", "remove_like"),
        ("我喜欢", "add_like"),
        ("我不再讨厌", "remove_dislike"),
        ("我讨厌", "add_dislike"),
    )
    for prefix, action in rules:
        if user_message.startswith(prefix):
            value = user_message[len(prefix):].strip()
            apply_profile_action(profile, action, value, evidence=[user_message])
            break
    return profile


def load_profile():
    raw_profile = safe_load_json(PROFILE_PATH, default_profile)
    profile = normalize_profile(raw_profile)
    _seed_legacy_facts(profile)
    materialize_profile(profile)
    if profile != raw_profile:
        safe_save_json(PROFILE_PATH, profile)
    return profile


def save_profile(profile):
    materialize_profile(profile)
    return safe_save_json(PROFILE_PATH, profile)
