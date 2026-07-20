"""Single source of truth for relationship-driven behaviour.

Relationship numbers are deliberately translated into a structured policy first.
Every prompt/rendering path consumes that same policy so thresholds cannot drift.
"""

from anime_assistant.infrastructure.models import normalize_relationship


def build_relationship_policy(relationship, emotion=None):
    relationship = normalize_relationship(relationship)
    emotion = emotion if isinstance(emotion, dict) else {}

    affection = relationship["affection"]
    trust = relationship["trust"]
    familiarity = relationship["familiarity"]

    if affection >= 70:
        closeness = "close"
    elif affection >= 40:
        closeness = "friendly"
    else:
        closeness = "reserved"

    if trust >= 70:
        openness = "open"
    elif trust >= 40:
        openness = "careful"
    else:
        openness = "guarded"

    if familiarity >= 70:
        familiarity_level = "familiar"
    elif familiarity >= 40:
        familiarity_level = "acquainted"
    else:
        familiarity_level = "new"

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
