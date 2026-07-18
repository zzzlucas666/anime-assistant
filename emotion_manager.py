import datetime
import re

from Storage_utils import safe_load_json, safe_save_json
from app_paths import DATA_DIR
from data_models import ALLOWED_VOICE_STYLES, normalize_emotion

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

AI_CONTROL_USER_MOODS = {
    "neutral", "happy", "sad", "anxious", "angry", "lonely",
    "bored", "stressed", "tired", "disappointed",
}
AI_CONTROL_REACTIONS = {
    "neutral", "happy", "shy", "sad", "worried", "touched",
    "curious", "surprised", "annoyed",
}
DISTRESS_USER_MOODS = {
    "sad", "anxious", "angry", "lonely", "stressed", "tired", "disappointed",
}
SUPPORT_VOICE_STYLES = {"concerned", "reassuring", "serious", "thoughtful"}

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
DIRECT_AFFECTION_PATTERN = re.compile(
    r"我(?:真的|真|一直|还是|越来越)?(?:很|非常|特别|最)?喜欢你"
)
CARE_MARKERS = ("辛苦了", "谢谢你陪", "谢谢你一直", "有你真好", "我会陪你", "别勉强自己")
USER_SAD_MARKERS = (
    "我好难过", "我很难过", "我不开心", "我很伤心", "我想哭",
    "我好失落", "我很失落", "我心情不好", "今天很糟糕",
)
USER_LONELY_MARKERS = (
    "孤单", "孤独", "寂寞", "空落落", "没人陪", "没人找我",
    "没人和我聊天", "没人跟我聊天", "一个人好难受", "感觉很冷清",
)
USER_BORED_MARKERS = (
    "好无聊", "很无聊", "挺无聊", "感到无聊", "觉得无聊",
    "没意思", "没什么事做", "不知道做什么", "提不起兴趣",
)
USER_ANXIOUS_MARKERS = (
    "我好紧张", "我很紧张", "我好担心", "我很担心", "我害怕",
    "我好焦虑", "我很焦虑", "我不安", "我慌了",
)
USER_STRESSED_MARKERS = (
    "压力很大", "压力好大", "压力太大", "忙不过来", "忙得喘不过气",
    "最近很忙", "最近挺忙", "挺忙的", "太忙了", "事情好多",
    "工作压得", "实习很累", "实习挺忙", "快撑不住",
)
USER_TIRED_MARKERS = (
    "我好累", "我很累", "累死了", "累坏了", "身心疲惫",
    "没睡好", "睡不够", "困死了", "精疲力尽",
)
USER_DISAPPOINTED_MARKERS = (
    "我很失望", "我好失望", "太失望了", "失败了", "搞砸了",
    "没考好", "不顺利", "被拒绝了", "白努力了",
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
ADVICE_MARKERS = (
    "怎么办", "有什么办法", "有什么好办法", "有什么建议", "该怎么做",
    "怎么调整", "要怎么改善", "能帮我想想", "要不要试试",
)
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
NEGATED_EMOTION_PATTERN = re.compile(
    r"(?:不|没|没有|并不|不再)(?:是|觉得|感到)?(?:很|太|怎么|那么|特别|非常|有点)?"
    r"(?:难过|伤心|失落|孤单|孤独|寂寞|无聊|紧张|担心|害怕|焦虑|生气|失望|疲惫|累)"
)
PROACTIVE_CONCERN_MARKERS = (
    "还好吗", "没事吧", "怎么了", "担心你", "有点担心", "我很担心",
    "别太勉强", "不要勉强", "休息一下", "难过", "不开心", "孤单", "孤独",
)
PROACTIVE_WARM_MARKERS = (
    "想和你聊", "想找你说", "好久没聊", "陪我聊", "有空吗", "在忙吗",
    "突然想和你", "突然想找你",
)
PROACTIVE_HAPPY_MARKERS = (
    "好消息", "太好了", "真开心", "很开心", "想告诉你", "一起庆祝",
)
PROACTIVE_SURPRISE_MARKERS = ("吓了一跳", "没想到", "居然", "你猜怎么着")
GREETING_WARM_MARKERS = (
    "你来了", "你来啦", "来了啊", "欢迎回来", "回来啦", "好久不见",
    "早上好", "下午好", "晚上好", "见到你", "今天怎么样", "今天过得",
)
GREETING_HAPPY_MARKERS = (
    "太好了", "真开心", "很开心", "好高兴", "终于来了", "等你好久",
)
GREETING_TIRED_MARKERS = ("好困", "有点困", "没睡醒", "我好累", "我有点累")


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
        "voice_style": "conversational",
        "voice_style_strength": 0.4,
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


def _has_personal_compliment(text):
    return (
        _contains_any(text, PERSONAL_COMPLIMENT_MARKERS)
        or bool(DIRECT_AFFECTION_PATTERN.search(text))
    )


def _has_direct_affection(text):
    return (
        _contains_any(text, DIRECT_AFFECTION_MARKERS)
        or bool(DIRECT_AFFECTION_PATTERN.search(text))
    )


def _base_turn_signal(reason="no_clear_signal"):
    return {
        "mood": "neutral",
        "intensity": 0.0,
        "duration_turns": 0,
        "modifier": "none",
        "modifier_strength": 0.0,
        "modifier_duration_turns": 0,
        "voice_style": "conversational",
        "voice_style_strength": 0.4,
        "user_mood": "neutral",
        "user_intensity": 0.0,
        "reset_primary": False,
        "reason": reason,
        "source": "user_input",
        "confidence": 0.25,
        "candidates": [],
        "decision_source": "local_rules",
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


def _set_voice_style(signal, voice_style, intensity=0.6):
    signal["voice_style"] = voice_style
    signal["voice_style_strength"] = max(0.0, min(1.0, float(intensity)))


def _emotion_text(text):
    """移除“没那么孤单”等明确否定片段，减少简单关键词的反向误判。"""
    return NEGATED_EMOTION_PATTERN.sub("", text)


def _candidate(reaction, voice_style, score, reason, user_mood="neutral"):
    return {
        "reaction": reaction,
        "voice_style": voice_style,
        "score": round(max(0.0, min(1.0, float(score))), 3),
        "reason": reason,
        "user_mood": user_mood,
    }


def score_turn_emotion_candidates(user_message, emotion=None, relationship=None):
    """给本轮生成多个轻量候选；只做本地计算，不增加网络请求。"""
    text = user_message if isinstance(user_message, str) else ""
    emotional_text = _emotion_text(text)
    state = normalize_emotion(emotion)
    relationship = relationship if isinstance(relationship, dict) else {}
    affection = float(relationship.get("affection", 30) or 30)
    familiarity = float(relationship.get("familiarity", 10) or 10)
    candidates = []

    def add(reaction, voice_style, score, reason, user_mood="neutral"):
        candidates.append(_candidate(
            reaction, voice_style, score, reason, user_mood=user_mood
        ))

    if _contains_any(emotional_text, USER_SAD_MARKERS) or USER_SAD_PATTERN.search(emotional_text):
        add("worried", "concerned", 0.94, "user_is_sad", "sad")
        add("worried", "reassuring", 0.72, "gentle_support", "sad")
    if _contains_any(emotional_text, USER_LONELY_MARKERS):
        add("worried", "concerned", 0.91, "user_is_lonely", "lonely")
        add("touched", "warm", 0.62, "offer_company", "lonely")
    if _contains_any(emotional_text, USER_ANXIOUS_MARKERS) or USER_ANXIOUS_PATTERN.search(emotional_text):
        add("worried", "reassuring", 0.92, "user_is_anxious", "anxious")
        add("worried", "concerned", 0.73, "anxious_support", "anxious")
    if _contains_any(emotional_text, USER_STRESSED_MARKERS):
        add("worried", "reassuring", 0.85, "user_is_stressed", "stressed")
        add("neutral", "thoughtful", 0.58, "practical_support", "stressed")
    if _contains_any(emotional_text, USER_DISAPPOINTED_MARKERS):
        add("worried", "concerned", 0.89, "user_is_disappointed", "disappointed")
        add("worried", "reassuring", 0.68, "encourage_after_setback", "disappointed")
    if _contains_any(emotional_text, USER_TIRED_MARKERS):
        add("worried", "reassuring", 0.84, "user_is_tired", "tired")
        add("neutral", "warm", 0.57, "gentle_rest_reminder", "tired")
    if _contains_any(emotional_text, USER_BORED_MARKERS):
        add("neutral", "thoughtful", 0.78, "user_is_bored", "bored")
        add("curious", "conversational", 0.52, "explore_boredom", "bored")
    if _contains_any(emotional_text, USER_ANGRY_MARKERS) or USER_ANGRY_PATTERN.search(emotional_text):
        add("worried", "serious", 0.87, "user_is_angry", "angry")
        add("worried", "concerned", 0.64, "calm_user_anger", "angry")
    if _contains_any(emotional_text, USER_HAPPY_MARKERS) or USER_HAPPY_PATTERN.search(emotional_text):
        add("happy", "cheerful", 0.88, "sharing_user_happiness", "happy")
        add("touched", "warm", 0.61, "share_good_news", "happy")

    if _contains_any(text, DIRECTED_NEGATIVE_MARKERS):
        add("sad", "disappointed", 0.95, "negative_words_toward_mio", "angry")
    elif _has_personal_compliment(text):
        closeness = max(0.0, min(1.0, (affection + familiarity - 60.0) / 100.0))
        direct_affection = _has_direct_affection(text)
        happy_bonus = 0.10 * closeness
        if state.get("mood") == "happy":
            happy_bonus += 0.08
        if direct_affection and affection >= 65 and familiarity >= 55:
            happy_bonus += 0.12
        shy_score = 0.84 - 0.13 * closeness - (0.05 if state.get("mood") == "happy" else 0.0)
        happy_score = 0.63 + happy_bonus
        add("shy", "bashful", shy_score, "personal_compliment")
        add("happy", "warm", happy_score, "accept_personal_compliment")
    elif _contains_any(text, ABILITY_COMPLIMENT_MARKERS):
        add("happy", "warm", 0.84, "ability_compliment")
        add("shy", "bashful", 0.58, "modest_about_ability")
    elif _contains_any(text, GENERAL_PRAISE_MARKERS):
        add("happy", "cheerful", 0.76, "general_praise")
        add("touched", "warm", 0.55, "appreciate_praise")
    elif _contains_any(text, CARE_MARKERS):
        add("touched", "warm", 0.86, "care_from_user")
        add("happy", "warm", 0.66, "happy_about_care")
    elif _contains_any(text, ANNOYED_MARKERS):
        add("annoyed", "mild_annoyed", 0.78, "light_teasing")
        add("neutral", "conversational", 0.45, "take_teasing_lightly")
    elif _contains_any(text, SURPRISE_MARKERS):
        add("surprised", "surprised", 0.8, "surprising_information")
        add("curious", "curious", 0.56, "follow_surprise")

    if _contains_any(text, ADVICE_MARKERS):
        add("neutral", "thoughtful", 0.66, "advice_request")
    elif "?" in text or "？" in text or _contains_any(text, QUESTION_MARKERS):
        add("neutral", "conversational", 0.46, "ordinary_question")

    if not candidates:
        add("neutral", "conversational", 0.3, "no_clear_signal")

    deduplicated = {}
    for item in candidates:
        key = (item["reaction"], item["voice_style"], item["user_mood"])
        if key not in deduplicated or item["score"] > deduplicated[key]["score"]:
            deduplicated[key] = item
    return sorted(deduplicated.values(), key=lambda item: item["score"], reverse=True)


def plan_turn_emotion(user_message, emotion=None, relationship=None):
    """在生成回复前规划本轮反应，不依赖 Mio 自己即将生成的措辞。"""
    text = user_message if isinstance(user_message, str) else ""
    emotional_text = _emotion_text(text)
    state = normalize_emotion(emotion)
    relationship = relationship if isinstance(relationship, dict) else {}
    signal = _base_turn_signal()

    personal_praise = _has_personal_compliment(text)
    ability_praise = _contains_any(text, ABILITY_COMPLIMENT_MARKERS)
    general_praise = _contains_any(text, GENERAL_PRAISE_MARKERS)
    candidates = score_turn_emotion_candidates(text, state, relationship)

    user_needs_support = False
    if _contains_any(emotional_text, USER_SAD_MARKERS) or USER_SAD_PATTERN.search(emotional_text):
        signal["user_mood"] = "sad"
        signal["user_intensity"] = 0.82
        _set_modifier(signal, "worried", 0.78, 3)
        _set_voice_style(signal, "concerned", 0.82)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_sad"
        user_needs_support = True
    elif _contains_any(emotional_text, USER_LONELY_MARKERS):
        signal["user_mood"] = "lonely"
        signal["user_intensity"] = 0.78
        _set_modifier(signal, "worried", 0.7, 3)
        _set_voice_style(signal, "concerned", 0.78)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_lonely"
        user_needs_support = True
    elif _contains_any(emotional_text, USER_ANXIOUS_MARKERS) or USER_ANXIOUS_PATTERN.search(emotional_text):
        signal["user_mood"] = "anxious"
        signal["user_intensity"] = 0.78
        _set_modifier(signal, "worried", 0.74, 3)
        _set_voice_style(signal, "reassuring", 0.78)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_anxious"
        user_needs_support = True
    elif _contains_any(emotional_text, USER_STRESSED_MARKERS):
        signal["user_mood"] = "stressed"
        signal["user_intensity"] = 0.58
        _set_modifier(signal, "worried", 0.46, 2)
        _set_voice_style(signal, "reassuring", 0.64)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_stressed"
        user_needs_support = True
    elif _contains_any(emotional_text, USER_DISAPPOINTED_MARKERS):
        signal["user_mood"] = "disappointed"
        signal["user_intensity"] = 0.72
        _set_modifier(signal, "worried", 0.65, 3)
        _set_voice_style(signal, "concerned", 0.72)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_disappointed"
        user_needs_support = True
    elif _contains_any(emotional_text, USER_TIRED_MARKERS):
        signal["user_mood"] = "tired"
        signal["user_intensity"] = 0.66
        _set_modifier(signal, "worried", 0.52, 2)
        _set_voice_style(signal, "reassuring", 0.68)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_tired"
        user_needs_support = True
    elif _contains_any(emotional_text, USER_BORED_MARKERS):
        signal["user_mood"] = "bored"
        signal["user_intensity"] = 0.5
        _set_voice_style(signal, "thoughtful", 0.58)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_bored"
        user_needs_support = True
    elif _contains_any(emotional_text, USER_ANGRY_MARKERS) or USER_ANGRY_PATTERN.search(emotional_text):
        signal["user_mood"] = "angry"
        signal["user_intensity"] = 0.72
        _set_modifier(signal, "worried", 0.58, 2)
        _set_voice_style(signal, "serious", 0.7)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_angry"
        user_needs_support = True
    elif _contains_any(emotional_text, USER_HAPPY_MARKERS) or USER_HAPPY_PATTERN.search(emotional_text):
        signal["user_mood"] = "happy"
        signal["user_intensity"] = 0.78
        _set_primary(signal, "happy", 0.7, "sharing_user_happiness", 4)
        _set_modifier(signal, "touched", 0.45, 2)
        _set_voice_style(signal, "cheerful", 0.74)

    if _contains_any(text, DIRECTED_NEGATIVE_MARKERS):
        signal["user_mood"] = "angry"
        signal["user_intensity"] = max(signal["user_intensity"], 0.78)
        _set_primary(signal, "sad", 0.76, "negative_words_toward_mio", 4)
        _set_modifier(signal, "worried", 0.55, 2)
        _set_voice_style(signal, "disappointed", 0.78)
    elif user_needs_support:
        # 用户正在表达压力或低落时，先接住用户，不让同一句里较弱的夸奖、
        # 问句或玩笑把 Mio 的反应抢走。
        pass
    elif personal_praise:
        # 同时保留“害羞”和“开心”两种候选。关系、当前心情和夸奖类型只
        # 调整概率，不再用一个硬阈值把所有夸奖都固定成同一种反应。
        praise_choice = next(
            (item for item in candidates if item["reaction"] in {"shy", "happy"}),
            {"reaction": "shy"},
        )
        if praise_choice["reaction"] == "happy":
            _set_primary(signal, "happy", 0.72, "warm_personal_compliment", 4)
            _set_modifier(signal, "touched", 0.58, 2)
            _set_voice_style(signal, "warm", 0.74)
        else:
            _set_primary(signal, "shy", 0.76, "personal_compliment", 3)
            _set_voice_style(signal, "bashful", 0.78)
    elif ability_praise:
        _set_primary(signal, "happy", 0.72, "ability_compliment", 5)
        _set_modifier(signal, "touched", 0.35, 1)
        _set_voice_style(signal, "warm", 0.68)
    elif general_praise:
        _set_primary(signal, "happy", 0.62, "general_praise", 4)
        _set_voice_style(signal, "cheerful", 0.64)
    elif _contains_any(text, CARE_MARKERS):
        _set_primary(signal, "happy", 0.62, "care_from_user", 4)
        _set_modifier(signal, "touched", 0.72, 3)
        _set_voice_style(signal, "warm", 0.76)
    elif _contains_any(text, ANNOYED_MARKERS):
        _set_modifier(signal, "annoyed", 0.5, 2)
        _set_voice_style(signal, "mild_annoyed", 0.55)
        signal["reason"] = "light_teasing"
    elif _contains_any(text, SURPRISE_MARKERS):
        _set_modifier(signal, "surprised", 0.62, 1)
        _set_voice_style(signal, "surprised", 0.68)
        signal["reason"] = "surprising_information"
    elif _contains_any(text, ADVICE_MARKERS):
        _set_voice_style(signal, "thoughtful", 0.58)
        signal["reason"] = "advice_request"
    elif ("?" in text or "？" in text or _contains_any(text, QUESTION_MARKERS)):
        # 普通提问只是对话形式，不等于 Mio 自己进入“好奇”情绪。
        _set_voice_style(signal, "conversational", 0.45)
        signal["reason"] = "ordinary_question"

    signal["candidates"] = candidates[:4]
    signal["confidence"] = candidates[0]["score"] if candidates else 0.25
    signal["decision_source"] = "local_candidates"
    return signal


def plan_proactive_emotion(message, signals=None, emotion=None, relationship=None):
    """规划 Mio 主动开口时的表情与声音，不把旧的用户情绪当成本轮输入。"""
    text = message if isinstance(message, str) else ""
    signals = signals if isinstance(signals, dict) else {}
    state = normalize_emotion(emotion)
    relationship = relationship if isinstance(relationship, dict) else {}
    top_event = signals.get("top_event")
    top_event = top_event if isinstance(top_event, dict) else {}
    event_emotion = str(top_event.get("emotion", "neutral") or "neutral")
    event_user_emotion = str(top_event.get("user_emotion", "neutral") or "neutral")
    signal = _base_turn_signal("proactive_conversation")
    signal["source"] = "proactive"

    past_user_distress = event_user_emotion in {
        "sad", "anxious", "angry", "lonely", "stressed", "tired", "disappointed"
    }
    if (
        _contains_any(text, PROACTIVE_CONCERN_MARKERS)
        or event_emotion == "worried"
        or past_user_distress
    ):
        _set_modifier(signal, "worried", 0.68, 2)
        _set_voice_style(signal, "concerned", 0.76)
        signal["reason"] = "proactive_concern"
    elif event_emotion == "touched":
        _set_primary(signal, "happy", 0.58, "proactive_touched_event", 3)
        _set_modifier(signal, "touched", 0.62, 2)
        _set_voice_style(signal, "warm", 0.72)
    elif event_emotion == "happy" or _contains_any(text, PROACTIVE_HAPPY_MARKERS):
        _set_primary(signal, "happy", 0.62, "proactive_happy_topic", 3)
        _set_voice_style(signal, "cheerful", 0.68)
    elif event_emotion == "shy":
        _set_primary(signal, "shy", 0.58, "proactive_shy_topic", 2)
        _set_voice_style(signal, "bashful", 0.68)
    elif event_emotion == "sad":
        _set_primary(signal, "sad", 0.58, "proactive_sad_topic", 3)
        _set_voice_style(signal, "disappointed", 0.68)
    elif state.get("mood") == "tired" or float(state.get("fatigue_strength", 0.0) or 0.0) >= 0.65:
        _set_voice_style(signal, "tired", 0.72)
        signal["reason"] = "proactive_fatigue"
    elif state.get("mood") == "sad":
        _set_voice_style(signal, "disappointed", max(0.55, state.get("mood_strength", 0.0)))
        signal["reason"] = "proactive_low_mood"
    elif _contains_any(text, PROACTIVE_SURPRISE_MARKERS):
        _set_modifier(signal, "surprised", 0.58, 1)
        _set_voice_style(signal, "surprised", 0.64)
        signal["reason"] = "proactive_surprise"
    elif event_emotion == "curious":
        _set_modifier(signal, "curious", 0.42, 1)
        _set_voice_style(signal, "curious", 0.58)
        signal["reason"] = "proactive_curiosity"
    elif (
        _contains_any(text, PROACTIVE_WARM_MARKERS)
        or float(signals.get("idle_score", 0.0) or 0.0) > 0.1
        and float(relationship.get("familiarity", 0.0) or 0.0) >= 30
    ):
        _set_voice_style(signal, "warm", 0.62)
        signal["reason"] = "proactive_warm_contact"
    elif "？" in text or "?" in text:
        _set_modifier(signal, "curious", 0.42, 1)
        _set_voice_style(signal, "curious", 0.58)
        signal["reason"] = "proactive_curiosity"

    return signal


def plan_greeting_emotion(message="", emotion=None, relationship=None):
    """规划启动问候的表情和声音；启动本身不代表用户表达了新情绪。"""
    text = message if isinstance(message, str) else ""
    state = normalize_emotion(emotion)
    relationship = relationship if isinstance(relationship, dict) else {}
    signal = _base_turn_signal("startup_greeting")
    signal["source"] = "greeting"

    if _contains_any(text, PROACTIVE_CONCERN_MARKERS):
        _set_modifier(signal, "worried", 0.58, 2)
        _set_voice_style(signal, "concerned", 0.68)
        signal["reason"] = "greeting_concern"
    elif state.get("mood") == "tired" or float(state.get("fatigue_strength", 0.0) or 0.0) >= 0.65:
        _set_voice_style(signal, "tired", 0.7)
        signal["reason"] = "greeting_tired"
    elif state.get("mood") == "sad":
        _set_voice_style(signal, "disappointed", max(0.55, state.get("mood_strength", 0.0)))
        signal["reason"] = "greeting_low_mood"
    elif state.get("mood") == "shy" or _contains_any(text, SHY_REPLY_MARKERS):
        _set_voice_style(signal, "bashful", max(0.58, state.get("mood_strength", 0.0)))
        signal["reason"] = "greeting_bashful"
    elif state.get("mood") == "happy":
        _set_voice_style(signal, "cheerful", max(0.58, state.get("mood_strength", 0.0)))
        signal["reason"] = "greeting_cheerful"
    elif _contains_any(text, GREETING_TIRED_MARKERS):
        _set_voice_style(signal, "tired", 0.66)
        signal["reason"] = "greeting_sounds_tired"
    elif _contains_any(text, GREETING_HAPPY_MARKERS):
        _set_primary(signal, "happy", 0.52, "greeting_happy_to_see_user", 2)
        _set_voice_style(signal, "cheerful", 0.62)
    elif (
        _contains_any(text, GREETING_WARM_MARKERS)
        or float(relationship.get("familiarity", 0.0) or 0.0) >= 30
        or float(relationship.get("affection", 0.0) or 0.0) >= 45
    ):
        _set_voice_style(signal, "warm", 0.58)
        signal["reason"] = "greeting_warm"

    return signal


def infer_interaction_emotion(user_message, ai_reply, relationship=None, planned=None):
    """回复后校准已存在的本轮计划；不会仅凭自己的语气凭空续期情绪。"""
    signal = dict(planned) if isinstance(planned, dict) else plan_turn_emotion(
        user_message, relationship=relationship
    )
    text = user_message if isinstance(user_message, str) else ""
    reply_text = ai_reply if isinstance(ai_reply, str) else ""
    is_praise = (
        _has_personal_compliment(text)
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
        _set_voice_style(
            signal,
            "embarrassed" if _contains_any(reply_text, ("害羞", "脸红", "红着脸")) else "bashful",
            0.84,
        )
    elif reply_is_happy:
        _set_primary(signal, "happy", 0.7, "accepted_compliment", 4)
        _set_voice_style(
            signal,
            "warm" if _has_personal_compliment(text) else "cheerful",
            0.7,
        )
    return signal


def _bounded_probability(value, default=0.0):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def apply_ai_emotion_control(planned, control):
    """用主回复附带的控制信息校准本轮反应；异常时原样回退本地计划。"""
    signal = dict(planned) if isinstance(planned, dict) else _base_turn_signal()
    if not isinstance(control, dict):
        return signal

    user_mood = str(control.get("user_mood", "neutral") or "neutral")
    reaction = str(control.get("reaction", "neutral") or "neutral")
    voice_style = str(control.get("voice_style", "conversational") or "conversational")
    strength = _bounded_probability(control.get("strength"), 0.5)
    ai_confidence = _bounded_probability(control.get("confidence"), 0.0)
    if (
        ai_confidence < 0.55
        or user_mood not in AI_CONTROL_USER_MOODS
        or reaction not in AI_CONTROL_REACTIONS
        or voice_style not in ALLOWED_VOICE_STYLES
    ):
        return signal

    local_confidence = _bounded_probability(signal.get("confidence"), 0.25)
    local_user_mood = str(signal.get("user_mood", "neutral") or "neutral")
    local_reason = str(signal.get("reason", "") or "")
    strong_support = (
        local_user_mood in DISTRESS_USER_MOODS
        and local_confidence >= 0.72
        and local_reason != "negative_words_toward_mio"
    )
    strong_directed_negative = (
        local_reason == "negative_words_toward_mio" and local_confidence >= 0.72
    )

    # 明确的求助/低落信号不能被模型误校准成开心或害羞；对 Mio 的直接
    # 负面话语也保留本地的失落反应。AI 在这些场景只可细化同方向语气。
    if strong_directed_negative:
        if voice_style in {"disappointed", "serious"}:
            _set_voice_style(signal, voice_style, strength)
    elif strong_support:
        if reaction == "worried":
            _set_modifier(signal, "worried", max(0.5, strength), 3)
        if voice_style in SUPPORT_VOICE_STYLES:
            _set_voice_style(signal, voice_style, strength)
    else:
        if user_mood != "neutral" and (
            local_user_mood == "neutral" or ai_confidence > local_confidence + 0.08
        ):
            signal["user_mood"] = user_mood
            signal["user_intensity"] = max(0.35, strength)
            if user_mood in DISTRESS_USER_MOODS:
                signal["reset_primary"] = True

        if user_mood in DISTRESS_USER_MOODS:
            if reaction == "worried":
                _set_modifier(signal, "worried", max(0.45, strength), 3)
            if voice_style in SUPPORT_VOICE_STYLES:
                _set_voice_style(signal, voice_style, strength)
        elif reaction in {"happy", "shy", "sad"}:
            _set_primary(
                signal,
                reaction,
                max(0.35, strength),
                f"ai_calibrated_{reaction}",
            )
        elif reaction in {"worried", "touched", "curious", "surprised", "annoyed"}:
            _set_modifier(signal, reaction, max(0.3, strength))
            signal["reason"] = f"ai_calibrated_{reaction}"

        if user_mood not in DISTRESS_USER_MOODS:
            _set_voice_style(signal, voice_style, strength)

    signal["decision_source"] = "hybrid_ai"
    signal["ai_confidence"] = ai_confidence
    signal["ai_control"] = {
        "user_mood": user_mood,
        "reaction": reaction,
        "voice_style": voice_style,
        "strength": strength,
    }
    return signal


def has_interaction_signal(signal):
    if not isinstance(signal, dict):
        return False
    return any((
        signal.get("mood") not in (None, "neutral"),
        signal.get("modifier") not in (None, "none"),
        signal.get("voice_style") not in (None, ""),
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
        _set_voice_style(
            signal,
            {"happy": "cheerful", "shy": "bashful", "sad": "disappointed"}[emotion],
            intensity,
        )
    elif emotion == "touched":
        _set_primary(signal, "happy", intensity * 0.8, "touching_event", 4)
        _set_modifier(signal, "touched", intensity, 3)
        _set_voice_style(signal, "warm", intensity)
    elif emotion == "worried":
        _set_modifier(signal, "worried", intensity, 3)
        _set_voice_style(signal, "concerned", intensity)
    elif emotion == "curious":
        _set_modifier(signal, "curious", intensity, 1)
        _set_voice_style(signal, "curious", intensity)
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


def _apply_voice_style(emotion, signal):
    """保存本轮说话方式；它与持续 mood 相互独立，不参与 mood 寿命计算。"""
    voice_style = signal.get("voice_style") if isinstance(signal, dict) else None
    if voice_style not in ALLOWED_VOICE_STYLES:
        voice_style = "conversational"
    emotion["voice_style"] = voice_style
    emotion["voice_style_strength"] = max(
        0.0,
        min(1.0, float(signal.get("voice_style_strength", 0.4) or 0.4)),
    )


def _fatigue_strength(energy):
    return max(0.0, min(1.0, (45.0 - float(energy)) / 25.0))


def update_emotion(emotion, event=None, interaction=None, consume_energy=True):
    """推进一轮情绪状态；即时反应优先，事件分析只作为兜底。"""
    normalized = normalize_emotion(emotion)
    emotion.clear()
    emotion.update(normalized)
    now = datetime.datetime.now()
    was_tired = emotion.get("mood") == "tired"

    elapsed = _elapsed_minutes(emotion.get("last_updated"), now)
    mood_elapsed = _elapsed_minutes(emotion.get("mood_set_at"), now)
    if consume_energy:
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
    _apply_voice_style(emotion, signal)
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
