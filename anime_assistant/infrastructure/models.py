"""运行时数据和 AI JSON 的统一规范化函数。

项目暂时不引入额外数据模型框架，以保持控制台核心依赖轻量。
所有函数都返回新的普通 dict/list，方便直接写入 JSON。
"""

import json
import math


ALLOWED_INTENTS = {"chat", "get_profile", "set_profile", "emotion_query"}
ALLOWED_MOODS = {"neutral", "happy", "shy", "sad", "tired"}
ALLOWED_EVENT_EMOTIONS = {"neutral", "happy", "shy", "curious", "sad", "touched", "worried"}
ALLOWED_USER_EMOTIONS = {
    "neutral", "happy", "sad", "anxious", "angry", "embarrassed",
    "lonely", "bored", "stressed", "tired", "disappointed",
}
ALLOWED_EMOTION_MODIFIERS = {"none", "worried", "touched", "curious", "surprised", "annoyed"}
ALLOWED_VOICE_STYLES = {
    "conversational", "thoughtful", "warm", "cheerful", "excited",
    "bashful", "embarrassed", "concerned", "reassuring", "curious",
    "surprised", "mild_annoyed", "serious", "disappointed", "tired",
}
ALLOWED_EVENT_IMPACTS = {"increase_bond", "increase_affinity", "none", "positive", "negative", "talk"}
ALLOWED_MESSAGE_ROLES = {"user", "assistant"}
MEMORY_SCHEMA_VERSION = 2
ALLOWED_MEMORY_TYPES = {
    "general", "identity", "preference", "plan", "emotional_episode",
    "relationship_moment", "temporary_context",
}
ALLOWED_MEMORY_STATUSES = {
    "candidate", "confirmed", "legacy", "superseded", "expired", "retracted",
}
ALLOWED_MEMORY_SOURCES = {
    "user_explicit", "user_corrected", "system_observed", "ai_inferred", "legacy_import",
}
ALLOWED_PROFILE_ACTIONS = {
    "add_like", "remove_like", "add_dislike", "remove_dislike",
    "set_name", "set_nickname", "none",
}
ALLOWED_PROFILE_FACT_CATEGORIES = {
    "identity.name", "identity.nickname", "preference.like", "preference.dislike",
}


def _clean_string(value, default=""):
    return value.strip() if isinstance(value, str) else default


def _number(value, default, minimum=None, maximum=None):
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def _integer(value, default, minimum=None, maximum=None):
    number = _number(value, default, minimum, maximum)
    return int(number)


def _boolean(value, default=False):
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True"):
        return True
    if value in (0, "0", "false", "False"):
        return False
    return default


def _string_list(value):
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        cleaned = _clean_string(item)
        if cleaned and cleaned not in seen:
            result.append(cleaned)
            seen.add(cleaned)
    return result


def parse_json_object(content):
    """从 AI 返回内容中解析 JSON 对象，兼容误加的 Markdown 代码栏或简短前后缀。"""
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        return None

    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start:end + 1])
        except (TypeError, json.JSONDecodeError):
            return None

    return parsed if isinstance(parsed, dict) else None


def normalize_intent_result(value, fallback_confidence=0.0):
    value = value if isinstance(value, dict) else {}
    intent = _clean_string(value.get("intent"))
    if intent not in ALLOWED_INTENTS:
        intent = "chat"
        confidence = fallback_confidence
    else:
        confidence = _number(value.get("confidence"), fallback_confidence, 0.0, 1.0)
    slots = value.get("slots")
    return {
        "intent": intent,
        "confidence": confidence,
        "slots": slots if isinstance(slots, dict) else {},
    }


def normalize_profile_extraction(value):
    value = value if isinstance(value, dict) else {}
    action = _clean_string(value.get("action"))
    if action not in ALLOWED_PROFILE_ACTIONS:
        action = "none"
    extracted_value = _clean_string(value.get("value"))
    if action == "none" or not extracted_value:
        return {"action": "none", "value": ""}
    return {"action": action, "value": extracted_value}


