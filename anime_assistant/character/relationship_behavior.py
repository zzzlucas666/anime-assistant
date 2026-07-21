"""Single source of truth for relationship-driven behaviour.

Relationship numbers are deliberately translated into a structured policy first.
Every prompt/rendering path consumes that same policy so thresholds cannot drift.
"""

from anime_assistant.infrastructure.models import normalize_relationship


def _resolve_stage(value, previous, *, low, middle, high):
    """Resolve a three-level stage with five-point exit hysteresis."""
    if previous == high:
        if value >= 65:
            return high
        return middle if value >= 35 else low
    if previous == middle:
        if value >= 70:
            return high
        return low if value < 35 else middle
    if previous == low:
        if value >= 70:
            return high
        return middle if value >= 40 else low
    if value >= 70:
        return high
    if value >= 40:
        return middle
    return low


def build_relationship_policy(relationship, emotion=None):
    relationship = normalize_relationship(relationship)
    emotion = emotion if isinstance(emotion, dict) else {}

    affection = relationship["affection"]
    trust = relationship["trust"]
    familiarity = relationship["familiarity"]

    closeness = _resolve_stage(
        affection,
        relationship.get("closeness_stage"),
        low="reserved",
        middle="friendly",
        high="close",
    )
    openness = _resolve_stage(
        trust,
        relationship.get("openness_stage"),
        low="guarded",
        middle="careful",
        high="open",
    )
    familiarity_level = _resolve_stage(
        familiarity,
        relationship.get("familiarity_stage"),
        low="new",
        middle="acquainted",
        high="familiar",
    )

    mood_expression = {
        "happy": 0.8,
        "shy": 0.4,
        "sad": 0.2,
        "tired": 0.3,
    }.get(emotion.get("mood"), 0.5)

    return {
        "closeness": closeness,
        "openness": openness,
        "familiarity_level": familiarity_level,
        "warmth": affection / 100.0,
        "formality": 1.0 - affection / 100.0,
        "initiative": trust / 100.0,
        "verbosity": familiarity / 100.0,
        "emotion_expression": mood_expression,
    }


def sync_relationship_stages(relationship):
    """Persist the semantic stages used as hysteresis history."""
    if not isinstance(relationship, dict):
        return relationship
    policy = build_relationship_policy(relationship)
    relationship["closeness_stage"] = policy["closeness"]
    relationship["openness_stage"] = policy["openness"]
    relationship["familiarity_stage"] = policy["familiarity_level"]
    return relationship


def build_relationship_hint(relationship):
    policy = build_relationship_policy(relationship)
    hints = []

    hints.append({
        "close": "- 现在对对方很有好感，语气可以更亲近，但不要擅自升级关系。",
        "friendly": "- 对对方有好感，语气自然友好，同时保留一点谨慎。",
        "reserved": "- 目前关系尚浅，语气礼貌温柔，不表现得过分亲密。",
    }[policy["closeness"]])
    hints.append({
        "open": "- 信任感较高，可以适当表达真实想法与感受。",
        "careful": "- 信任感一般，保持真诚，但不要过度坦白敏感内容。",
        "guarded": "- 信任仍在建立，避免过度暴露内心或替对方作判断。",
    }[policy["openness"]])
    hints.append({
        "familiar": "- 已经比较熟悉，可以自然使用昵称并回顾有来源的共同记忆。",
        "acquainted": "- 有一定熟悉度，可以偶尔使用昵称，但不要随意杜撰过去。",
        "new": "- 还不够熟悉，像刚认识不久一样交流，不假装记得不存在的经历。",
    }[policy["familiarity_level"]])
    return "\n".join(hints)


def build_behavior_profile(relationship, emotion):
    """Compatibility-facing numeric profile derived from the canonical policy."""
    return build_relationship_policy(relationship, emotion)
