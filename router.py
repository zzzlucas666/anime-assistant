def handle_intent(intent, clean_message, profile, emotion):

    if intent == "get_profile":

        likes = profile.get("likes", [])
        dislikes = profile.get("dislikes", [])
        nickname = profile.get("nickname", "")
        name = profile.get("name", "")

        # 喜欢
        if any(k in clean_message for k in ["喜欢什么", "我喜欢", "我的喜好", "我爱什么"]):
            return f"你喜欢：{', '.join(likes) if likes else '暂无'}"

        # 讨厌
        if any(k in clean_message for k in ["讨厌什么", "我讨厌", "我不喜欢", "我反感"]):
            return f"你讨厌：{', '.join(dislikes) if dislikes else '暂无'}"

        # 昵称
        if any(k in clean_message for k in ["昵称", "怎么称呼我", "叫我什么"]):
            return f"你的昵称是：{nickname or '暂无'}"

        # 名字
        if any(k in clean_message for k in ["我叫什么", "我的名字", "我名字是"]):
            return f"你的名字是：{name or '暂无'}"

        # 记不记得我 / 还记得吗
        if any(k in clean_message for k in ["记得我吗", "还记得我", "记得我喜欢", "记得我说过"]):
            if not likes and not dislikes and not name:
                return "嗯……还没怎么了解你呢，多跟我聊聊吧。"
            parts = []
            if name:
                parts.append(f"你叫{name}")
            if likes:
                parts.append(f"喜欢{', '.join(likes)}")
            if dislikes:
                parts.append(f"讨厌{', '.join(dislikes)}")
            return "当然记得，" + "，".join(parts) + "。"

        # 兜底：把已知信息整体报一下
        if any(k in clean_message for k in ["关于我", "了解我", "我的信息", "我的资料"]):
            parts = []
            if name:
                parts.append(f"名字是{name}")
            if nickname:
                parts.append(f"昵称是{nickname}")
            if likes:
                parts.append(f"喜欢{', '.join(likes)}")
            if dislikes:
                parts.append(f"讨厌{', '.join(dislikes)}")
            if not parts:
                return "目前还不太了解你，多和我说说吧。"
            return "我知道的是：" + "，".join(parts) + "。"

    elif intent == "emotion_query":

        # 追问/叙事型问题（为什么、怎么了、发生了什么），需要 AI 自由发挥讲故事，
        # router 没有"为什么"的答案，交还给 AI，不要用固定模板糊弄过去
        narrative_words = ["为什么", "为啥", "怎么了", "发生", "什么事", "出什么事"]
        if any(k in clean_message for k in narrative_words):
            return None

        mood = emotion.get("mood", "")
        energy = emotion.get("energy", "")
        affection = emotion.get("affection", "")

        mood_text = {
            "happy": "心情很好",
            "shy": "有点害羞",
            "sad": "心情不太好",
            "tired": "感觉有点累",
        }.get(mood, f"心情是 {mood}")

        # 精力 / 累
        if any(k in clean_message for k in ["精力", "累", "疲惫", "困不困", "睡了吗"]):
            return f"现在精力值是 {energy}/100。"

        # 好感度
        if any(k in clean_message for k in ["好感", "喜不喜欢我", "对我什么感觉"]):
            return f"目前对你的好感度是 {affection}/100。"

        # 是否开心
        if any(k in clean_message for k in ["开心", "高兴", "快乐"]):
            if mood == "happy":
                return "嗯，现在心情很好！"
            else:
                return f"现在还说不上很开心，{mood_text}。"

        # 是否难过 / 伤心
        if any(k in clean_message for k in ["难过", "伤心", "不开心", "不高兴"]):
            if mood == "sad":
                return "嗯…现在心情确实不太好。"
            else:
                return f"没有不开心呀，{mood_text}。"

        # 是否害羞
        if any(k in clean_message for k in ["害羞", "羞不羞", "脸红"]):
            if mood == "shy":
                return "有点……有点害羞啦。"
            else:
                return f"现在倒没有害羞，{mood_text}。"

        # 笼统的"心情怎么样" / "你现在怎么样" / "状态如何"
        if any(k in clean_message for k in ["心情", "状态", "怎么样", "感觉如何", "你还好吗", "怎么"]):
            return f"现在{mood_text}，精力值 {energy}/100。"

        # 默认兜底
        return f"现在{mood_text}，精力值 {energy}/100。"

    return None