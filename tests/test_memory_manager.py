import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import memory_manager
from ai.fallbacks import FALLBACK_REPLIES


class SaveMemoryTests(unittest.TestCase):
    def test_trims_in_place_and_preserves_shared_identity(self):
        history = [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "two"},
            {"role": "user", "content": "three"},
        ]
        orchestrator_history = history
        initiative_history = history

        with tempfile.TemporaryDirectory() as temp_dir:
            memory_path = str(Path(temp_dir) / "conversation_history.json")
            with (
                patch.object(memory_manager, "MEMORY_PATH", memory_path),
                patch.object(memory_manager, "MAX_HISTORY", 2),
            ):
                saved_history, overflow = memory_manager.save_memory(orchestrator_history)

            persisted = json.loads(Path(memory_path).read_text(encoding="utf-8"))

        self.assertIs(saved_history, history)
        self.assertIs(orchestrator_history, initiative_history)
        self.assertEqual([item["content"] for item in initiative_history], ["two", "three"])
        self.assertEqual([item["content"] for item in overflow], ["one"])
        self.assertEqual(persisted, history)

    def test_removes_empty_messages_from_all_shared_views(self):
        history = [
            {"role": "user", "content": "kept"},
            {"role": "assistant", "content": ""},
        ]
        second_owner = history

        with tempfile.TemporaryDirectory() as temp_dir:
            memory_path = str(Path(temp_dir) / "conversation_history.json")
            with patch.object(memory_manager, "MEMORY_PATH", memory_path):
                saved_history, overflow = memory_manager.save_memory(history)

        self.assertIs(saved_history, second_owner)
        self.assertEqual(second_owner, [{"role": "user", "content": "kept"}])
        self.assertEqual(overflow, [])

    def test_load_removes_transient_fallbacks_but_keeps_user_messages(self):
        raw_history = [
            {"role": "user", "content": "你害怕很多人的目光吗"},
            {"role": "assistant", "content": FALLBACK_REPLIES[0]},
            {"role": "assistant", "content": "会有一点，不过熟悉后就好多了。"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            memory_path = str(Path(temp_dir) / "conversation_history.json")
            Path(memory_path).write_text(
                json.dumps(raw_history, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch.object(memory_manager, "MEMORY_PATH", memory_path):
                loaded = memory_manager.load_memory()

            persisted = json.loads(Path(memory_path).read_text(encoding="utf-8"))

        expected = [raw_history[0], raw_history[2]]
        self.assertEqual(loaded, expected)
        self.assertEqual(persisted, expected)

    def test_style_migration_backs_up_and_resets_polluted_history(self):
        raw_history = []
        for index in range(6):
            raw_history.extend([
                {"role": "user", "content": f"message-{index}"},
                {
                    "role": "assistant",
                    "content": "贝斯和琴弦的声音像雨后的空气一样温柔。" * 8,
                },
            ])

        with tempfile.TemporaryDirectory() as temp_dir:
            memory_path = Path(temp_dir) / "conversation_history.json"
            memory_path.write_text(
                json.dumps(raw_history, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch.object(memory_manager, "MEMORY_PATH", str(memory_path)):
                loaded = memory_manager.load_memory()
                marker_path, backup_path = memory_manager._style_migration_paths()

            persisted = json.loads(memory_path.read_text(encoding="utf-8"))
            backup = json.loads(Path(backup_path).read_text(encoding="utf-8"))
            marker = json.loads(Path(marker_path).read_text(encoding="utf-8"))

        self.assertEqual(loaded, [])
        self.assertEqual(persisted, [])
        self.assertEqual(backup, raw_history)
        self.assertEqual(marker["version"], memory_manager.STYLE_HISTORY_VERSION)


if __name__ == "__main__":
    unittest.main()
