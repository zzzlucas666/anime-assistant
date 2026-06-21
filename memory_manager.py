import json


def save_memory(conversation_history):
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