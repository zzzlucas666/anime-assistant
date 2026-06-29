"""
通用的安全 JSON 读写工具。

设计目标：
- 保存时自动维护一份 .bak 备份（备份的是"上一次成功保存"的内容）
- 加载时：主文件读取失败 -> 尝试备份文件 -> 仍失败则使用调用方提供的默认值
- 任何环节都不让程序直接崩溃，最坏情况下也能用默认值继续运行
"""

import json
import os
import shutil
from logger_utils import get_logger

logger = get_logger(__name__)


def safe_save_json(path, data):
    """
    保存 JSON 数据，并在覆盖前自动备份旧文件。
    返回 True/False 表示是否保存成功（备份失败不影响保存结果，只记录警告）。
    """
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    backup_path = path + ".bak"

    # 备份旧文件（如果存在）
    if os.path.exists(path):
        try:
            shutil.copyfile(path, backup_path)
        except Exception as e:
            logger.warning("备份 %s 失败（不影响本次保存）：%s", path, e)

    # 写入新内容（先写临时文件再替换，避免写到一半被中断导致主文件损坏）
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        logger.error("保存 %s 失败：%s", path, e)
        return False


def safe_load_json(path, default_factory):
    """
    读取 JSON 数据，按优先级尝试：主文件 -> 备份文件 -> 默认值。
    default_factory: 一个无参函数，返回默认值（比如 lambda: {"mood": "neutral", ...}）
    """
    backup_path = path + ".bak"

    # 1. 尝试主文件
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.info("读取 %s 失败：%s，尝试备份文件...", path, e)

    # 2. 尝试备份文件
    try:
        with open(backup_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.warning("已从备份 %s 恢复数据。", backup_path)
            # 用恢复出来的数据覆盖损坏的主文件，避免下次还要走这条路径
            safe_save_json(path, data)
            return data
    except Exception as e:
        logger.info("读取备份 %s 也失败：%s，使用默认值。", backup_path, e)

    # 3. 两者都失败，使用默认值，并立即落盘，确保下次能正常加载
    default_data = default_factory()
    safe_save_json(path, default_data)
    return default_data