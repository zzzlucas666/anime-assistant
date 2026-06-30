from Storage_utils import safe_load_json, safe_save_json

MEMORY_PATH = "data/conversation_history.json"
MAX_HISTORY = 50


def default_history():
    return []


def clean_history(history):
    return [
        msg
        for msg in history
        if msg.get("content")
    ]


def save_memory(conversation_history):
    """
    清洗 + 截断到最近 MAX_HISTORY 条，存盘。

    返回 (trimmed_history, overflow_messages)：
    - trimmed_history：截断后的列表，调用方应该用这个重新赋值回自己的
      conversation_history 变量，否则内存里的列表永远不会真正变短
      （这是之前版本的一个隐藏bug：之前只是把截断后的"副本"存进了文件，
      原始列表对象从未被真正裁剪过，长时间运行会在内存里无限增长）。
    - overflow_messages：被截断丢弃掉的那部分旧消息，供 long_term_memory
      压缩成摘要，不至于真的"凭空消失"。
    """
    cleaned = clean_history(conversation_history)
    overflow_messages = cleaned[:-MAX_HISTORY] if len(cleaned) > MAX_HISTORY else []
    trimmed_history = cleaned[-MAX_HISTORY:]

    safe_save_json(MEMORY_PATH, trimmed_history)
    return trimmed_history, overflow_messages


def load_memory():
    return safe_load_json(MEMORY_PATH, default_history)