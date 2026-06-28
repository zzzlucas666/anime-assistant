from Storage_utils import safe_load_json, safe_save_json

RELATIONSHIP_PATH = "data/relationship.json"


def default_relationship():
    return {
        "affection": 30,
        "trust": 30,
        "familiarity": 10
    }


def load_relationship():
    return safe_load_json(RELATIONSHIP_PATH, default_relationship)


def save_relationship(data):
    safe_save_json(RELATIONSHIP_PATH, data)


def update_relationship(relationship, event):
    """
    根据 event_manager.extract_event 返回的事件字典更新关系状态。
    event 形如：
        {
            "event": "...",
            "emotion": "...",
            "impact": "increase_bond" | "increase_affinity" | "none",
            "importance": 0.0~1.0
        }
    也兼容旧的字符串调用方式："positive" / "negative" / "talk"。
    """
    # 兼容旧调用方式（直接传字符串）
    if isinstance(event, str):
        impact = event
        importance = 1.0
    else:
        impact = event.get("impact", "none") if event else "none"
        importance = event.get("importance", 0.5) if event else 0.5

    if impact == "increase_bond":
        relationship["affection"] += 3 * importance
        relationship["trust"] += 2 * importance
        relationship["familiarity"] += 1 * importance

    elif impact == "increase_affinity":
        relationship["affection"] += 1 * importance
        relationship["familiarity"] += 0.5 * importance

    elif impact == "positive":
        relationship["affection"] += 1

    elif impact == "negative":
        relationship["affection"] -= 1

    elif impact == "talk":
        relationship["familiarity"] += 0.1

    else:
        # 普通对话也会略微增加熟悉度
        relationship["familiarity"] += 0.05

    # 限制范围
    relationship["affection"] = max(0, min(100, relationship["affection"]))
    relationship["trust"] = max(0, min(100, relationship["trust"]))
    relationship["familiarity"] = max(0, min(100, relationship["familiarity"]))

    return relationship