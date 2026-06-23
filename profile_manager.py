import json

def update_profile(profile, user_message):

    # 我叫什么
    if user_message.startswith("我叫"):
        profile["name"] = (
            user_message
            .replace("我叫", "")
            .strip()
        )

    # 我喜欢什么
    elif user_message.startswith("我喜欢"):
        like = (
            user_message
            .replace("我喜欢", "")
            .strip()
        )

        if like not in profile["likes"]:
            profile["likes"].append(like)

    # 我讨厌什么
    elif user_message.startswith("我讨厌"):
        dislike = (
            user_message
            .replace("我讨厌", "")
            .strip()
        )

        if dislike not in profile["dislikes"]:
            profile["dislikes"].append(dislike)

    # 昵称
    elif user_message.startswith("你可以叫我"):
        profile["nickname"] = (
            user_message
            .replace("你可以叫我", "")
            .strip()
        )

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