def normalize_event_extraction(value):
    value = value if isinstance(value, dict) else {}
    is_event = _boolean(value.get("is_event"), False)
    event_text = _clean_string(value.get("event"))
    if not is_event or not event_text:
        return {
            "is_event": False,
            "event": "",
            "emotion": "neutral",
            "user_emotion": "neutral",
            "impact": "none",
            "importance": 0.0,
            "type": "general",
            "source": "ai_inferred",
            "evidence": "",
            "confidence": 0.0,
            "expires_at": None,
        }

    emotion = _clean_string(value.get("emotion"), "neutral")
    if emotion not in ALLOWED_EVENT_EMOTIONS:
        emotion = "neutral"
    user_emotion = _clean_string(value.get("user_emotion"), "neutral")
    if user_emotion not in ALLOWED_USER_EMOTIONS:
        user_emotion = "neutral"
    impact = _clean_string(value.get("impact"), "none")
    if impact not in ALLOWED_EVENT_IMPACTS:
        impact = "none"
    importance = _number(value.get("importance"), 0.3, 0.0, 1.0)
    memory_type = _clean_string(value.get("type"), "general")
    if memory_type not in ALLOWED_MEMORY_TYPES:
        memory_type = "general"
    source = _clean_string(value.get("source"), "ai_inferred")
    if source not in {"user_explicit", "user_corrected", "ai_inferred"}:
        source = "ai_inferred"
    evidence = _clean_string(value.get("evidence"))
    confidence = _number(value.get("confidence"), 0.0, 0.0, 1.0)
    expires_at = value.get("expires_at") if isinstance(value.get("expires_at"), str) else None
    return {
        "is_event": True,
        "event": event_text,
        "emotion": emotion,
        "user_emotion": user_emotion,
        "impact": impact,
        "importance": importance,
        "type": memory_type,
        "source": source,
        "evidence": evidence,
        "confidence": confidence,
        "expires_at": expires_at,
    }


def normalize_profile_fact(value):
    if not isinstance(value, dict):
        return None
    category = _clean_string(value.get("category"))
    fact_value = _clean_string(value.get("value"))
    if category not in ALLOWED_PROFILE_FACT_CATEGORIES or not fact_value:
        return None
    status = _clean_string(value.get("status"), "candidate")
    if status not in ALLOWED_MEMORY_STATUSES:
        status = "candidate"
    source = _clean_string(value.get("source"), "ai_inferred")
    if source not in ALLOWED_MEMORY_SOURCES:
        source = "ai_inferred"
    return {
        "id": _clean_string(value.get("id")),
        "category": category,
        "value": fact_value,
        "status": status,
        "source": source,
        "confidence": _number(value.get("confidence"), 0.0, 0.0, 1.0),
        "created_at": value.get("created_at") if isinstance(value.get("created_at"), str) else None,
        "updated_at": value.get("updated_at") if isinstance(value.get("updated_at"), str) else None,
        "supersedes": _clean_string(value.get("supersedes")) or None,
        "superseded_by": _clean_string(value.get("superseded_by")) or None,
        "evidence": _string_list(value.get("evidence")),
    }


def normalize_profile(value):
    value = value if isinstance(value, dict) else {}
    name = _clean_string(value.get("name"))
    nickname = _clean_string(value.get("nickname"))
    names = _string_list(value.get("names"))
    nicknames = _string_list(value.get("nicknames"))
    if name and name not in names:
        names.append(name)
    if nickname and nickname not in nicknames:
        nicknames.append(nickname)
    facts = []
    seen_fact_ids = set()
    for raw_fact in value.get("facts", []) if isinstance(value.get("facts"), list) else []:
        fact = normalize_profile_fact(raw_fact)
        if fact is None:
            continue
        if not fact["id"] or fact["id"] in seen_fact_ids:
            continue
        seen_fact_ids.add(fact["id"])
        facts.append(fact)
    return {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "name": name,
        "nickname": nickname,
        "names": names,
        "nicknames": nicknames,
        "likes": _string_list(value.get("likes")),
        "dislikes": _string_list(value.get("dislikes")),
        "facts": facts,
    }


