from openai import OpenAI
import json
import os


def extract_event(api_key, model, user_message, ai_reply):
    """
    用 AI 判断这轮对话里是否发生了"值得记住的事件"，
    覆盖范围比之前的规则匹配（只认"喜欢"+"吗"）广得多，
    比如：用户提到的计划、烦恼、重要日子、对AI的评价、新信息等。
    """

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    prompt = f"""
你是一个事件记忆提取器，负责从一轮对话中判断是否发生了"值得长期记住的事件"。

值得记住的事件包括（但不限于）：
- 用户表达了喜欢/讨厌某件事物
- 用户分享了计划、烦恼、心事、重要的事情
- 用户提到了重要日期（生日、纪念日等）
- 用户对AI表达了关心、感谢、夸奖或不满
- 用户透露了新的个人信息或重要经历

不值得记住的事件：
- 单纯的寒暄、闲聊、无实质内容的对话

请分析下面这轮对话，返回严格的JSON格式：

{{
  "is_event": true 或 false,
  "event": "用一句话概括这件事（如果 is_event 为 false，留空字符串）",
  "emotion": "这件事对应的情绪标签，例如 happy / curious / sad / touched / neutral",
  "impact": "increase_bond 或 increase_affinity 或 none",
  "importance": 0.0到1.0之间的数字，表示这件事的重要程度
}}

判断标准：
- increase_bond：能显著增进感情的事件（用户表达关心、分享心事、确认情感等），importance 通常 >= 0.7
- increase_affinity：一般的好感类事件（提到喜好等），importance 通常在 0.4~0.7
- none：普通对话，importance 通常 < 0.4

用户说的话：
{user_message}

AI的回复：
{ai_reply}

只返回JSON，不要解释，不要markdown。
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt}
        ],
        temperature=0
    )

    content = response.choices[0].message.content

    try:
        result = json.loads(content)
    except Exception:
        return None

    if not result.get("is_event"):
        return None

    return {
        "event": result.get("event", ""),
        "emotion": result.get("emotion", "neutral"),
        "impact": result.get("impact", "none"),
        "importance": result.get("importance", 0.3)
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


def load_recent_events(limit=5, min_importance=0.5):
    """
    读取近期 + 重要的事件，供 chat.py 拼进 system prompt，
    让 AI 能"记得"并主动提起之前发生过的事。

    - 只挑选 importance >= min_importance 的事件（过滤掉"普通对话"这类噪音）
    - 按时间顺序保留最近 limit 条（越新越靠后）
    """
    try:
        with open("data/event_memory.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    important_events = [
        e for e in data
        if isinstance(e, dict) and e.get("importance", 0) >= min_importance
    ]

    return important_events[-limit:]