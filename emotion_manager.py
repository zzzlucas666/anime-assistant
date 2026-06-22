import json

def load_emotion():
    with open("data/emotion_state.json", "r", encoding="utf-8") as f:
        return json.load(f)


def save_emotion(emotion):
    with open("data/emotion_state.json", "w", encoding="utf-8") as f:
        json.dump(emotion, f, ensure_ascii=False, indent=4)


# =========================
#  核心：情绪变化系统
# =========================
def update_emotion(emotion, user_message):
    msg = user_message.lower()

    #  基础消耗（每次聊天都会累）
    emotion["energy"] -= 1

    #  正向反馈
    if "谢谢" in msg or "厉害" in msg:
        emotion["affection"] += 5
        emotion["mood"] = "happy"
        emotion["energy"] += 2

    #  害羞触发
    elif "喜欢" in msg or "你是谁" in msg:
        emotion["mood"] = "shy"
        emotion["energy"] -= 1

    #  负面
    elif "烦" in msg or "讨厌" in msg:
        emotion["affection"] -= 5
        emotion["mood"] = "sad"
        emotion["energy"] -= 5

    #  疲劳状态覆盖
    if emotion["energy"] < 20:
        emotion["mood"] = "tired"

    #  限制范围
    emotion["affection"] = max(0, min(100, emotion["affection"]))
    emotion["energy"] = max(0, min(100, emotion["energy"]))

    return emotion