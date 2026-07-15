import datetime
import re

from Storage_utils import safe_load_json, safe_save_json
from app_paths import DATA_DIR
from data_models import normalize_emotion

EMOTION_PATH = str(DATA_DIR / "emotion_state.json")

MOOD_DECAY_MINUTES = 20
ENERGY_RECOVERY_PER_MINUTE = 1 / 10
ENERGY_RECOVERY_CAP = 30
MIN_SIGNAL_INTENSITY = 0.28
STRONG_SWITCH_INTENSITY = 0.72
PENDING_MOOD_MINUTES = 5
FATIGUE_ENTER_ENERGY = 25
FATIGUE_EXIT_ENERGY = 35

POSITIVE_MOODS = {"happy", "shy"}
MOOD_DURATIONS = {"happy": 5, "shy": 3, "sad": 6}
MODIFIER_DURATIONS = {
    "worried": 3,
    "touched": 2,
    "curious": 1,
    "surprised": 1,
    "annoyed": 2,
}

PERSONAL_COMPLIMENT_MARKERS = (
    "你好可爱", "你很可爱", "真可爱", "太可爱", "觉得你可爱",
    "你好漂亮", "你很漂亮", "真漂亮", "太漂亮", "觉得你漂亮",
    "你好看", "你很美", "很有魅力", "声音好听", "声音真好听",
    "我喜欢你", "最喜欢你", "我爱你", "对你心动",
)
ABILITY_COMPLIMENT_MARKERS = (
    "弹得真好", "弹得很好", "弹得好", "唱得真好", "唱得很好", "唱得好",
    "演奏得真好", "演奏得很好", "贝斯很棒", "贝斯真棒",
    "做得真好", "做得很好", "做得不错", "进步很大", "进步好多",
    "很厉害", "真厉害", "太厉害", "很优秀", "真优秀", "了不起",
)
GENERAL_PRAISE_MARKERS = (
    "真棒", "太棒", "很棒", "干得好", "表现很好", "表现不错", "值得夸",
)
DIRECT_AFFECTION_MARKERS = ("我喜欢你", "最喜欢你", "我爱你", "对你心动")
CARE_MARKERS = ("辛苦了", "谢谢你陪", "谢谢你一直", "有你真好", "我会陪你", "别勉强自己")
USER_SAD_MARKERS = (
    "我好难过", "我很难过", "我不开心", "我很伤心", "我想哭",
    "我好失落", "我很失落", "我心情不好", "今天很糟糕",
)
USER_ANXIOUS_MARKERS = (
    "我好紧张", "我很紧张", "我好担心", "我很担心", "我害怕",
    "我好焦虑", "我很焦虑", "我不安", "我慌了",
)
USER_ANGRY_MARKERS = ("我生气", "我很生气", "气死我", "我好火大", "烦死了")
USER_HAPPY_MARKERS = (
    "我好开心", "我很开心", "太好了", "我成功了", "我通过了",
    "我做到了", "我考得很好", "今天很顺利",
)
DIRECTED_NEGATIVE_MARKERS = ("讨厌你", "你真烦", "不想理你", "你让我失望")
ANNOYED_MARKERS = ("你真笨", "笨蛋", "逗你的", "开玩笑的")
SURPRISE_MARKERS = ("没想到", "居然", "告诉你个秘密", "你猜怎么着", "我中奖了")
QUESTION_MARKERS = ("为什么", "怎么会", "你觉得", "你知道", "真的吗", "是不是")
SHY_REPLY_MARKERS = (
    "害羞", "脸红", "红着脸", "移开视线", "低下头", "别这样说",
    "突然说什么", "让人不好意思", "不知道怎么办", "才不可爱", "哪有那么",
)
HAPPY_REPLY_MARKERS = (
    "好开心", "很开心", "太好了", "谢谢你夸", "谢谢你这么说", "我会继续努力",
)
STAMMER_PATTERN = re.compile(r"(?:^|[（(，,。！？!?、\s])[你我这那]\s*[、,，]")
USER_SAD_PATTERN = re.compile(r"我(?:(?!你).){0,8}(?:难过|伤心|不开心|失落|想哭|心情不好)")
USER_ANXIOUS_PATTERN = re.compile(r"我(?:(?!你).){0,8}(?:紧张|担心|害怕|焦虑|不安|慌)")
USER_ANGRY_PATTERN = re.compile(r"我(?:(?!你).){0,8}(?:生气|火大|恼火)")
USER_HAPPY_PATTERN = re.compile(r"我(?:(?!你).){0,8}(?:开心|高兴|成功了|通过了|做到了)")


