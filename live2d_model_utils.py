"""Live2D model3.json metadata helpers."""

import json
import os

from logger_utils import get_logger

logger = get_logger(__name__)


def load_live2d_model_metadata(model_path):
    """
    从 model3.json 里读取可用的表情和动作名称。

    这里不依赖 live2d-py，只做纯 JSON 解析：GUI 启动前就能知道模型资源大概有什么，
    也方便之后把情绪映射写进配置，而不是在代码里猜资源名。
    """
    if not model_path:
        return {"expressions": [], "motion_groups": []}

    if not os.path.exists(model_path):
        logger.warning("Live2D 模型文件不存在，跳过表情/动作元数据读取：%s", model_path)
        return {"expressions": [], "motion_groups": []}

    try:
        with open(model_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("读取 Live2D model3.json 失败，跳过表情/动作元数据读取：%s", e)
        return {"expressions": [], "motion_groups": []}

    refs = data.get("FileReferences", {})
    expressions = _extract_expression_names(refs.get("Expressions", []))
    motion_groups = sorted((refs.get("Motions") or {}).keys())
    parameters = _load_display_parameter_ids(model_path, refs.get("DisplayInfo"))

    if not expressions:
        logger.info("Live2D 模型未声明 Expressions，情绪表情映射会暂时跳过。")
    if not motion_groups:
        logger.info("Live2D 模型未声明 Motions，情绪动作映射会暂时跳过。")

    return {
        "expressions": expressions,
        "motion_groups": motion_groups,
        "parameters": parameters,
    }


def _extract_expression_names(expressions):
    names = []
    for item in expressions:
        if not isinstance(item, dict):
            continue

        name = item.get("Name")
        file_path = item.get("File")

        if name:
            names.append(name)
        elif file_path:
            # 有些模型没有写 Name，只写了表情文件名；这种情况下用文件名当作可配置 id。
            names.append(os.path.splitext(os.path.basename(file_path))[0])

    return names


def _load_display_parameter_ids(model_path, display_info_path):
    """
    读取 cdi3.json 里的参数 ID。

    这让我们能在没有 exp3 表情文件时，用参数预设做一个轻量的“伪表情”层，
    比如脸颊、眼睛微笑、眉毛角度等。
    """
    if not display_info_path:
        return []

    cdi_path = os.path.join(os.path.dirname(model_path), display_info_path)
    if not os.path.exists(cdi_path):
        return []

    try:
        with open(cdi_path, "r", encoding="utf-8") as f:
            cdi = json.load(f)
    except Exception as e:
        logger.warning("读取 Live2D cdi3.json 失败，跳过参数列表读取：%s", e)
        return []

    return [
        item.get("Id")
        for item in cdi.get("Parameters", [])
        if isinstance(item, dict) and item.get("Id")
    ]
