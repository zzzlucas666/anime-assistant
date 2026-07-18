"""
统一的日志工具。

用法：
    from anime_assistant.infrastructure.logging import get_logger
    logger = get_logger(__name__)
    logger.warning("xxx 调用失败：%s", e)

设计：
- 日志统一写到项目 data/app.log，方便事后排查（尤其是后台线程里发生的问题，
  控制台可能根本看不到）
- 同时也会打印到控制台（级别 WARNING 以上才打印，避免刷屏），
  保留"出问题时終端也能看到"的体验
- 每个模块用 __name__ 取自己的 logger，但实际都写到同一个文件里，
  日志里能看出是哪个模块报的
"""

import logging
import os

from anime_assistant.infrastructure.paths import DATA_DIR

LOG_PATH = str(DATA_DIR / "app.log")
_initialized_loggers = set()


def get_logger(name):
    logger = logging.getLogger(name)

    if name in _initialized_loggers:
        return logger

    os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 写文件：记录所有 INFO 及以上的日志，留作事后排查
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # 同时打印到控制台：只显示 WARNING 及以上，避免正常运行时刷屏
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.WARNING)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # 避免重复打印（不传给root logger）

    _initialized_loggers.add(name)
    return logger