def default_emotion():
    return {
        "mood": "neutral",
        "energy": 80,
        "last_updated": None,
        "mood_set_at": None,
        "mood_strength": 0.0,
        "mood_turns_remaining": 0,
        "mood_source": "default",
        "modifier": "none",
        "modifier_strength": 0.0,
        "modifier_turns_remaining": 0,
        "user_mood": "neutral",
        "user_mood_strength": 0.0,
        "user_mood_set_at": None,
        "fatigue_strength": 0.0,
        "pending_mood": None,
        "pending_mood_count": 0,
        "pending_mood_expires_at": None,
    }


def load_emotion():
    raw_emotion = safe_load_json(EMOTION_PATH, default_emotion)
    emotion = normalize_emotion(raw_emotion)
    if emotion != raw_emotion:
        safe_save_json(EMOTION_PATH, emotion)
    return emotion


def save_emotion(emotion):
    normalized = normalize_emotion(emotion)
    emotion.clear()
    emotion.update(normalized)
    return safe_save_json(EMOTION_PATH, emotion)


def _elapsed_minutes(timestamp_str, now):
    if not timestamp_str:
        return None
    try:
        last_time = datetime.datetime.fromisoformat(timestamp_str)
        return (now - last_time).total_seconds() / 60
    except Exception:
        return None


def _contains_any(text, markers):
    return any(marker in text for marker in markers)


def _base_turn_signal(reason="no_clear_signal"):
    return {
        "mood": "neutral",
        "intensity": 0.0,
        "duration_turns": 0,
        "modifier": "none",
        "modifier_strength": 0.0,
        "modifier_duration_turns": 0,
        "user_mood": "neutral",
        "user_intensity": 0.0,
        "reset_primary": False,
        "reason": reason,
        "source": "user_input",
    }


def _set_primary(signal, mood, intensity, reason, duration=None):
    # 后出现的明确 Mio 反应优先于之前“先回到平静再关心用户”的计划。
    signal["reset_primary"] = False
    signal["mood"] = mood
    signal["intensity"] = intensity
    signal["duration_turns"] = duration if duration is not None else MOOD_DURATIONS.get(mood, 0)
    signal["reason"] = reason


def _set_modifier(signal, modifier, intensity, duration=None):
    signal["modifier"] = modifier
    signal["modifier_strength"] = intensity
    signal["modifier_duration_turns"] = (
        duration if duration is not None else MODIFIER_DURATIONS.get(modifier, 1)
    )


