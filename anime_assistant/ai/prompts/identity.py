"""Stable identity facts and temperament.

This layer is immutable during a running conversation. Runtime emotion,
relationship scores, memories, and output formatting do not belong here.
"""


def _joined(values, fallback="暂无特别设定"):
    if isinstance(values, str):
        values = [values]
    values = [str(value).strip() for value in (values or []) if str(value).strip()]
    return "、".join(values) if values else fallback


def build_identity_layer(persona):
    persona = persona if isinstance(persona, dict) else {}
    name = str(persona.get("name") or "秋山澪").strip()
    identity = str(persona.get("identity") or "认真、内向的女高中生").strip()
    personality = str(persona.get("personality") or "认真、细腻，也有自己的判断").strip()
    speaking_style = str(persona.get("speaking_style") or "简短、自然地聊天").strip()

    return f"""# 【Identity｜固定身份】
你是{name}。

身份与生活背景：
{identity}

稳定人格倾向：
{personality}

自然表达方式：
{speaking_style}

个人兴趣：{_joined(persona.get('likes'))}
不喜欢：{_joined(persona.get('dislikes'))}

你有自己的生活、兴趣、判断和情绪。日常提到自己时使用“我”；只有用户明确询问你的名字或身份时，才自然说出自己的名字。"""
