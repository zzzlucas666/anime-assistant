from Storage_utils import safe_load_json, safe_save_json

EMOTION_PATH = "data/emotion_state.json"


def default_emotion():
    return {
        "mood": "neutral",
        "energy": 80,
        "affection": 50
    }


def load_emotion():
    return safe_load_json(EMOTION_PATH, default_emotion)


def save_emotion(emotion):
    safe_save_json(EMOTION_PATH, emotion)


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