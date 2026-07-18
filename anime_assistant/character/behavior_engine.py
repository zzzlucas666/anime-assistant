def build_behavior_profile(relationship, emotion):
    
    behavior = {
        "warmth": 0,
        "formality": 0,
        "initiative": 0,
        "verbosity": 0,
        "emotion_expression": 0
    }

    affection = relationship["affection"]
    trust = relationship["trust"]
    familiarity = relationship["familiarity"]

    mood = emotion["mood"]

    # =====================
    # ❤️ affection → warmth
    # =====================
    behavior["warmth"] = affection / 100

    # =====================
    # 🤝 trust → initiative
    # =====================
    behavior["initiative"] = trust / 100

    # =====================
    # 🧠 familiarity → verbosity
    # =====================
    behavior["verbosity"] = familiarity / 100

    # =====================
    # 😳 mood → emotion expression
    # =====================
    if mood == "happy":
        behavior["emotion_expression"] = 0.8
    elif mood == "shy":
        behavior["emotion_expression"] = 0.4
    elif mood == "sad":
        behavior["emotion_expression"] = 0.2
    else:
        behavior["emotion_expression"] = 0.5

    # =====================
    # ❄️ formality（反向关系）
    # =====================
    behavior["formality"] = 1 - (affection / 100)

    return behavior