import json

def load_relationship():
    with open("data/relationship.json", "r", encoding="utf-8") as f:
        return json.load(f)


def save_relationship(data):
    with open("data/relationship.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def update_relationship(relationship, action):
    if action == "positive":
        relationship["affection"] += 1

    elif action == "negative":
        relationship["affection"] -= 1

    elif action == "talk":
        relationship["familiarity"] += 0.1

    # 限制范围
    relationship["affection"] = max(0, min(100, relationship["affection"]))
    relationship["trust"] = max(0, min(100, relationship["trust"]))

    return relationship