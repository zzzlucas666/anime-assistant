import json

MAX_HISTORY = 50
def clean_history(history):
    return [
        msg
        for msg in history
        if msg.get("content")
    ]
def save_memory(conversation_history):
    conversation_history = clean_history(conversation_history)
    coversation_history = conversation_history[-MAX_HISTORY:]
    with open(
        "data/conversation_history.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            conversation_history,
            file,
            ensure_ascii=False,
            indent=4
        )
def load_memory():
    with open(
        "data/conversation_history.json",
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)

