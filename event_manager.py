import json
import os


def extract_event(user_message, ai_reply):
    
    if "喜欢" in user_message and "吗" in user_message:
        return {
            "event": f"用户在确认我是否也喜欢：{user_message}",
            "emotion": "curious",
            "impact": "increase_bond",
            "importance": 0.8
        }

    if "喜欢" in user_message:
        return {
            "event": f"用户表达了对某事的喜好：{user_message}",
            "emotion": "neutral_positive",
            "impact": "increase_affinity",
            "importance": 0.6
        }

    return {
        "event": f"普通对话：{user_message}",
        "emotion": "neutral",
        "impact": "none",
        "importance": 0.2
    }
def save_event(event):
    if not event:
        return

    try:
        os.makedirs("data", exist_ok=True)
        with open("data/event_memory.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        data = []

    data.append(event)

    with open("data/event_memory.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)