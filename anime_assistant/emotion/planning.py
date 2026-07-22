"""Pure local planning for chat, greeting, and proactive emotion signals."""

from anime_assistant.infrastructure.models import normalize_emotion
from anime_assistant.emotion.signals import (
    EmotionCandidate,
    EmotionSignal,
    _base_turn_signal,
    _set_modifier,
    _set_primary,
    _set_voice_style,
)
from anime_assistant.emotion.rules import (
    ABILITY_COMPLIMENT_MARKERS,
    ADVICE_MARKERS,
    ANNOYED_MARKERS,
    CARE_MARKERS,
    DIRECTED_NEGATIVE_MARKERS,
    GENERAL_PRAISE_MARKERS,
    GREETING_HAPPY_MARKERS,
    GREETING_TIRED_MARKERS,
    GREETING_WARM_MARKERS,
    HAPPY_REPLY_MARKERS,
    PROACTIVE_CONCERN_MARKERS,
    PROACTIVE_HAPPY_MARKERS,
    PROACTIVE_SURPRISE_MARKERS,
    PROACTIVE_WARM_MARKERS,
    QUESTION_MARKERS,
    SHY_REPLY_MARKERS,
    STAMMER_PATTERN,
    SURPRISE_MARKERS,
    USER_ANGRY_MARKERS,
    USER_ANGRY_PATTERN,
    USER_ANXIOUS_MARKERS,
    USER_ANXIOUS_PATTERN,
    USER_BORED_MARKERS,
    USER_DISAPPOINTED_MARKERS,
    USER_HAPPY_MARKERS,
    USER_HAPPY_PATTERN,
    USER_LONELY_MARKERS,
    USER_SAD_MARKERS,
    USER_SAD_PATTERN,
    USER_STRESSED_MARKERS,
    USER_TIRED_MARKERS,
    contains_any,
    emotion_text,
    has_direct_affection,
    has_personal_compliment,
)


def _candidate(
    reaction: str,
    voice_style: str,
    score: float,
    reason: str,
    user_mood: str = "neutral",
) -> EmotionCandidate:
    return {
        "reaction": reaction,
        "voice_style": voice_style,
        "score": round(max(0.0, min(1.0, float(score))), 3),
        "reason": reason,
        "user_mood": user_mood,
    }


