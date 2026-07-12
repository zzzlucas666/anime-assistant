from Storage_utils import safe_load_json, safe_save_json
from app_paths import DATA_DIR
from data_models import normalize_messages

MEMORY_PATH = str(DATA_DIR / "conversation_history.json")
MAX_HISTORY = 50


def default_history():
    return []


def clean_history(history):
    return normalize_messages(history)


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
    history = normalize_messages(raw_history)
    if history != raw_history:
        safe_save_json(MEMORY_PATH, history)
    return history
