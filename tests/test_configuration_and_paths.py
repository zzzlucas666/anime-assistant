import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai.client import DEFAULT_BASE_URL, create_ai_client
from ai.chat import get_user_display_name, load_persona
from app_paths import APP_ROOT, CONFIG_DIR, DATA_DIR, resolve_project_path
from config_loader import (
    DEFAULT_CONFIG,
    load_config,
    save_live2d_parameter_preset,
    save_live2d_waiting_gaze_intensity,
    save_live2d_waiting_motion_intensity,
    save_live2d_waiting_motion_speed,
)
from live2d_model_utils import resolve_live2d_model_path


class ConfigurationAndPathTests(unittest.TestCase):
    def test_ai_client_uses_default_or_configured_base_url(self):
        with patch("ai.client.OpenAI") as openai:
            create_ai_client("key")
            openai.assert_called_once_with(api_key="key", base_url=DEFAULT_BASE_URL)

        with patch("ai.client.OpenAI") as openai:
            create_ai_client("key", "https://example.invalid/v1")
            openai.assert_called_once_with(api_key="key", base_url="https://example.invalid/v1")

    def test_project_paths_are_absolute_and_stable(self):
        self.assertTrue(APP_ROOT.is_absolute())
        self.assertEqual(CONFIG_DIR, APP_ROOT / "config")
        self.assertEqual(DATA_DIR, APP_ROOT / "data")
        self.assertEqual(resolve_project_path("data/example.json"), APP_ROOT / "data" / "example.json")

    def test_config_defaults_are_merged_without_overwriting_user_values(self):
        configured = {
            "api_key": "test-key",
            "model": "test-model",
            "assistant_name": "Test Assistant",
            "proactive_max_per_day": 7,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "settings.json"
            config_path.write_text(json.dumps(configured), encoding="utf-8")
            loaded = load_config(config_path)

        self.assertEqual(loaded["base_url"], DEFAULT_CONFIG["base_url"])
        self.assertFalse(loaded["chat_thinking_enabled"])
        self.assertEqual(loaded["chat_history_max_messages"], 8)
        self.assertEqual(loaded["live2d_model_path"], "")
        self.assertEqual(loaded["live2d_waiting_motion_intensity"], 1.0)
        self.assertEqual(loaded["live2d_waiting_gaze_intensity"], 1.0)
        self.assertEqual(loaded["live2d_waiting_motion_speed"], 1.4)
        self.assertEqual(loaded["proactive_max_per_day"], 7)
        self.assertTrue(loaded["tts_enabled"])
        self.assertTrue(loaded["tts_translate_to_japanese"])
        self.assertEqual(loaded["aivis_endpoint"], "http://127.0.0.1:10101")
        self.assertEqual(loaded["aivis_timeout_seconds"], 60.0)
        self.assertEqual(loaded["aivis_max_chars_per_request"], 56)
        self.assertEqual(loaded["aivis_mood_speakers"]["tired"], 1878365379)

    def test_live2d_parameter_preset_is_saved_without_losing_config(self):
        config = {
            "api_key": "secret-key",
            "model": "test-model",
            "assistant_name": "Mio",
            "live2d_parameter_map": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "settings.json"
            saved = save_live2d_parameter_preset(
                config,
                "sad",
                {"ParamMouthForm": -0.27, "invalid": "skip-me"},
                config_path,
            )
            persisted = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertTrue(saved)
        self.assertEqual(persisted["api_key"], "secret-key")
        self.assertEqual(
            persisted["live2d_parameter_map"]["sad"],
            {"ParamMouthForm": -0.27},
        )

    def test_waiting_motion_intensity_is_saved_and_clamped(self):
        config = {
            "api_key": "secret-key",
            "model": "test-model",
            "assistant_name": "Mio",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "settings.json"
            saved = save_live2d_waiting_motion_intensity(
                config, 3.5, config_path
            )
            persisted = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertTrue(saved)
        self.assertEqual(persisted["live2d_waiting_motion_intensity"], 2.0)
        self.assertEqual(persisted["api_key"], "secret-key")

    def test_waiting_gaze_intensity_is_saved_and_clamped(self):
        config = {
            "api_key": "secret-key",
            "model": "test-model",
            "assistant_name": "Mio",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "settings.json"
            saved = save_live2d_waiting_gaze_intensity(
                config, -1.0, config_path
            )
            persisted = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertTrue(saved)
        self.assertEqual(persisted["live2d_waiting_gaze_intensity"], 0.0)

    def test_waiting_motion_speed_is_saved_and_clamped(self):
        config = {
            "api_key": "secret-key",
            "model": "test-model",
            "assistant_name": "Mio",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "settings.json"
            saved = save_live2d_waiting_motion_speed(
                config, 5.0, config_path
            )
            persisted = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertTrue(saved)
        self.assertEqual(persisted["live2d_waiting_motion_speed"], 2.0)

    def test_persona_load_does_not_depend_on_current_working_directory(self):
        previous_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                persona = load_persona()
            finally:
                os.chdir(previous_cwd)

        self.assertIn("name", persona)
        self.assertIn("personality", persona)

    def test_invalid_live2d_path_disables_live2d(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.model3.json"
            self.assertIsNone(resolve_live2d_model_path(str(missing)))

    def test_valid_live2d_path_is_normalized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "model.model3.json"
            model_path.write_text("{}", encoding="utf-8")
            self.assertEqual(resolve_live2d_model_path(str(model_path)), str(model_path.resolve()))

    def test_user_display_name_prefers_nickname_then_name(self):
        self.assertEqual(get_user_display_name({"nickname": "Nick", "name": "Name"}), "Nick")
        self.assertEqual(get_user_display_name({"nickname": "", "name": "Name"}), "Name")
        self.assertEqual(get_user_display_name({}), "对方")


if __name__ == "__main__":
    unittest.main()
