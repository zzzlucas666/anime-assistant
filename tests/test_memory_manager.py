import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import memory_manager


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


if __name__ == "__main__":
    unittest.main()