def plan_turn_emotion(user_message, emotion=None, relationship=None):
    """在生成回复前规划本轮反应，不依赖 Mio 自己即将生成的措辞。"""
    text = user_message if isinstance(user_message, str) else ""
    state = normalize_emotion(emotion)
    relationship = relationship if isinstance(relationship, dict) else {}
    affection = float(relationship.get("affection", 30) or 30)
    familiarity = float(relationship.get("familiarity", 10) or 10)
    signal = _base_turn_signal()

    personal_praise = _contains_any(text, PERSONAL_COMPLIMENT_MARKERS)
    ability_praise = _contains_any(text, ABILITY_COMPLIMENT_MARKERS)
    general_praise = _contains_any(text, GENERAL_PRAISE_MARKERS)

    if _contains_any(text, USER_SAD_MARKERS) or USER_SAD_PATTERN.search(text):
        signal["user_mood"] = "sad"
        signal["user_intensity"] = 0.82
        _set_modifier(signal, "worried", 0.78, 3)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_sad"
    elif _contains_any(text, USER_ANXIOUS_MARKERS) or USER_ANXIOUS_PATTERN.search(text):
        signal["user_mood"] = "anxious"
        signal["user_intensity"] = 0.78
        _set_modifier(signal, "worried", 0.74, 3)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_anxious"
    elif _contains_any(text, USER_ANGRY_MARKERS) or USER_ANGRY_PATTERN.search(text):
        signal["user_mood"] = "angry"
        signal["user_intensity"] = 0.72
        _set_modifier(signal, "worried", 0.58, 2)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_angry"
    elif _contains_any(text, USER_HAPPY_MARKERS) or USER_HAPPY_PATTERN.search(text):
        signal["user_mood"] = "happy"
        signal["user_intensity"] = 0.78
        _set_primary(signal, "happy", 0.7, "sharing_user_happiness", 4)
        _set_modifier(signal, "touched", 0.45, 2)

    if _contains_any(text, DIRECTED_NEGATIVE_MARKERS):
        signal["user_mood"] = "angry"
        signal["user_intensity"] = max(signal["user_intensity"], 0.78)
        _set_primary(signal, "sad", 0.76, "negative_words_toward_mio", 4)
        _set_modifier(signal, "worried", 0.55, 2)
    elif personal_praise:
        # 关系足够亲近且本来就在开心时，更可能坦然高兴；其他情况下保留
        # Mio 对直接夸奖的害羞反应。回复完成后还会根据实际措辞做一次校准。
        accepts_warmly = affection >= 65 and familiarity >= 55 and state.get("mood") == "happy"
        if accepts_warmly and _contains_any(text, DIRECT_AFFECTION_MARKERS):
            _set_primary(signal, "happy", 0.72, "warm_personal_compliment", 4)
            _set_modifier(signal, "touched", 0.58, 2)
        else:
            _set_primary(signal, "shy", 0.76, "personal_compliment", 3)
    elif ability_praise:
        _set_primary(signal, "happy", 0.72, "ability_compliment", 5)
        _set_modifier(signal, "touched", 0.35, 1)
    elif general_praise:
        _set_primary(signal, "happy", 0.62, "general_praise", 4)
    elif _contains_any(text, CARE_MARKERS):
        _set_primary(signal, "happy", 0.62, "care_from_user", 4)
        _set_modifier(signal, "touched", 0.72, 3)
    elif _contains_any(text, ANNOYED_MARKERS):
        _set_modifier(signal, "annoyed", 0.5, 2)
        signal["reason"] = "light_teasing"
    elif _contains_any(text, SURPRISE_MARKERS):
        _set_modifier(signal, "surprised", 0.62, 1)
        signal["reason"] = "surprising_information"
    elif ("?" in text or "？" in text or _contains_any(text, QUESTION_MARKERS)):
        _set_modifier(signal, "curious", 0.35, 1)
        signal["reason"] = "question"

    return signal


def infer_interaction_emotion(user_message, ai_reply, relationship=None, planned=None):
    """回复后校准已存在的本轮计划；不会仅凭自己的语气凭空续期情绪。"""
    signal = dict(planned) if isinstance(planned, dict) else plan_turn_emotion(
        user_message, relationship=relationship
    )
    text = user_message if isinstance(user_message, str) else ""
    reply_text = ai_reply if isinstance(ai_reply, str) else ""
    is_praise = (
        _contains_any(text, PERSONAL_COMPLIMENT_MARKERS)
        or _contains_any(text, ABILITY_COMPLIMENT_MARKERS)
        or _contains_any(text, GENERAL_PRAISE_MARKERS)
    )
    if not is_praise:
        return signal

    reply_is_shy = (
        _contains_any(reply_text, SHY_REPLY_MARKERS)
        or bool(STAMMER_PATTERN.search(reply_text))
        or ("不好意思" in reply_text and "不用不好意思" not in reply_text)
    )
    reply_is_happy = _contains_any(reply_text, HAPPY_REPLY_MARKERS)
    if reply_is_shy:
        _set_primary(signal, "shy", 0.86, "shy_reaction_to_praise", 3)
    elif reply_is_happy:
        _set_primary(signal, "happy", 0.7, "accepted_compliment", 4)
    return signal


def has_interaction_signal(signal):
    if not isinstance(signal, dict):
        return False
    return any((
        signal.get("mood") not in (None, "neutral"),
        signal.get("modifier") not in (None, "none"),
        signal.get("user_mood") not in (None, "neutral"),
        bool(signal.get("reset_primary")),
    ))


