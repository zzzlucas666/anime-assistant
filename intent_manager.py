from openai import OpenAI
import json

INTENT_SCHEMA = {
    "intent": "",
    "confidence": 0.0,
    "slots": {}
}


def detect_intent(api_key, model, user_message, emotion, profile):

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

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
- affection: {emotion['affection']}
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

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt}
        ],
        temperature=0
    )

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except:
        return {
            "intent": "chat",
            "confidence": 0.5,
            "slots": {}
        }