import json
import sys
from logger_utils import get_logger

logger = get_logger(__name__)

REQUIRED_FIELDS = ["api_key", "model", "assistant_name"]


def load_config():
    try:
        with open("config/settings.json", "r", encoding="utf-8") as file:
            content = file.read()
        config = json.loads(content)
    except FileNotFoundError:
        logger.error("找不到 config/settings.json，请检查文件是否存在。")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error("config/settings.json 格式不是合法的 JSON：%s", e)
        sys.exit(1)

    missing = [field for field in REQUIRED_FIELDS if not config.get(field)]
    if missing:
        logger.error("配置缺少必填字段：%s，请检查 config/settings.json。", missing)
        sys.exit(1)

    return config