def normalize_emotion(value):
    value = value if isinstance(value, dict) else {}
    mood = _clean_string(value.get("mood"), "neutral")
    if mood not in ALLOWED_MOODS:
        mood = "neutral"
    mood_strength_default = 0.0 if mood == "neutral" else (0.8 if mood == "tired" else 0.7)
    modifier = _clean_string(value.get("modifier"), "none")
    if modifier not in ALLOWED_EMOTION_MODIFIERS:
        modifier = "none"
    user_mood = _clean_string(value.get("user_mood"), "neutral")
    if user_mood not in ALLOWED_USER_EMOTIONS:
        user_mood = "neutral"
    voice_style = _clean_string(value.get("voice_style"), "conversational")
    if voice_style not in ALLOWED_VOICE_STYLES:
        voice_style = "conversational"
    return {
        "mood": mood,
        "energy": _number(value.get("energy"), 80, 0.0, 100.0),
        "last_updated": value.get("last_updated") if isinstance(value.get("last_updated"), str) else None,
        "mood_set_at": value.get("mood_set_at") if isinstance(value.get("mood_set_at"), str) else None,
        "mood_strength": _number(value.get("mood_strength"), mood_strength_default, 0.0, 1.0),
        "mood_turns_remaining": _integer(value.get("mood_turns_remaining"), 0, 0, 20),
        "mood_source": _clean_string(value.get("mood_source"), "legacy"),
        "modifier": modifier,
        "modifier_strength": _number(value.get("modifier_strength"), 0.0, 0.0, 1.0),
        "modifier_turns_remaining": _integer(value.get("modifier_turns_remaining"), 0, 0, 10),
        "voice_style": voice_style,
        "voice_style_strength": _number(
            value.get("voice_style_strength"), 0.4, 0.0, 1.0
        ),
        "user_mood": user_mood,
        "user_mood_strength": _number(value.get("user_mood_strength"), 0.0, 0.0, 1.0),
        "user_mood_set_at": (
            value.get("user_mood_set_at")
            if isinstance(value.get("user_mood_set_at"), str)
            else None
        ),
        "fatigue_strength": _number(value.get("fatigue_strength"), 0.0, 0.0, 1.0),
        "pending_mood": (
            value.get("pending_mood")
            if value.get("pending_mood") in {"happy", "shy", "sad"}
            else None
        ),
        "pending_mood_count": _integer(value.get("pending_mood_count"), 0, 0, 2),
        "pending_mood_expires_at": (
            value.get("pending_mood_expires_at")
            if isinstance(value.get("pending_mood_expires_at"), str)
            else None
        ),
    }


def normalize_relationship(value):
    value = value if isinstance(value, dict) else {}
    normalized = {
        "affection": _number(value.get("affection"), 30, 0.0, 100.0),
        "trust": _number(value.get("trust"), 30, 0.0, 100.0),
        "familiarity": _number(value.get("familiarity"), 10, 0.0, 100.0),
    }
    stage_values = {
        "closeness_stage": {"reserved", "friendly", "close"},
        "openness_stage": {"guarded", "careful", "open"},
        "familiarity_stage": {"new", "acquainted", "familiar"},
    }
    for field, allowed in stage_values.items():
        if value.get(field) in allowed:
            normalized[field] = value[field]
    return normalized


def normalize_messages(value):
    if not isinstance(value, list):
        return []
    messages = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = _clean_string(item.get("role"))
        content = _clean_string(item.get("content"))
        if role in ALLOWED_MESSAGE_ROLES and content:
            messages.append({"role": role, "content": content})
    return messages


def normalize_interaction_state(value):
    value = value if isinstance(value, dict) else {}
    timestamp = value.get("last_interaction_time")
    return {
        "last_interaction_time": timestamp if isinstance(timestamp, str) else None,
    }


def normalize_proactive_state(value):
    value = value if isinstance(value, dict) else {}
    last_time = value.get("last_proactive_time")
    count_date = value.get("count_date")
    return {
        "last_proactive_time": last_time if isinstance(last_time, str) else None,
        "count_today": _integer(value.get("count_today"), 0, 0),
        "count_date": count_date if isinstance(count_date, str) else None,
    }


def normalize_summaries(value):
    if not isinstance(value, list):
        return []
    summaries = []
    for item in value:
        if not isinstance(item, dict):
            continue
        summary_text = _clean_string(item.get("summary"))
        if not summary_text:
            continue
        summaries.append({
            "id": _clean_string(item.get("id")),
            "summary": summary_text,
            "created_at": item.get("created_at") if isinstance(item.get("created_at"), str) else None,
            "covers_message_count": _integer(item.get("covers_message_count"), 0, 0),
        })
    return summaries


