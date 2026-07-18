import importlib
from pathlib import Path
import unittest

from anime_assistant.infrastructure.paths import APP_ROOT
from anime_assistant.speech.service import (
    DEFAULT_MIO_GPT_SOVITS_WORKER,
    DEFAULT_MIO_TTS_WORKER,
)


class PackageLayoutTests(unittest.TestCase):
    def test_feature_packages_are_importable(self):
        packages = (
            "ai",
            "character",
            "conversation",
            "emotion",
            "infrastructure",
            "live2d",
            "memory",
            "proactive",
            "speech",
            "ui",
        )
        for package in packages:
            with self.subTest(package=package):
                module = importlib.import_module(f"anime_assistant.{package}")
                self.assertIsNotNone(module)

    def test_root_only_keeps_compatibility_entry_points(self):
        retired_modules = (
            "emotion_manager.py",
            "tts_service.py",
            "orchestrator.py",
            "character_controller.py",
            "config_loader.py",
        )
        for filename in retired_modules:
            with self.subTest(filename=filename):
                self.assertFalse((APP_ROOT / filename).exists())
        self.assertTrue((APP_ROOT / "main.py").is_file())
        self.assertTrue((APP_ROOT / "main_gui.py").is_file())

    def test_default_worker_paths_follow_package_layout(self):
        for relative_path in (
            DEFAULT_MIO_TTS_WORKER,
            DEFAULT_MIO_GPT_SOVITS_WORKER,
        ):
            with self.subTest(relative_path=relative_path):
                self.assertTrue((APP_ROOT / Path(relative_path)).is_file())


if __name__ == "__main__":
    unittest.main()
