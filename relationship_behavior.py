def build_relationship_hint(relationship):
    hint = []

    affection = relationship["affection"]
    trust = relationship["trust"]
    familiarity = relationship["familiarity"]

    # affection
    if affection >= 80:
        hint.append("语气非常亲近，像很熟的人")
    elif affection >= 50:
        hint.append("语气自然友好")
    else:
        hint.append("语气略微保持距离")

    # trust
    if trust >= 80:
        hint.append("可以表达真实情绪和内心想法")
    elif trust >= 50:
        hint.append("偶尔表达真实感受")
    else:
        hint.append("避免过度暴露内心")

    # familiarity
    if familiarity >= 50:
        hint.append("会提及过去对话内容")
    elif familiarity >= 20:
        hint.append("偶尔记得用户习惯")
    else:
        hint.append("像初次认识")

    return "\n".join(hint)