def normalize_event_record(value):
    if not isinstance(value, dict):
        return None

    is_legacy = _integer(value.get("schema_version"), 0, 0) < MEMORY_SCHEMA_VERSION
    event_id = _clean_string(value.get("id"))
    event_text = _clean_string(value.get("event"))
    emotion = _clean_string(value.get("emotion"), "neutral")
    if emotion not in ALLOWED_EVENT_EMOTIONS:
        emotion = "neutral"
    user_emotion = _clean_string(value.get("user_emotion"), "neutral")
    if user_emotion not in ALLOWED_USER_EMOTIONS:
        user_emotion = "neutral"
    impact = _clean_string(value.get("impact"), "none")
    if impact not in ALLOWED_EVENT_IMPACTS:
        impact = "none"

    embedding = value.get("embedding")
    if not isinstance(embedding, list) or not all(
        isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item)
        for item in embedding
    ):
        embedding = None

    memory_type = _clean_string(value.get("type"), "general")
    if memory_type not in ALLOWED_MEMORY_TYPES:
        memory_type = "general"
    source = _clean_string(value.get("source"))
    if source not in ALLOWED_MEMORY_SOURCES:
        source = "legacy_import" if is_legacy else "ai_inferred"
    status = _clean_string(value.get("status"))
    if status not in ALLOWED_MEMORY_STATUSES:
        status = "legacy" if is_legacy else "candidate"

    return {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "id": event_id,
        "event": event_text,
        "emotion": emotion,
        "user_emotion": user_emotion,
        "impact": impact,
        "importance": _number(value.get("importance"), 0.3, 0.0, 1.0),
        "notified": _boolean(value.get("notified"), False),
        "created_at": value.get("created_at") if isinstance(value.get("created_at"), str) else None,
        "updated_at": value.get("updated_at") if isinstance(value.get("updated_at"), str) else None,
        "type": memory_type,
        "status": status,
        "source": source,
        "confidence": _number(value.get("confidence"), 0.5 if is_legacy else 0.0, 0.0, 1.0),
        "evidence": _string_list(value.get("evidence")),
        "expires_at": value.get("expires_at") if isinstance(value.get("expires_at"), str) else None,
        "embedding": embedding,
        "embedding_model": _clean_string(value.get("embedding_model")),
        "embedding_version": _clean_string(value.get("embedding_version")),
    }