def score_turn_emotion_candidates(
    user_message,
    emotion=None,
    relationship=None,
) -> list[EmotionCandidate]:
    """给本轮生成多个轻量候选；只做本地计算，不增加网络请求。"""
    text = user_message if isinstance(user_message, str) else ""
    emotional_text = emotion_text(text)
    state = normalize_emotion(emotion)
    relationship = relationship if isinstance(relationship, dict) else {}
    affection = float(relationship.get("affection", 30) or 30)
    familiarity = float(relationship.get("familiarity", 10) or 10)
    candidates = []

    def add(reaction, voice_style, score, reason, user_mood="neutral"):
        candidates.append(_candidate(
            reaction, voice_style, score, reason, user_mood=user_mood
        ))

    if contains_any(emotional_text, USER_SAD_MARKERS) or USER_SAD_PATTERN.search(emotional_text):
        add("worried", "concerned", 0.94, "user_is_sad", "sad")
        add("worried", "reassuring", 0.72, "gentle_support", "sad")
    if contains_any(emotional_text, USER_LONELY_MARKERS):
        add("worried", "concerned", 0.91, "user_is_lonely", "lonely")
        add("touched", "warm", 0.62, "offer_company", "lonely")
    if contains_any(emotional_text, USER_ANXIOUS_MARKERS) or USER_ANXIOUS_PATTERN.search(emotional_text):
        add("worried", "reassuring", 0.92, "user_is_anxious", "anxious")
        add("worried", "concerned", 0.73, "anxious_support", "anxious")
    if contains_any(emotional_text, USER_STRESSED_MARKERS):
        add("worried", "reassuring", 0.85, "user_is_stressed", "stressed")
        add("neutral", "thoughtful", 0.58, "practical_support", "stressed")
    if contains_any(emotional_text, USER_DISAPPOINTED_MARKERS):
        add("worried", "concerned", 0.89, "user_is_disappointed", "disappointed")
        add("worried", "reassuring", 0.68, "encourage_after_setback", "disappointed")
    if contains_any(emotional_text, USER_TIRED_MARKERS):
        add("worried", "reassuring", 0.84, "user_is_tired", "tired")
        add("neutral", "warm", 0.57, "gentle_rest_reminder", "tired")
    if contains_any(emotional_text, USER_BORED_MARKERS):
        add("neutral", "thoughtful", 0.78, "user_is_bored", "bored")
        add("curious", "conversational", 0.52, "explore_boredom", "bored")
    if contains_any(emotional_text, USER_ANGRY_MARKERS) or USER_ANGRY_PATTERN.search(emotional_text):
        add("worried", "serious", 0.87, "user_is_angry", "angry")
        add("worried", "concerned", 0.64, "calm_user_anger", "angry")
    if contains_any(emotional_text, USER_HAPPY_MARKERS) or USER_HAPPY_PATTERN.search(emotional_text):
        add("happy", "cheerful", 0.88, "sharing_user_happiness", "happy")
        add("touched", "warm", 0.61, "share_good_news", "happy")

    if contains_any(text, DIRECTED_NEGATIVE_MARKERS):
        add("sad", "disappointed", 0.95, "negative_words_toward_mio", "angry")
    elif has_personal_compliment(text):
        closeness = max(0.0, min(1.0, (affection + familiarity - 60.0) / 100.0))
        direct_affection = has_direct_affection(text)
        happy_bonus = 0.10 * closeness
        if state.get("mood") == "happy":
            happy_bonus += 0.08
        if direct_affection and affection >= 65 and familiarity >= 55:
            happy_bonus += 0.12
        shy_score = 0.84 - 0.13 * closeness - (0.05 if state.get("mood") == "happy" else 0.0)
        happy_score = 0.63 + happy_bonus
        add("shy", "bashful", shy_score, "personal_compliment")
        add("happy", "warm", happy_score, "accept_personal_compliment")
    elif contains_any(text, ABILITY_COMPLIMENT_MARKERS):
        add("happy", "warm", 0.84, "ability_compliment")
        add("shy", "bashful", 0.58, "modest_about_ability")
    elif contains_any(text, GENERAL_PRAISE_MARKERS):
        add("happy", "cheerful", 0.76, "general_praise")
        add("touched", "warm", 0.55, "appreciate_praise")
    elif contains_any(text, CARE_MARKERS):
        add("touched", "warm", 0.86, "care_from_user")
        add("happy", "warm", 0.66, "happy_about_care")
    elif contains_any(text, ANNOYED_MARKERS):
        add("annoyed", "mild_annoyed", 0.78, "light_teasing")
        add("neutral", "conversational", 0.45, "take_teasing_lightly")
    elif contains_any(text, SURPRISE_MARKERS):
        add("surprised", "surprised", 0.8, "surprising_information")
        add("curious", "curious", 0.56, "follow_surprise")

    if contains_any(text, ADVICE_MARKERS):
        add("neutral", "thoughtful", 0.66, "advice_request")
    elif "?" in text or "？" in text or contains_any(text, QUESTION_MARKERS):
        add("neutral", "conversational", 0.46, "ordinary_question")

    if not candidates:
        add("neutral", "conversational", 0.3, "no_clear_signal")

    deduplicated = {}
    for item in candidates:
        key = (item["reaction"], item["voice_style"], item["user_mood"])
        if key not in deduplicated or item["score"] > deduplicated[key]["score"]:
            deduplicated[key] = item
    return sorted(deduplicated.values(), key=lambda item: item["score"], reverse=True)


