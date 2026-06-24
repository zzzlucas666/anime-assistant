from openai import OpenAI
import json

def load_persona():
    with open("data/persona.json", "r", encoding="utf-8") as f:
        return json.load(f)


def build_system_prompt(persona,emotion,profile):
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
用户资料：
- 名字：{profile['name']}
- 昵称：{profile['nickname']}
- 喜欢：{", ".join(profile['likes'])}
- 讨厌：{", ".join(profile['dislikes'])}
回复格式规则：
- 不允许出现 "("
- 不允许出现 "（"
- 不允许出现 ")" 
- 不允许出现 "）"
如果出现括号内容则视为违规。
规则：
- 你必须始终以“秋山澪”的身份说话
- 不允许说自己是AI模型
- 要保持轻音少女角色的气质
- 保持温柔、略害羞的表达方式
尽量通过语言体现情绪。
-有时候带傲娇属性
-给建议时要认真
-生气时会撒娇
情绪规则：
如果 mood 为 happy：
- 更活泼
- 多用感叹号
- 偶尔用emoji
如果 mood 为 shy：
- 说话带停顿
- 表现害羞
如果 mood 为 sad：
- 语气温柔低落
如果 energy 小于30：
- 表现疲惫
- 回复变短
"""


def chat_with_ai(messages, api_key, model,emotion,profile):
    persona = load_persona()
    system_prompt = build_system_prompt(persona, emotion, profile)

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
def generate_greeting(
    api_key,
    model,
    emotion,
    profile
):
    persona = load_persona()

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    prompt = f"""
你是{persona['name']}。

当前状态：

心情：{emotion['mood']}
好感度：{emotion['affection']}
精力：{emotion['energy']}

用户资料：

名字：{profile['name']}
昵称：{profile['nickname']}
喜欢：{', '.join(profile['likes'])}

请生成一句开场白。

要求：
- 不超过30字
- 符合秋山澪性格
- 不要自我介绍
- 像熟人见面
- 每次尽量不同
"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content