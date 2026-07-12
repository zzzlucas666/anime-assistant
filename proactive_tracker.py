"""
主动消息的冷却限制——避免触发条件持续满足时（比如 mood 一直 sad），
Initiative Engine 无限期地每隔几十分钟就调一次 AI。

两道闸：
1. 两次主动消息之间至少间隔 MIN_INTERVAL_MINUTES
2. 每天最多触发 MAX_PER_DAY 次（按自然日计算，过了凌晨自动重置）
"""

import datetime
from app_paths import DATA_DIR
from data_models import normalize_proactive_state
from Storage_utils import safe_load_json, safe_save_json
from logger_utils import get_logger

logger = get_logger(__name__)

PROACTIVE_STATE_PATH = str(DATA_DIR / "proactive_state.json")

MIN_INTERVAL_MINUTES = 60   # 两次主动消息之间至少间隔1小时
MAX_PER_DAY = 3              # 每天最多主动找用户聊3次


def default_proactive_state():
    return {
        "last_proactive_time": None,
        "count_today": 0,
        "count_date": None  # 记录 count_today 是哪一天的计数，跨天自动重置
    }


def _load_state():
    raw_state = safe_load_json(PROACTIVE_STATE_PATH, default_proactive_state)
    state = normalize_proactive_state(raw_state)
    if state != raw_state:
        safe_save_json(PROACTIVE_STATE_PATH, state)
    return state


def _save_state(state):
    normalized = normalize_proactive_state(state)
    state.clear()
    state.update(normalized)
    return safe_save_json(PROACTIVE_STATE_PATH, state)


def can_trigger_proactive(
    min_interval_minutes=MIN_INTERVAL_MINUTES,
    max_per_day=MAX_PER_DAY
):
    """
    判断现在能不能触发一次新的主动消息。
    只读不写，调用这个函数本身不会消耗"今日额度"。
    """
    state = _load_state()
    now = datetime.datetime.now()
    today_str = now.date().isoformat()

    # 跨天了，今日计数视为0（实际重置发生在 record_proactive_trigger 里）
    count_today = state.get("count_today", 0) if state.get("count_date") == today_str else 0

    if count_today >= max_per_day:
        logger.info("主动消息已达今日上限（%d/%d），暂不触发。", count_today, max_per_day)
        return False

    last_time_str = state.get("last_proactive_time")
    if last_time_str:
        try:
            last_time = datetime.datetime.fromisoformat(last_time_str)
            elapsed_minutes = (now - last_time).total_seconds() / 60
            if elapsed_minutes < min_interval_minutes:
                logger.info(
                    "距上次主动消息只过了 %.1f 分钟（需要 >= %d 分钟），暂不触发。",
                    elapsed_minutes, min_interval_minutes
                )
                return False
        except Exception as e:
            logger.warning("解析上次主动消息时间失败：%s", e)

    return True


def record_proactive_trigger():
    """记录一次主动消息已经发出，更新冷却计时和今日计数"""
    now = datetime.datetime.now()
    today_str = now.date().isoformat()

    state = _load_state()
    count_today = state.get("count_today", 0) if state.get("count_date") == today_str else 0

    state["last_proactive_time"] = now.isoformat()
    state["count_today"] = count_today + 1
    state["count_date"] = today_str

    _save_state(state)
    logger.info("已记录一次主动消息触发，今日第 %d 次。", state["count_today"])
