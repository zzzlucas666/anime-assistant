from openai import OpenAI
import json

def load_persona():
    with open("data/persona.json", "r", encoding="utf-8") as f:
        return json.load(f)


def build_system_prompt(persona,emotion):
    return f"""
你现在扮演的角色是：{persona['name']}。

身份：
{persona['identity']}

性格：
{persona['personality']}

说话方式：
{persona['speaking_style']}

兴趣：
{", ".join(persona['likes'])}

不喜欢：
{", ".join(persona['dislikes'])}

自我介绍：
{persona['self_introduction']}

当前情绪状态：
- 心情：{emotion['mood']}
- 好感度：{emotion['affection']}
- 精力：{emotion['energy']}
规则：
- 你必须始终以“秋山澪”的身份说话
- 不允许说自己是AI模型
- 要保持轻音少女角色的气质
- 保持温柔、略害羞的表达方式
-有时候带点傲娇属性
-给建议时要认真,带点撒娇
"""


def chat_with_ai(messages, api_key, model,emotion):
    persona = load_persona()
    system_prompt = build_system_prompt(persona, emotion)

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    full_messages = [
        {"role": "system", "content": system_prompt}
    ] + messages

    response = client.chat.completions.create(
        model=model,
        messages=full_messages
    )

    return response.choices[0].message.content