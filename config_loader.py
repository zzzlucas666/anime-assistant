import json
import math
import sys
from pathlib import Path

from ai.client import DEFAULT_BASE_URL
from app_paths import CONFIG_DIR
from data_models import normalize_app_config
from logger_utils import get_logger
from Storage_utils import safe_save_json
from tts_service import (
    DEFAULT_AIVIS_ENDPOINT,
    DEFAULT_AIVIS_MAX_CHARS,
    DEFAULT_AIVIS_TIMEOUT_SECONDS,
    DEFAULT_MOOD_SPEAKERS,
)

logger = get_logger(__name__)

REQUIRED_FIELDS = ["api_key", "model", "assistant_name"]

DEFAULT_CONFIG = {
    "base_url": DEFAULT_BASE_URL,
    "chat_thinking_enabled": False,
    "chat_history_max_messages": 8,
    "live2d_model_path": "",
    "live2d_expression_intensity": 1.25,
    "live2d_waiting_motion_intensity": 1.0,
    "live2d_waiting_gaze_intensity": 1.0,
    "live2d_waiting_motion_speed": 1.4,
    "live2d_expression_map": {},
    "live2d_motion_map": {},
    "live2d_parameter_map": {},
    "tts_enabled": True,
    "tts_translate_to_japanese": True,
    "tts_speed_scale": 1.0,
    "tts_volume_scale": 1.0,
    "aivis_endpoint": DEFAULT_AIVIS_ENDPOINT,
    "aivis_timeout_seconds": DEFAULT_AIVIS_TIMEOUT_SECONDS,
    "aivis_max_chars_per_request": DEFAULT_AIVIS_MAX_CHARS,
    "aivis_mood_speakers": DEFAULT_MOOD_SPEAKERS.copy(),
    "proactive_check_interval_minutes": 5,
    "proactive_idle_threshold_minutes": 30,
    "proactive_min_interval_minutes": 120,
    "proactive_max_per_day": 3,
}

LIVE2D_PRESET_MOODS = {"neutral", "happy", "sad", "shy", "tired"}


def load_config(config_path=None):
    path = Path(config_path) if config_path else CONFIG_DIR / "settings.json"
    try:
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
        config = json.loads(content)
    except FileNotFoundError:
        logger.error("找不到配置文件 %s，请检查文件是否存在。", path)
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error("配置文件 %s 不是合法的 JSON：%s", path, e)
        sys.exit(1)

    if not isinstance(config, dict):
        logger.error("配置文件 %s 的顶层必须是 JSON 对象。", path)
        sys.exit(1)

    missing = [
        field for field in REQUIRED_FIELDS
        if not isinstance(config.get(field), str) or not config[field].strip()
    ]
    if missing:
        logger.error("配置缺少必填字段：%s，请检查 %s。", missing, path)
        sys.exit(1)

    return normalize_app_config(config, DEFAULT_CONFIG)


def save_live2d_parameter_preset(config, mood, parameters, config_path=None):
    """把滑块调好的情绪参数安全写回本地 settings.json。"""
    if not isinstance(config, dict) or mood not in LIVE2D_PRESET_MOODS:
        return False
    if not isinstance(parameters, dict):
        return False

    cleaned = {}
    for param_id, value in parameters.items():
        if not isinstance(param_id, str) or not param_id:
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric_value):
            cleaned[param_id] = numeric_value

    parameter_map = config.get("live2d_parameter_map")
    if not isinstance(parameter_map, dict):
        parameter_map = {}
        config["live2d_parameter_map"] = parameter_map
    parameter_map[mood] = cleaned

    path = Path(config_path) if config_path else CONFIG_DIR / "settings.json"
    return safe_save_json(str(path), config)


def save_live2d_waiting_motion_intensity(config, intensity, config_path=None):
    """保存待机摆头/头发物理动作的整体倍率。"""
    if not isinstance(config, dict):
        return False
    try:
        intensity = float(intensity)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(intensity):
        return False
    config["live2d_waiting_motion_intensity"] = max(0.0, min(2.0, intensity))
    path = Path(config_path) if config_path else CONFIG_DIR / "settings.json"
    return safe_save_json(str(path), config)


def save_live2d_waiting_gaze_intensity(config, intensity, config_path=None):
    """保存等待语音时眼睛游移幅度的整体倍率。"""
    if not isinstance(config, dict):
        return False
    try:
        intensity = float(intensity)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(intensity):
        return False
    config["live2d_waiting_gaze_intensity"] = max(0.0, min(2.0, intensity))
    path = Path(config_path) if config_path else CONFIG_DIR / "settings.json"
    return safe_save_json(str(path), config)


def save_live2d_waiting_motion_speed(config, speed, config_path=None):
    """保存待机动作整体速度倍率。"""
    if not isinstance(config, dict):
        return False
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(speed):
        return False
    config["live2d_waiting_motion_speed"] = max(0.5, min(2.0, speed))
    path = Path(config_path) if config_path else CONFIG_DIR / "settings.json"
    return safe_save_json(str(path), config)
