import datetime
from Storage_utils import safe_load_json, safe_save_json

EMOTION_PATH = "data/emotion_state.json"

# mood 自然回归 neutral 的等待时间：超过这么久没有新的"强情绪事件"，
# 心情就慢慢平复下来，而不是永远卡在上一次的状态
MOOD_DECAY_MINUTES = 20

# 精力被动恢复速率：每隔多少分钟回 1 点（模拟"休息一下就缓过来了"）
ENERGY_RECOVERY_PER_MINUTE = 1 / 10
# 单次最多被动回复多少点精力（避免挂机太久直接回满，显得不真实）
ENERGY_RECOVERY_CAP = 30

# event_manager.extract_event 返回的 "emotion" 标签 -> 这里的 mood 枚举值
# 没在表里的标签（比如 neutral）不会主动改变 mood，让自然衰减逻辑去处理
EVENT_EMOTION_TO_MOOD = {
    "happy": "happy",
    "touched": "happy",
    "sad": "sad",
    "worried": "sad",
}


def default_emotion():
    return {
        "mood": "neutral",
        "energy": 80,
        "last_updated": None,   # 上次调用 update_emotion 的真实时间
        "mood_set_at": None,    # mood 最近一次被"强信号"设置的真实时间
    }


def load_emotion():
    return safe_load_json(EMOTION_PATH, default_emotion)


def save_emotion(emotion):
    safe_save_json(EMOTION_PATH, emotion)


def _elapsed_minutes(timestamp_str, now):
    if not timestamp_str:
        return None
    try:
        last_time = datetime.datetime.fromisoformat(timestamp_str)
        return (now - last_time).total_seconds() / 60
    except Exception:
        return None


def update_emotion(emotion, event=None):
    """
    更新情绪状态。

    跟旧版最大的区别：
    - 不再自己维护 affection（好感度只由 relationship 管理，避免两套数字打架）
    - mood 的变化依据 event_manager（AI）的判断结果，而不是关键词匹配
    - energy 会随"真实流逝的时间"被动恢复，不会无限走低、永久疲惫
    - mood 没有新的强信号时，会随时间自然衰减回 neutral，不会永远卡在某个情绪

    event: event_manager.extract_event() 返回的字典，或者 None（比如本轮是
           router 精确回复、没有走事件提取）。
    """
    now = datetime.datetime.now()

    elapsed = _elapsed_minutes(emotion.get("last_updated"), now)
    mood_elapsed = _elapsed_minutes(emotion.get("mood_set_at"), now)

    # 1. 精力：每轮基础消耗 1 点，同时按真实流逝时间被动恢复一些
    emotion["energy"] -= 1
    if elapsed is not None:
        recovered = min(elapsed * ENERGY_RECOVERY_PER_MINUTE, ENERGY_RECOVERY_CAP)
        emotion["energy"] += recovered

    # 2. mood：优先看这轮事件判断出的情绪标签
    mood_changed_by_event = False
    if event:
        event_mood = event.get("emotion", "neutral")
        new_mood = EVENT_EMOTION_TO_MOOD.get(event_mood)
        if new_mood:
            emotion["mood"] = new_mood
            emotion["mood_set_at"] = now.isoformat()
            mood_changed_by_event = True

    # 3. 没有新的强信号时，mood 随时间自然衰减回 neutral
    if not mood_changed_by_event:
        if emotion.get("mood") not in (None, "neutral") and mood_elapsed is not None:
            if mood_elapsed >= MOOD_DECAY_MINUTES:
                emotion["mood"] = "neutral"

    # 4. 精力过低时，疲惫状态覆盖其他情绪（这是身体状态，优先级更高）
    if emotion["energy"] < 20:
        emotion["mood"] = "tired"

    # 5. 限制范围 + 记录这次更新时间
    emotion["energy"] = max(0, min(100, emotion["energy"]))
    emotion["last_updated"] = now.isoformat()

    return emotion