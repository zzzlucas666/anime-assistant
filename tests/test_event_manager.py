import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import event_manager


class EventMigrationTests(unittest.TestCase):
    def test_load_migrates_legacy_event_and_persists_schema(self):
        legacy_event = {
            "event": "an older memory",
            "emotion": "neutral",
            "impact": "none",
            "importance": 0.8,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = Path(temp_dir) / "event_memory.json"
            event_path.write_text(json.dumps([legacy_event]), encoding="utf-8")

            with patch.object(event_manager, "EVENT_PATH", str(event_path)):
                events = event_manager.load_all_events()
                persisted = json.loads(event_path.read_text(encoding="utf-8"))

        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["id"])
        self.assertFalse(events[0]["notified"])
        self.assertIsNone(events[0]["created_at"])
        self.assertIsNone(events[0]["embedding"])
        self.assertEqual(persisted, events)

    def test_duplicate_ids_are_replaced_during_migration(self):
        events = [
            {"id": "same", "event": "first"},
            {"id": "same", "event": "second"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = Path(temp_dir) / "event_memory.json"
            event_path.write_text(json.dumps(events), encoding="utf-8")

            with patch.object(event_manager, "EVENT_PATH", str(event_path)):
                migrated = event_manager.load_all_events()

        self.assertEqual(len({event["id"] for event in migrated}), 2)
        self.assertEqual(migrated[0]["id"], "same")

    def test_legacy_important_event_can_be_marked_notified(self):
        legacy_event = {"event": "important", "importance": 0.9}

        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = Path(temp_dir) / "event_memory.json"
            event_path.write_text(json.dumps([legacy_event]), encoding="utf-8")

            with patch.object(event_manager, "EVENT_PATH", str(event_path)):
                pending = event_manager.get_unnotified_important_events()
                event_manager.mark_event_notified(pending[0]["id"])
                updated = event_manager.load_all_events()

        self.assertTrue(pending[0]["id"])
        self.assertTrue(updated[0]["notified"])


if __name__ == "__main__":
    unittest.main()
