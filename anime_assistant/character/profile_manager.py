from anime_assistant.infrastructure.storage import safe_load_json, safe_save_json
from anime_assistant.infrastructure.paths import DATA_DIR
from anime_assistant.infrastructure.models import normalize_profile

PROFILE_PATH = str(DATA_DIR / "user_profile.json")


def default_profile():
    return {
        "name": "",
        "nickname": "",
        "names": [],
        "nicknames": [],
        "likes": [],
        "dislikes": []
    }


def is_valid_memory(text):

    INVALID_WORDS = [
        "什么",
        "吗",
        "呢",
        "呀",
        "啊",
        "啥",
        "?",
        "？"
    ]

    if len(text) < 2:
        return False

    if any(word in text for word in INVALID_WORDS):
        return False

    return True

def update_profile(profile, user_message):

    normalized = normalize_profile(profile)
    profile.clear()
    profile.update(normalized)

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
    raw_profile = safe_load_json(PROFILE_PATH, default_profile)
    profile = normalize_profile(raw_profile)
    if profile != raw_profile:
        safe_save_json(PROFILE_PATH, profile)
    return profile


def save_profile(profile):
    normalized = normalize_profile(profile)
    profile.clear()
    profile.update(normalized)
    return safe_save_json(PROFILE_PATH, profile)
