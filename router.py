def handle_intent(intent, clean_message, profile, emotion):
    
    if intent == "get_profile":

        likes = profile.get("likes", [])
        dislikes = profile.get("dislikes", [])
        nickname = profile.get("nickname", "")
        name = profile.get("name", "")

        if "喜欢" in clean_message:
            return f"你喜欢：{', '.join(likes) if likes else '暂无'}"

        if "讨厌" in clean_message:
            return f"你讨厌：{', '.join(dislikes) if dislikes else '暂无'}"

        if "昵称" in clean_message:
            return f"你的昵称是：{nickname or '暂无'}"

        if "名字" in clean_message:
            return f"你的名字是：{name or '暂无'}"

    return None