def plan_turn_emotion(
    user_message,
    emotion=None,
    relationship=None,
) -> EmotionSignal:
    """在生成回复前规划本轮反应，不依赖 Mio 自己即将生成的措辞。"""
    text = user_message if isinstance(user_message, str) else ""
    emotional_text = emotion_text(text)
    state = normalize_emotion(emotion)
    relationship = relationship if isinstance(relationship, dict) else {}
    signal = _base_turn_signal()

    personal_praise = has_personal_compliment(text)
    ability_praise = contains_any(text, ABILITY_COMPLIMENT_MARKERS)
    general_praise = contains_any(text, GENERAL_PRAISE_MARKERS)
    candidates = score_turn_emotion_candidates(text, state, relationship)

    user_needs_support = False
    if contains_any(emotional_text, USER_SAD_MARKERS) or USER_SAD_PATTERN.search(emotional_text):
        signal["user_mood"] = "sad"
        signal["user_intensity"] = 0.82
        _set_modifier(signal, "worried", 0.78, 3)
        _set_voice_style(signal, "concerned", 0.82)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_sad"
        user_needs_support = True
    elif contains_any(emotional_text, USER_LONELY_MARKERS):
        signal["user_mood"] = "lonely"
        signal["user_intensity"] = 0.78
        _set_modifier(signal, "worried", 0.7, 3)
        _set_voice_style(signal, "concerned", 0.78)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_lonely"
        user_needs_support = True
    elif contains_any(emotional_text, USER_ANXIOUS_MARKERS) or USER_ANXIOUS_PATTERN.search(emotional_text):
        signal["user_mood"] = "anxious"
        signal["user_intensity"] = 0.78
        _set_modifier(signal, "worried", 0.74, 3)
        _set_voice_style(signal, "reassuring", 0.78)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_anxious"
        user_needs_support = True
    elif contains_any(emotional_text, USER_STRESSED_MARKERS):
        signal["user_mood"] = "stressed"
        signal["user_intensity"] = 0.58
        _set_modifier(signal, "worried", 0.46, 2)
        _set_voice_style(signal, "reassuring", 0.64)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_stressed"
        user_needs_support = True
    elif contains_any(emotional_text, USER_DISAPPOINTED_MARKERS):
        signal["user_mood"] = "disappointed"
        signal["user_intensity"] = 0.72
        _set_modifier(signal, "worried", 0.65, 3)
        _set_voice_style(signal, "concerned", 0.72)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_disappointed"
        user_needs_support = True
    elif contains_any(emotional_text, USER_TIRED_MARKERS):
        signal["user_mood"] = "tired"
        signal["user_intensity"] = 0.66
        _set_modifier(signal, "worried", 0.52, 2)
        _set_voice_style(signal, "reassuring", 0.68)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_tired"
        user_needs_support = True
    elif contains_any(emotional_text, USER_BORED_MARKERS):
        signal["user_mood"] = "bored"
        signal["user_intensity"] = 0.5
        _set_voice_style(signal, "thoughtful", 0.58)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_bored"
        user_needs_support = True
    elif contains_any(emotional_text, USER_ANGRY_MARKERS) or USER_ANGRY_PATTERN.search(emotional_text):
        signal["user_mood"] = "angry"
        signal["user_intensity"] = 0.72
        _set_modifier(signal, "worried", 0.58, 2)
        _set_voice_style(signal, "serious", 0.7)
        signal["reset_primary"] = True
        signal["reason"] = "user_is_angry"
        user_needs_support = True
    elif contains_any(emotional_text, USER_HAPPY_MARKERS) or USER_HAPPY_PATTERN.search(emotional_text):
        signal["user_mood"] = "happy"
        signal["user_intensity"] = 0.78
        _set_primary(signal, "happy", 0.7, "sharing_user_happiness", 4)
        _set_modifier(signal, "touched", 0.45, 2)
        _set_voice_style(signal, "cheerful", 0.74)

    if contains_any(text, DIRECTED_NEGATIVE_MARKERS):
        signal["user_mood"] = "angry"
        signal["user_intensity"] = max(signal["user_intensity"], 0.78)
        _set_primary(signal, "sad", 0.76, "negative_words_toward_mio", 4)
        _set_modifier(signal, "worried", 0.55, 2)
        _set_voice_style(signal, "disappointed", 0.78)
    elif user_needs_support:
        pass
    elif personal_praise:
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
    elif contains_any(text, CARE_MARKERS):
        _set_primary(signal, "happy", 0.62, "care_from_user", 4)
        _set_modifier(signal, "touched", 0.72, 3)
        _set_voice_style(signal, "warm", 0.76)
    elif contains_any(text, ANNOYED_MARKERS):
        _set_modifier(signal, "annoyed", 0.5, 2)
        _set_voice_style(signal, "mild_annoyed", 0.55)
        signal["reason"] = "light_teasing"
    elif contains_any(text, SURPRISE_MARKERS):
        _set_modifier(signal, "surprised", 0.62, 1)
        _set_voice_style(signal, "surprised", 0.68)
        signal["reason"] = "surprising_information"
    elif contains_any(text, ADVICE_MARKERS):
        _set_voice_style(signal, "thoughtful", 0.58)
        signal["reason"] = "advice_request"
    elif "?" in text or "？" in text or contains_any(text, QUESTION_MARKERS):
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
        contains_any(text, PROACTIVE_CONCERN_MARKERS)
        or event_emotion == "worried"
        or past_user_distress
    ):
        _set_modifier(signal, "worried", 0.68, 2)
        _set_voice_style(signal, "concerned", 0.76)
        signal["reason"] = "proactive_concern"
    elif event_emotion == "touched":
        _set_modifier(signal, "touched", 0.62, 2)
        _set_voice_style(signal, "warm", 0.72)
        signal["reason"] = "proactive_touched_event"
    elif event_emotion == "happy" or contains_any(text, PROACTIVE_HAPPY_MARKERS):
        _set_voice_style(signal, "cheerful", 0.68)
        signal["reason"] = "proactive_happy_topic"
    elif event_emotion == "shy":
        _set_voice_style(signal, "bashful", 0.68)
        signal["reason"] = "proactive_shy_topic"
    elif event_emotion == "sad":
        _set_voice_style(signal, "disappointed", 0.68)
        signal["reason"] = "proactive_sad_topic"
    elif state.get("mood") == "tired" or float(state.get("fatigue_strength", 0.0) or 0.0) >= 0.65:
        _set_voice_style(signal, "tired", 0.72)
        signal["reason"] = "proactive_fatigue"
    elif state.get("mood") == "sad":
        _set_voice_style(signal, "disappointed", max(0.55, state.get("mood_strength", 0.0)))
        signal["reason"] = "proactive_low_mood"
    elif contains_any(text, PROACTIVE_SURPRISE_MARKERS):
        _set_modifier(signal, "surprised", 0.58, 1)
        _set_voice_style(signal, "surprised", 0.64)
        signal["reason"] = "proactive_surprise"
    elif event_emotion == "curious":
        _set_modifier(signal, "curious", 0.42, 1)
        _set_voice_style(signal, "curious", 0.58)
        signal["reason"] = "proactive_curiosity"
    elif (
        contains_any(text, PROACTIVE_WARM_MARKERS)
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

    if contains_any(text, PROACTIVE_CONCERN_MARKERS):
        _set_modifier(signal, "worried", 0.58, 2)
        _set_voice_style(signal, "concerned", 0.68)
        signal["reason"] = "greeting_concern"
    elif state.get("mood") == "tired" or float(state.get("fatigue_strength", 0.0) or 0.0) >= 0.65:
        _set_voice_style(signal, "tired", 0.7)
        signal["reason"] = "greeting_tired"
    elif state.get("mood") == "sad":
        _set_voice_style(signal, "disappointed", max(0.55, state.get("mood_strength", 0.0)))
        signal["reason"] = "greeting_low_mood"
    elif state.get("mood") == "shy" or contains_any(text, SHY_REPLY_MARKERS):
        _set_voice_style(signal, "bashful", max(0.58, state.get("mood_strength", 0.0)))
        signal["reason"] = "greeting_bashful"
    elif state.get("mood") == "happy":
        _set_voice_style(signal, "cheerful", max(0.58, state.get("mood_strength", 0.0)))
        signal["reason"] = "greeting_cheerful"
    elif contains_any(text, GREETING_TIRED_MARKERS):
        _set_voice_style(signal, "tired", 0.66)
        signal["reason"] = "greeting_sounds_tired"
    elif contains_any(text, GREETING_HAPPY_MARKERS):
        _set_primary(signal, "happy", 0.52, "greeting_happy_to_see_user", 2)
        _set_voice_style(signal, "cheerful", 0.62)
    elif (
        contains_any(text, GREETING_WARM_MARKERS)
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
        has_personal_compliment(text)
        or contains_any(text, ABILITY_COMPLIMENT_MARKERS)
        or contains_any(text, GENERAL_PRAISE_MARKERS)
    )
    if not is_praise:
        return signal

    reply_is_shy = (
        contains_any(reply_text, SHY_REPLY_MARKERS)
        or bool(STAMMER_PATTERN.search(reply_text))
        or ("不好意思" in reply_text and "不用不好意思" not in reply_text)
    )
    reply_is_happy = contains_any(reply_text, HAPPY_REPLY_MARKERS)
    if reply_is_shy:
        _set_primary(signal, "shy", 0.86, "shy_reaction_to_praise", 3)
        _set_voice_style(
            signal,
            "embarrassed" if contains_any(reply_text, ("害羞", "脸红", "红着脸")) else "bashful",
            0.84,
        )
    elif reply_is_happy:
        _set_primary(signal, "happy", 0.7, "accepted_compliment", 4)
        _set_voice_style(
            signal,
            "warm" if has_personal_compliment(text) else "cheerful",
            0.7,
        )
    return signal