def normalize_app_config(value, defaults):
    value = value if isinstance(value, dict) else {}
    result = {**defaults, **value}

    for key in (
        "api_key", "model", "assistant_name", "base_url", "live2d_model_path",
        "aivis_endpoint", "tts_backend", "mio_tts_python", "mio_tts_worker",
        "mio_tts_repo", "mio_tts_model", "mio_tts_config",
        "mio_tts_style_vectors", "mio_tts_output_dir", "mio_tts_device",
        "mio_gpt_sovits_python", "mio_gpt_sovits_worker",
        "mio_gpt_sovits_repo", "mio_gpt_sovits_gpt_weights",
        "mio_gpt_sovits_sovits_weights",
    ):
        result[key] = _clean_string(result.get(key), _clean_string(defaults.get(key)))

    if result["tts_backend"] not in {
        "aivis", "mio_style_bert_vits2", "mio_gpt_sovits_v2proplus"
    }:
        result["tts_backend"] = defaults.get("tts_backend", "aivis")

    result["tts_enabled"] = _boolean(
        result.get("tts_enabled"), defaults.get("tts_enabled", False)
    )
    result["tts_fallback_to_aivis"] = _boolean(
        result.get("tts_fallback_to_aivis"),
        defaults.get("tts_fallback_to_aivis", True),
    )
    result["chat_thinking_enabled"] = _boolean(
        result.get("chat_thinking_enabled"),
        defaults.get("chat_thinking_enabled", False),
    )
    result["chat_history_max_messages"] = _integer(
        result.get("chat_history_max_messages"),
        defaults.get("chat_history_max_messages", 8),
        2,
        20,
    )
    result["tts_translate_to_japanese"] = _boolean(
        result.get("tts_translate_to_japanese"),
        defaults.get("tts_translate_to_japanese", True),
    )
    result["tts_speed_scale"] = _number(
        result.get("tts_speed_scale"), defaults.get("tts_speed_scale", 1.0), 0.5, 2.0
    )
    result["tts_volume_scale"] = _number(
        result.get("tts_volume_scale"), defaults.get("tts_volume_scale", 1.0), 0.0, 2.0
    )
    result["aivis_timeout_seconds"] = _number(
        result.get("aivis_timeout_seconds"),
        defaults.get("aivis_timeout_seconds", 60.0),
        1.0,
        120.0,
    )
    result["aivis_max_chars_per_request"] = _integer(
        result.get("aivis_max_chars_per_request"),
        defaults.get("aivis_max_chars_per_request", 56),
        20,
        120,
    )
    result["mio_tts_startup_timeout_seconds"] = _number(
        result.get("mio_tts_startup_timeout_seconds"),
        defaults.get("mio_tts_startup_timeout_seconds", 45.0),
        5.0,
        180.0,
    )
    result["mio_tts_timeout_seconds"] = _number(
        result.get("mio_tts_timeout_seconds"),
        defaults.get("mio_tts_timeout_seconds", 120.0),
        5.0,
        300.0,
    )
    result["mio_tts_sdp_ratio"] = _number(
        result.get("mio_tts_sdp_ratio"),
        defaults.get("mio_tts_sdp_ratio", 0.35),
        0.0,
        1.0,
    )
    result["mio_tts_noise"] = _number(
        result.get("mio_tts_noise"), defaults.get("mio_tts_noise", 0.5), 0.0, 2.0
    )
    result["mio_tts_noise_w"] = _number(
        result.get("mio_tts_noise_w"), defaults.get("mio_tts_noise_w", 0.7), 0.0, 2.0
    )
    result["mio_tts_style_weight"] = _number(
        result.get("mio_tts_style_weight"),
        defaults.get("mio_tts_style_weight", 1.0),
        0.0,
        100.0,
    )
    default_references = defaults.get("mio_gpt_sovits_references", {})
    configured_references = result.get("mio_gpt_sovits_references")
    if not isinstance(configured_references, dict):
        configured_references = {}
    result["mio_gpt_sovits_references"] = {
        mood: {
            "audio": _clean_string(
                (configured_references.get(mood) or {}).get("audio")
                if isinstance(configured_references.get(mood), dict)
                else None,
                reference.get("audio", ""),
            ),
            "prompt": _clean_string(
                (configured_references.get(mood) or {}).get("prompt")
                if isinstance(configured_references.get(mood), dict)
                else None,
                reference.get("prompt", ""),
            ),
        }
        for mood, reference in default_references.items()
        if isinstance(reference, dict)
    }
    default_speakers = defaults.get("aivis_mood_speakers", {})
    configured_speakers = result.get("aivis_mood_speakers")
    if not isinstance(configured_speakers, dict):
        configured_speakers = {}
    result["aivis_mood_speakers"] = {
        mood: _integer(configured_speakers.get(mood), speaker_id, 0)
        for mood, speaker_id in default_speakers.items()
    }

    result["live2d_expression_intensity"] = _number(
        result.get("live2d_expression_intensity"), defaults["live2d_expression_intensity"], 0.0, 10.0
    )
    result["live2d_waiting_motion_intensity"] = _number(
        result.get("live2d_waiting_motion_intensity"),
        defaults.get("live2d_waiting_motion_intensity", 1.0),
        0.0,
        2.0,
    )
    result["live2d_waiting_gaze_intensity"] = _number(
        result.get("live2d_waiting_gaze_intensity"),
        defaults.get("live2d_waiting_gaze_intensity", 1.0),
        0.0,
        2.0,
    )
    result["live2d_waiting_motion_speed"] = _number(
        result.get("live2d_waiting_motion_speed"),
        defaults.get("live2d_waiting_motion_speed", 1.4),
        0.5,
        2.0,
    )
    for key in ("live2d_expression_map", "live2d_motion_map", "live2d_parameter_map"):
        if not isinstance(result.get(key), dict):
            result[key] = defaults[key].copy()

    result["proactive_check_interval_minutes"] = _number(
        result.get("proactive_check_interval_minutes"), defaults["proactive_check_interval_minutes"], 0.1
    )
    result["proactive_idle_threshold_minutes"] = _number(
        result.get("proactive_idle_threshold_minutes"), defaults["proactive_idle_threshold_minutes"], 0.1
    )
    result["proactive_min_interval_minutes"] = _number(
        result.get("proactive_min_interval_minutes"), defaults["proactive_min_interval_minutes"], 0.0
    )
    result["proactive_max_per_day"] = _integer(
        result.get("proactive_max_per_day"), defaults["proactive_max_per_day"], 0, 100
    )
    return result
