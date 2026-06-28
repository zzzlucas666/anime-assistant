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
    conversation_history = clean_history(conversation_history)
    conversation_history = conversation_history[-MAX_HISTORY:]
    safe_save_json(MEMORY_PATH, conversation_history)


def load_memory():
    return safe_load_json(MEMORY_PATH, default_history)

