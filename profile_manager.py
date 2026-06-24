import json
def is_valid_memory(text):

    INVALID_WORDS = [
        "什么",
        "吗",
        "呢",
        "呀",
        "啊",
        "啥"
        "?",
        "？"
    ]

    if len(text) < 2:
        return False

    if any(word in text for word in INVALID_WORDS):
        return False

    return True

def update_profile(profile, user_message):

    # 我叫什么
    if user_message.startswith("我叫"):
        
        name = (
            user_message
            .replace("我叫", "")
            .strip()
        )

        if is_valid_memory(name) and name not in profile["names"]:
            profile["name"] = name

    # 我喜欢什么
    elif user_message.startswith("我喜欢"):
        like = (
            user_message
            .replace("我喜欢", "")
            .strip()
        )

        if is_valid_memory(like) and like not in profile["likes"]:
            profile["likes"].append(like)

    # 我讨厌什么
    elif user_message.startswith("我讨厌"):
        dislike = (
            user_message
            .replace("我讨厌", "")
            .strip()
        )

        if is_valid_memory(dislike) and dislike not in profile["dislikes"]:
            profile["dislikes"].append(dislike)

    # 昵称
    elif user_message.startswith("你可以叫我"):
        nickname = (
            user_message
            .replace("你可以叫我", "")
            .strip()
        )

        if is_valid_memory(nickname) and nickname not in profile["nicknames"]:
            profile["nickname"] = nickname
            profile["nicknames"].append(nickname)
    return profile
def load_profile():
    with open(
        "data/user_profile.json",
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


def save_profile(profile):
    with open(
        "data/user_profile.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            profile,
            file,
            ensure_ascii=False,
            indent=4
        )


