import json

def load_config():
    with open("config/settings.json", "r", encoding="utf-8") as file:
        content = file.read()

    print("读取到的内容：")
    print(content)

    config = json.loads(content)

    return config