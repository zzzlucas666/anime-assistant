import json
import sys

REQUIRED_FIELDS = ["api_key", "model", "assistant_name"]


def load_config():
    try:
        with open("config/settings.json", "r", encoding="utf-8") as file:
            content = file.read()
        config = json.loads(content)
    except FileNotFoundError:
        print("[config_loader] 找不到 config/settings.json，请检查文件是否存在。")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[config_loader] config/settings.json 格式不是合法的 JSON：{e}")
        sys.exit(1)

    missing = [field for field in REQUIRED_FIELDS if not config.get(field)]
    if missing:
        print(f"[config_loader] 配置缺少必填字段：{missing}，请检查 config/settings.json。")
        sys.exit(1)

    return config