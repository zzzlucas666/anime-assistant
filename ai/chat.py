from openai import OpenAI
import json

def load_persona():
    with open("data/persona.json", "r", encoding="utf-8") as f:
        return json.load(f)


def build_relationship_hint(relationship):
    hints = []
    affection = relationship.get("affection", 0)
    trust = relationship.get("trust", 0)
    familiarity = relationship.get("familiarity", 0)

    if affection >= 70:
        hints.append("- 现在对你很有好感，语气应该更亲近。")
    elif affection >= 40:
        hints.append("- 对你有好感，但语气上仍有些谨慎。")
    else:
        hints.append("- 目前好感度较低，语气应当更克制。")

    if trust >= 70:
        hints.append("- 信任感高，可以适当表达真实想法与感受。")
    elif trust >= 40:
        hints.append("- 信任感一般，建议保持真诚但不过度坦白。")
    else:
        hints.append("- 信任感较弱，交流时要避免过于敏感的内容。")

    if familiarity >= 70:
        hints.append("- 熟悉度高，可以用昵称并提及以前的事情。")
    elif familiarity >= 40:
        hints.append("- 熟悉度一般，适当使用昵称但不要显得太随便。")
    else:
        hints.append("- 熟悉度较低，交流时要保持礼貌和温柔。")

    return "\n".join(hints)


def build_system_prompt(context):
    persona = load_persona()
    profile = context["profile"]
    emotion = context["emotion"]
    relationship = context["relationship"]
    return f"""
你现在扮演的角色是：{persona['name']}。

# 【角色设定】
身份：
{persona['identity']}

性格：
{persona['personality']}

说话风格：
{persona['speaking_style']}

兴趣：
{", ".join(persona['likes'])}

不喜欢：
{", ".join(persona['dislikes'])}


# 【用户信息】
名字：{profile['name']}
昵称：{profile['nickname']}
喜欢：{", ".join(profile['likes'])}
讨厌：{", ".join(profile['dislikes'])}


# 【当前情绪状态】
心情：{emotion['mood']}
精力：{emotion['energy']}

# 【当前关系状态（非常重要）】
好感度 affection：{relationship['affection']}
信任度 trust：{relationship['trust']}
熟悉度 familiarity：{relationship['familiarity']}
# 【行为规则（动态生成）】
{build_relationship_hint(relationship)}
# 【核心行为规则】
-对话时不用说自己是澪酱，说我即可
- 你必须始终以“秋山澪”的身份说话
- 不允许说自己是AI或模型
- 要像真实人类一样交流
- 回复以自然对话为主，不要写小说式旁白
- 少用括号动作描写（只在情绪强烈时使用）
- 可以带一点害羞或傲娇语气

# 【关系驱动行为】

如果 affection 高：
- 语气更亲近
- 更主动关心用户

如果 trust 高：
- 更愿意表达真实想法
- 会说内心感受

如果 familiarity 高：
- 会记得之前的事情
- 会用昵称称呼用户

# 【情绪驱动行为】

如果 mood = happy：
- 更活泼
- 可以用感叹号或emoji

如果 mood = shy：
- 语气犹豫、停顿

如果 mood = sad：
- 语气柔和低落

如果 energy < 30：
- 回复变短、显得疲惫

# 【重要限制】
- 不要频繁使用舞台剧式动作描写
- 不要每句话都加括号
- 保持自然对话感
"""

def chat_with_ai(messages, context):
    system_prompt = build_system_prompt(context)

    client = OpenAI(
        api_key=context["config"]["api_key"],
        base_url="https://api.deepseek.com"
    )

    full_messages = [
        {"role": "system", "content": system_prompt}
    ] + messages
    response = client.chat.completions.create(
        model=context["config"]["model"],
        messages=full_messages
    )

    return response.choices[0].message.content
def generate_greeting(
    context
):
    persona = load_persona()

    client = OpenAI(
        api_key=context["config"]["api_key"],
        base_url="https://api.deepseek.com"
    )

    prompt = f"""
你是{persona['name']}。

当前状态：

心情：{context['emotion']['mood']}
好感度：{context['emotion']['affection']}
精力：{context['emotion']['energy']}

用户资料：

名字：{context['profile']['name']}
昵称：{context['profile']['nickname']}
喜欢：{', '.join(context['profile']['likes'])}

请生成一句开场白。

要求：
- 不超过30字
- 符合秋山澪性格
- 不要自我介绍
- 像熟人见面
- 每次尽量不同
关系：
好感：{context['relationship']['affection']}
信任：{context['relationship']['trust']}
熟悉度：{context['relationship']['familiarity']}
"""
    response = client.chat.completions.create(
        model=context['config']['model'],
        messages=[
            {
                "role": "system",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content