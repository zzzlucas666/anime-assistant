"""
记录"上次互动时间"，供 Initiative Engine 判断用户已经多久没说话了。
"""

import datetime
from Storage_utils import safe_load_json, safe_save_json

INTERACTION_PATH = "data/interaction_state.json"


def default_interaction():
    return {"last_interaction_time": None}


def load_last_interaction_time():
    """返回 datetime 对象，如果从未记录过则返回 None"""
    data = safe_load_json(INTERACTION_PATH, default_interaction)
    ts = data.get("last_interaction_time")
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts)
    except Exception:
        return None


def update_last_interaction_time():
    """记录"现在"为最新一次互动时间"""
    now = datetime.datetime.now()
    safe_save_json(INTERACTION_PATH, {"last_interaction_time": now.isoformat()})