def _event_signal(event):
    if not isinstance(event, dict):
        return None
    emotion = event.get("emotion", "neutral")
    try:
        importance = float(event.get("importance", 0.3))
    except (TypeError, ValueError):
        importance = 0.3
    importance = max(0.0, min(1.0, importance))
    intensity = max(0.35, min(0.9, 0.35 + importance * 0.55))
    signal = _base_turn_signal("long_term_event")
    signal["source"] = "long_term_event"
    signal["user_mood"] = event.get("user_emotion", "neutral")
    signal["user_intensity"] = intensity if signal["user_mood"] != "neutral" else 0.0
    if emotion in {"happy", "shy", "sad"}:
        _set_primary(signal, emotion, intensity, "long_term_event")
    elif emotion == "touched":
        _set_primary(signal, "happy", intensity * 0.8, "touching_event", 4)
        _set_modifier(signal, "touched", intensity, 3)
    elif emotion == "worried":
        _set_modifier(signal, "worried", intensity, 3)
    elif emotion == "curious":
        _set_modifier(signal, "curious", intensity, 1)
    return signal


def _is_cross_valence(current_mood, new_mood):
    if current_mood in ("neutral", "tired") or new_mood in ("neutral", "tired"):
        return False
    return (current_mood in POSITIVE_MOODS) != (new_mood in POSITIVE_MOODS)


def _clear_pending(emotion):
    emotion["pending_mood"] = None
    emotion["pending_mood_count"] = 0
    emotion["pending_mood_expires_at"] = None


def _pending_valid(emotion, now, mood):
    if emotion.get("pending_mood") != mood:
        return False
    expires_at = emotion.get("pending_mood_expires_at")
    if not expires_at:
        return False
    try:
        return datetime.datetime.fromisoformat(expires_at) >= now
    except Exception:
        return False


def _apply_mood_signal(emotion, signal, now):
    new_mood = signal.get("mood") if isinstance(signal, dict) else None
    try:
        intensity = float(signal.get("intensity", 0.0))
    except (AttributeError, TypeError, ValueError):
        return False
    intensity = max(0.0, min(1.0, intensity))
    if new_mood not in {"happy", "shy", "sad"} or intensity < MIN_SIGNAL_INTENSITY:
        return False

    current_mood = emotion.get("mood", "neutral")
    current_strength = float(emotion.get("mood_strength", 0.0) or 0.0)
    duration = int(signal.get("duration_turns") or MOOD_DURATIONS.get(new_mood, 3))

    if new_mood == current_mood:
        emotion["mood_strength"] = min(1.0, current_strength * 0.55 + intensity * 0.55)
        emotion["mood_turns_remaining"] = max(emotion.get("mood_turns_remaining", 0), duration)
        emotion["mood_set_at"] = now.isoformat()
        emotion["mood_source"] = str(signal.get("source") or signal.get("reason") or "interaction")
        _clear_pending(emotion)
        return True

    if _is_cross_valence(current_mood, new_mood) and intensity < STRONG_SWITCH_INTENSITY:
        if _pending_valid(emotion, now, new_mood):
            emotion["pending_mood_count"] = int(emotion.get("pending_mood_count", 0)) + 1
        else:
            emotion["pending_mood"] = new_mood
            emotion["pending_mood_count"] = 1
        emotion["pending_mood_expires_at"] = (
            now + datetime.timedelta(minutes=PENDING_MOOD_MINUTES)
        ).isoformat()
        if emotion["pending_mood_count"] < 2:
            return False

    emotion["mood"] = new_mood
    emotion["mood_strength"] = intensity
    emotion["mood_turns_remaining"] = duration
    emotion["mood_set_at"] = now.isoformat()
    emotion["mood_source"] = str(signal.get("source") or signal.get("reason") or "interaction")
    _clear_pending(emotion)
    return True


def _advance_mood_lifetime(emotion):
    if emotion.get("mood") in (None, "neutral", "tired"):
        return
    remaining = max(0, int(emotion.get("mood_turns_remaining", 0)))
    if remaining > 0:
        emotion["mood_turns_remaining"] = remaining - 1
        return
    strength = float(emotion.get("mood_strength", 0.0) or 0.0) * 0.55
    if strength < MIN_SIGNAL_INTENSITY:
        emotion["mood"] = "neutral"
        emotion["mood_strength"] = 0.0
        emotion["mood_source"] = "natural_decay"
    else:
        emotion["mood_strength"] = strength


