"""项目路径定义。

所有运行时文件都相对于此模块所在的项目根目录，而不是进程的
当前工作目录。这样从 IDE、快捷方式或其他目录启动都会使用同一份数据。
"""

import os
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = APP_ROOT / "config"
DATA_DIR = APP_ROOT / "data"


def resolve_project_path(path_value):
    """解析用户配置的路径：支持 ~、环境变量和相对于项目根目录的路径。"""
    if not path_value:
        return None

    expanded = os.path.expandvars(os.path.expanduser(str(path_value)))
    path = Path(expanded)
    if not path.is_absolute():
        path = APP_ROOT / path
    return path.resolve(strict=False)
