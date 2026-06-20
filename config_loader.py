import json

def load_config():
    with open("config/settings.json", "r", encoding="utf-8") as file:
        content = file.read()
    config = json.loads(content)

    return config