def _advance_modifier(emotion, signal):
    modifier = signal.get("modifier") if isinstance(signal, dict) else "none"
    if modifier not in (None, "none"):
        emotion["modifier"] = modifier
        emotion["modifier_strength"] = max(0.0, min(1.0, float(signal.get("modifier_strength", 0.5))))
        emotion["modifier_turns_remaining"] = int(
            signal.get("modifier_duration_turns") or MODIFIER_DURATIONS.get(modifier, 1)
        )
        return

    remaining = max(0, int(emotion.get("modifier_turns_remaining", 0)))
    if remaining > 1:
        emotion["modifier_turns_remaining"] = remaining - 1
        emotion["modifier_strength"] *= 0.82
    else:
        emotion["modifier"] = "none"
        emotion["modifier_strength"] = 0.0
        emotion["modifier_turns_remaining"] = 0


def _apply_user_emotion(emotion, signal, now):
    user_mood = signal.get("user_mood") if isinstance(signal, dict) else "neutral"
    if user_mood in (None, "neutral"):
        # 用户情绪比 Mio 的短暂表情更慢淡出，但不会永久保留。
        emotion["user_mood_strength"] *= 0.7
        if emotion["user_mood_strength"] < 0.2:
            emotion["user_mood"] = "neutral"
            emotion["user_mood_strength"] = 0.0
        return
    emotion["user_mood"] = user_mood
    emotion["user_mood_strength"] = max(0.0, min(1.0, float(signal.get("user_intensity", 0.6))))
    emotion["user_mood_set_at"] = now.isoformat()


def _fatigue_strength(energy):
    return max(0.0, min(1.0, (45.0 - float(energy)) / 25.0))


def update_emotion(emotion, event=None, interaction=None):
    """推进一轮情绪状态；即时反应优先，事件分析只作为兜底。"""
    normalized = normalize_emotion(emotion)
    emotion.clear()
    emotion.update(normalized)
    now = datetime.datetime.now()
    was_tired = emotion.get("mood") == "tired"

    elapsed = _elapsed_minutes(emotion.get("last_updated"), now)
    mood_elapsed = _elapsed_minutes(emotion.get("mood_set_at"), now)
    emotion["energy"] -= 1
    if elapsed is not None:
        emotion["energy"] += min(
            elapsed * ENERGY_RECOVERY_PER_MINUTE,
            ENERGY_RECOVERY_CAP,
        )
    emotion["energy"] = max(0, min(100, emotion["energy"]))
    emotion["fatigue_strength"] = _fatigue_strength(emotion["energy"])

    signal = interaction if has_interaction_signal(interaction) else _event_signal(event)
    if signal is None:
        signal = _base_turn_signal()

    _apply_user_emotion(emotion, signal, now)
    _advance_modifier(emotion, signal)

    has_primary = signal.get("mood") not in (None, "neutral")
    reset_primary = bool(signal.get("reset_primary"))
    if reset_primary:
        emotion["mood"] = "neutral"
        emotion["mood_strength"] = 0.0
        emotion["mood_turns_remaining"] = 0
        emotion["mood_source"] = str(signal.get("reason") or "empathetic_reset")
        _clear_pending(emotion)
    elif has_primary:
        mood_changed = _apply_mood_signal(emotion, signal, now)
        if not mood_changed:
            _advance_mood_lifetime(emotion)
    else:
        _clear_pending(emotion)
        _advance_mood_lifetime(emotion)

    if (
        emotion.get("mood") not in (None, "neutral", "tired")
        and mood_elapsed is not None
        and mood_elapsed >= MOOD_DECAY_MINUTES
        and not has_primary
        and not reset_primary
    ):
        emotion["mood"] = "neutral"
        emotion["mood_strength"] = 0.0
        emotion["mood_turns_remaining"] = 0
        emotion["mood_source"] = "time_decay"

    # 疲惫使用进入/退出双阈值，避免精力在边界附近来回闪烁。
    if emotion["energy"] <= FATIGUE_ENTER_ENERGY or (
        was_tired and emotion["energy"] < FATIGUE_EXIT_ENERGY
    ):
        emotion["mood"] = "tired"
        emotion["mood_strength"] = max(0.65, emotion["fatigue_strength"])
        emotion["mood_turns_remaining"] = 0
        emotion["mood_source"] = "fatigue"
        _clear_pending(emotion)
    elif was_tired and emotion["energy"] >= FATIGUE_EXIT_ENERGY and not has_primary:
        emotion["mood"] = "neutral"
        emotion["mood_strength"] = 0.0
        emotion["mood_source"] = "recovered"

    emotion["last_updated"] = now.isoformat()
    return emotion
