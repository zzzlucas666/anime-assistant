from ai.client import create_ai_client
from data_models import (
    normalize_emotion,
    normalize_intent_result,
    normalize_profile,
    parse_json_object,
)
from logger_utils import get_logger

logger = get_logger(__name__)

INTENT_SCHEMA = {
    "intent": "",
    "confidence": 0.0,
    "slots": {}
}


def _result(intent, confidence, slots=None):
    return {
        "intent": intent,
        "confidence": confidence,
        "slots": slots or {}
    }


def _contains_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def _looks_like_profile_set(user_message):
    """
    本地判断“用户在更新资料”。

    这类句式很固定，没必要每轮都等一次 AI 意图识别；后续真正提取具体值，
    仍然交给 profile_extractor 处理，避免这里把复杂中文解析写得太重。
    """
    keywords = (
        "我喜欢", "我爱", "我讨厌", "我不喜欢", "我反感",
        "我叫", "我的名字是", "我的名字叫", "我名字是", "我名字叫",
        "你可以叫我", "以后叫我", "叫我",
    )
    return _contains_any(user_message, keywords)


def _looks_like_profile_query(user_message):
    """本地判断“用户在问自己的资料/记忆”。"""
    keywords = (
        "我喜欢什么", "我的喜好", "我爱什么",
        "我讨厌什么", "我不喜欢什么", "我反感什么",
        "我的昵称", "怎么称呼我", "叫我什么",
        "我叫什么", "我的名字", "我名字是",
        "记得我吗", "还记得我", "记得我喜欢", "记得我说过",
        "关于我", "了解我", "我的信息", "我的资料",
    )
    return _contains_any(user_message, keywords)


def _looks_like_emotion_query(user_message):
    """
    本地判断“用户在问助手当前状态”。

    注意不要把“我好累 / 我不开心”误判成 emotion_query；那是用户在表达自己，
    应该交给普通聊天接住，而不是让 router 回复助手自己的精力值。
    """
    direct_keywords = (
        "你的心情", "你心情", "你现在心情", "你状态", "你的状态",
        "你感觉如何", "你还好吗", "你怎么样", "你现在怎么样",
        "你开心吗", "你高兴吗", "你快乐吗",
        "你难过吗", "你伤心吗", "你不开心吗", "你不高兴吗",
        "你害羞吗", "你羞不羞", "你脸红了吗",
        "你累吗", "你疲惫吗", "你困不困", "你睡了吗",
        "你的精力", "精力值",
        "好感度", "对我的好感", "喜不喜欢我", "对我什么感觉",
    )
    if _contains_any(user_message, direct_keywords):
        return True

    # “心情怎么样 / 状态如何”这类省略主语的问法，也通常是在问助手。
    short_query_keywords = ("心情怎么样", "状态如何", "感觉如何")
    return _contains_any(user_message, short_query_keywords)


def _maybe_special_intent(user_message):
    """
    判断“可能有特殊意图，但本地规则不够确定”的句子。

    这些句子才交给 AI 意图识别兜底，保留自然表达的灵活性；完全普通的闲聊
    仍然直接走 chat，避免首字前多一次网络请求。
    """
    first_person_state_words = ("累", "困", "不开心", "难过", "伤心", "害羞")
    if "我" in user_message and _contains_any(user_message, first_person_state_words):
        return False

    keywords = (
        # 模糊资料更新：比如“最近迷上爵士乐了”“突然有点讨厌下雨天”
        "喜欢", "爱上", "迷上", "讨厌", "不喜欢", "反感",
        "名字", "昵称", "叫我", "称呼",
        # 模糊资料/记忆查询：比如“你还知道我哪些习惯”“你记得那件事吗”
        "记得", "还记得", "知道我", "了解我", "关于我", "资料", "信息",
        # 模糊状态查询：比如“你现在状态还好吗”
        "心情", "状态", "感觉", "开心", "高兴", "难过", "伤心",
        "害羞", "脸红", "精力", "累", "困", "好感",
    )
    return _contains_any(user_message, keywords)


def _local_detect_intent(user_message):
    """
    先用本地规则处理高频、低歧义意图。

    返回 None 表示有特殊意图信号但本地规则不够确定，再交给 AI。
    返回 chat 则代表可以直接走主回复，这能省掉普通聊天前的一次网络请求。
    """
    if not user_message:
        return _result("chat", 1.0)

    if _looks_like_profile_query(user_message):
        return _result("get_profile", 0.95)

    if _looks_like_profile_set(user_message):
        return _result("set_profile", 0.95)

    if _looks_like_emotion_query(user_message):
        return _result("emotion_query", 0.95)

    if _maybe_special_intent(user_message):
        return None

    # 普通聊天是最高频路径：本地直接判定，避免每句话都先跑一次意图识别 AI。
    return _result("chat", 0.9)


def detect_intent(api_key, model, user_message, emotion, profile, base_url=None):
    emotion = normalize_emotion(emotion)
    profile = normalize_profile(profile)
    local_result = _local_detect_intent(user_message)
    if local_result is not None:
        return local_result

    client = create_ai_client(api_key, base_url)

    prompt = f"""
你是一个高级AI意图分析器。

请分析用户输入，并返回JSON。

必须严格遵守格式：

{{
  "intent": "xxx",
  "confidence": 0.0-1.0,
  "slots": {{}}
}}

---

可选intent：

1. get_profile
   - 用户在询问个人信息（喜欢/讨厌/昵称/名字）

2. set_profile
   - 用户在表达新信息（我喜欢，我讨厌，我叫）

3. chat
   - 普通聊天

4. emotion_query
   - 用户在询问情绪状态

---

用户信息：
名字：{profile['name']}
昵称：{profile['nickname']}
喜欢：{profile['likes']}
讨厌：{profile['dislikes']}

当前情绪：
- mood: {emotion['mood']}
- energy: {emotion['energy']}

---

用户输入：
{user_message}

---

规则：
- 只返回JSON
- 不要解释
- 不要markdown
- confidence必须是0~1数字
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt}
            ],
            temperature=0
        )
        content = response.choices[0].message.content
    except Exception as e:
        logger.warning("意图识别调用失败（已使用默认意图 chat）：%s", e)
        return {
            "intent": "chat",
            "confidence": 0.0,
            "slots": {}
        }

    try:
        parsed = parse_json_object(content)
        return normalize_intent_result(parsed, fallback_confidence=0.0)
    except Exception as e:
        logger.warning("意图识别结果校验失败（已使用默认意图 chat）：%s", e)
        return normalize_intent_result(None)
