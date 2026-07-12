"""运行时数据和 AI JSON 的统一规范化函数。

项目暂时不引入额外数据模型框架，以保持控制台核心依赖轻量。
所有函数都返回新的普通 dict/list，方便直接写入 JSON。
"""

import json
import math


ALLOWED_INTENTS = {"chat", "get_profile", "set_profile", "emotion_query"}
ALLOWED_PROFILE_ACTIONS = {"add_like", "add_dislike", "set_name", "set_nickname", "none"}
ALLOWED_MOODS = {"neutral", "happy", "shy", "sad", "tired"}
ALLOWED_EVENT_EMOTIONS = {"neutral", "happy", "curious", "sad", "touched", "worried"}
ALLOWED_EVENT_IMPACTS = {"increase_bond", "increase_affinity", "none", "positive", "negative", "talk"}
ALLOWED_MESSAGE_ROLES = {"user", "assistant"}


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
            "impact": "none",
            "importance": 0.0,
        }

    emotion = _clean_string(value.get("emotion"), "neutral")
    if emotion not in ALLOWED_EVENT_EMOTIONS:
        emotion = "neutral"
    impact = _clean_string(value.get("impact"), "none")
    if impact not in ALLOWED_EVENT_IMPACTS:
        impact = "none"
    importance = _number(value.get("importance"), 0.3, 0.0, 1.0)
    return {
        "is_event": True,
        "event": event_text,
        "emotion": emotion,
        "impact": impact,
        "importance": importance,
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
    return {
        "name": name,
        "nickname": nickname,
        "names": names,
        "nicknames": nicknames,
        "likes": _string_list(value.get("likes")),
        "dislikes": _string_list(value.get("dislikes")),
    }


def normalize_emotion(value):
    value = value if isinstance(value, dict) else {}
    mood = _clean_string(value.get("mood"), "neutral")
    if mood not in ALLOWED_MOODS:
        mood = "neutral"
    return {
        "mood": mood,
        "energy": _number(value.get("energy"), 80, 0.0, 100.0),
        "last_updated": value.get("last_updated") if isinstance(value.get("last_updated"), str) else None,
        "mood_set_at": value.get("mood_set_at") if isinstance(value.get("mood_set_at"), str) else None,
    }


def normalize_relationship(value):
    value = value if isinstance(value, dict) else {}
    return {
        "affection": _number(value.get("affection"), 30, 0.0, 100.0),
        "trust": _number(value.get("trust"), 30, 0.0, 100.0),
        "familiarity": _number(value.get("familiarity"), 10, 0.0, 100.0),
    }


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

    event_id = _clean_string(value.get("id"))
    event_text = _clean_string(value.get("event"))
    emotion = _clean_string(value.get("emotion"), "neutral")
    if emotion not in ALLOWED_EVENT_EMOTIONS:
        emotion = "neutral"
    impact = _clean_string(value.get("impact"), "none")
    if impact not in ALLOWED_EVENT_IMPACTS:
        impact = "none"

    embedding = value.get("embedding")
    if not isinstance(embedding, list) or not all(
        isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item)
        for item in embedding
    ):
        embedding = None

    return {
        "id": event_id,
        "event": event_text,
        "emotion": emotion,
        "impact": impact,
        "importance": _number(value.get("importance"), 0.3, 0.0, 1.0),
        "notified": _boolean(value.get("notified"), False),
        "created_at": value.get("created_at") if isinstance(value.get("created_at"), str) else None,
        "embedding": embedding,
    }


def normalize_app_config(value, defaults):
    value = value if isinstance(value, dict) else {}
    result = {**defaults, **value}

    for key in ("api_key", "model", "assistant_name", "base_url", "live2d_model_path"):
        result[key] = _clean_string(result.get(key), _clean_string(defaults.get(key)))

    result["live2d_expression_intensity"] = _number(
        result.get("live2d_expression_intensity"), defaults["live2d_expression_intensity"], 0.0, 10.0
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
