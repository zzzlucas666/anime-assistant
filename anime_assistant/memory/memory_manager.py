from pathlib import Path

from anime_assistant.infrastructure.storage import safe_load_json, safe_save_json
from anime_assistant.ai.fallbacks import is_transient_fallback
from anime_assistant.infrastructure.paths import DATA_DIR
from anime_assistant.infrastructure.models import normalize_messages
from anime_assistant.infrastructure.logging import get_logger


logger = get_logger(__name__)

MEMORY_PATH = str(DATA_DIR / "conversation_history.json")
MAX_HISTORY = 50
STYLE_HISTORY_VERSION = 2


def default_history():
    return []


def clean_history(history):
    return [
        message
        for message in normalize_messages(history)
        if not (
            message["role"] == "assistant"
            and is_transient_fallback(message["content"])
        )
    ]


def _style_migration_paths():
    memory_path = Path(MEMORY_PATH)
    marker_path = memory_path.with_name(
        f"{memory_path.stem}.style-v{STYLE_HISTORY_VERSION}.json"
    )
    backup_path = memory_path.with_name(
        f"{memory_path.stem}.pre-mio-style-v{STYLE_HISTORY_VERSION}.json"
    )
    return str(marker_path), str(backup_path)


def _looks_style_polluted(history):
    """识别旧版长篇、音乐比喻密集的助手历史，避免误清理正常新对话。"""
    assistant_messages = [
        item["content"] for item in history if item.get("role") == "assistant"
    ]
    if len(assistant_messages) < 5:
        return False
    average_length = sum(map(len, assistant_messages)) / len(assistant_messages)
    music_heavy = sum(
        any(term in content for term in ("贝斯", "琴弦", "低音"))
        for content in assistant_messages
    )
    return average_length > 90 or music_heavy >= 3


def _migrate_legacy_style_history(raw_history):
    """首次升级到新口吻时备份并重置受污染的短期历史。"""
    marker_path, backup_path = _style_migration_paths()
    marker = safe_load_json(marker_path, lambda: {})
    if marker.get("version") == STYLE_HISTORY_VERSION:
        return raw_history

    normalized = clean_history(raw_history)
    if _looks_style_polluted(normalized):
        if not safe_save_json(backup_path, raw_history):
            logger.error("旧风格历史备份失败，已取消自动重置：%s", backup_path)
            return raw_history
        if not safe_save_json(MEMORY_PATH, []):
            logger.error("短期历史重置失败，将继续使用原历史。")
            return raw_history
        raw_history = []
        logger.info(
            "已备份并重置旧风格短期历史：messages=%d backup=%s",
            len(normalized),
            backup_path,
        )

    safe_save_json(marker_path, {"version": STYLE_HISTORY_VERSION})
    return raw_history


def save_memory(conversation_history):
    """
    清洗 + 截断到最近 MAX_HISTORY 条，存盘。

    返回 (trimmed_history, overflow_messages)：
    - trimmed_history：与传入的 conversation_history 是同一个列表对象。
      清洗和截断会在原列表上就地完成，确保 Orchestrator 和
      InitiativeEngine 等多个持有者始终看到同一份历史，不会因为
      某一方重新赋值而分叉。
    - overflow_messages：被截断丢弃掉的那部分旧消息，供 long_term_memory
      压缩成摘要，不至于真的"凭空消失"。
    """
    cleaned = clean_history(conversation_history)
    overflow_messages = cleaned[:-MAX_HISTORY] if len(cleaned) > MAX_HISTORY else []
    trimmed_history = cleaned[-MAX_HISTORY:]

    # 不要把 trimmed_history 作为新列表交给各个调用方各自保存。
    # 两个组件可能正在共享 conversation_history 的引用；切片赋值
    # 可以在保持对象身份不变的前提下，清洗并截断其内容。
    conversation_history[:] = trimmed_history

    safe_save_json(MEMORY_PATH, conversation_history)
    return conversation_history, overflow_messages


def load_memory():
    raw_history = safe_load_json(MEMORY_PATH, default_history)
    raw_history = _migrate_legacy_style_history(raw_history)
    history = clean_history(raw_history)
    if history != raw_history:
        safe_save_json(MEMORY_PATH, history)
    return history
