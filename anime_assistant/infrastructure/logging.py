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
import threading
from logging.handlers import RotatingFileHandler

from anime_assistant.infrastructure.paths import DATA_DIR

LOG_PATH = str(DATA_DIR / "app.log")
DEFAULT_LOG_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 3
_initialized_loggers = set()
_handler_lock = threading.RLock()
_file_handler = None
_console_handler = None


def _positive_env_int(name, default):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


LOG_MAX_BYTES = _positive_env_int(
    "ANIME_ASSISTANT_LOG_MAX_BYTES",
    DEFAULT_LOG_MAX_BYTES,
)
LOG_BACKUP_COUNT = _positive_env_int(
    "ANIME_ASSISTANT_LOG_BACKUP_COUNT",
    DEFAULT_LOG_BACKUP_COUNT,
)


def _shared_handlers():
    """Create one handler pair shared by all module loggers.

    Sharing matters on Windows: multiple rotating handlers holding the same file
    can otherwise race while renaming it during rollover.
    """
    global _file_handler, _console_handler
    if _file_handler is not None and _console_handler is not None:
        return _file_handler, _console_handler

    os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    _file_handler.setFormatter(formatter)
    _file_handler.setLevel(logging.INFO)

    _console_handler = logging.StreamHandler()
    _console_handler.setFormatter(formatter)
    _console_handler.setLevel(logging.WARNING)
    return _file_handler, _console_handler


def get_logger(name):
    logger = logging.getLogger(name)
    with _handler_lock:
        if name in _initialized_loggers:
            return logger

        file_handler, console_handler = _shared_handlers()
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # 避免重复打印（不传给root logger）
        _initialized_loggers.add(name)
    return logger
