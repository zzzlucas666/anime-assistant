import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import emotion_manager
import event_manager
import intent_manager
import memory_manager
import profile_extractor
import profile_manager
import relationship_manager
from config_loader import DEFAULT_CONFIG
from data_models import (
    normalize_app_config,
    normalize_emotion,
    normalize_event_extraction,
    normalize_event_record,
    normalize_intent_result,
    normalize_messages,
    normalize_profile,
    normalize_profile_extraction,
    normalize_relationship,
    parse_json_object,
)


def fake_client_with_content(content):
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    return client


class DataModelTests(unittest.TestCase):
    def test_json_parser_accepts_fence_and_rejects_non_object(self):
        self.assertEqual(parse_json_object('```json\n{"intent":"chat"}\n```'), {"intent": "chat"})
        self.assertEqual(parse_json_object('result: {"intent":"chat"} done'), {"intent": "chat"})
        self.assertIsNone(parse_json_object("[1, 2, 3]"))
        self.assertIsNone(parse_json_object("not json"))

    def test_intent_schema_validates_enum_slots_and_confidence(self):
        valid = normalize_intent_result({"intent": "get_profile", "confidence": "3", "slots": []})
        invalid = normalize_intent_result({"intent": "delete_everything", "confidence": 1})
        self.assertEqual(valid, {"intent": "get_profile", "confidence": 1.0, "slots": {}})
        self.assertEqual(invalid, {"intent": "chat", "confidence": 0.0, "slots": {}})

    def test_profile_extraction_requires_known_action_and_string_value(self):
        self.assertEqual(
            normalize_profile_extraction({"action": "add_like", "value": "  jazz  "}),
            {"action": "add_like", "value": "jazz"},
        )
        self.assertEqual(
            normalize_profile_extraction({"action": "run_command", "value": "x"}),
            {"action": "none", "value": ""},
        )
        self.assertEqual(
            normalize_profile_extraction({"action": "set_name", "value": 123}),
            {"action": "none", "value": ""},
        )

    def test_event_extraction_clamps_values_and_rejects_empty_event(self):
        event = normalize_event_extraction({
            "is_event": "true",
            "event": "  important  ",
            "emotion": "angry",
            "impact": "overwrite_files",
            "importance": 9,
        })
        empty = normalize_event_extraction({"is_event": True, "event": ""})
        self.assertEqual(event["event"], "important")
        self.assertEqual(event["emotion"], "neutral")
        self.assertEqual(event["impact"], "none")
        self.assertEqual(event["importance"], 1.0)
        self.assertFalse(empty["is_event"])

    def test_persisted_models_remove_invalid_fields_and_ranges(self):
        profile = normalize_profile({
            "name": " Alice ",
            "likes": ["jazz", "jazz", 3],
            "dislikes": "rain",
            "unexpected": "drop",
        })
        emotion = normalize_emotion({"mood": "angry", "energy": 900, "affection": 99})
        relationship = normalize_relationship({"affection": -5, "trust": "55", "familiarity": float("nan")})
        messages = normalize_messages([
            {"role": "user", "content": " hi "},
            {"role": "system", "content": "hidden"},
            "bad",
        ])
        record = normalize_event_record({"event": "x", "importance": "-2", "embedding": [1, "bad"]})

        self.assertEqual(profile["name"], "Alice")
        self.assertEqual(profile["names"], ["Alice"])
        self.assertEqual(profile["likes"], ["jazz"])
        self.assertNotIn("unexpected", profile)
        self.assertEqual(emotion["mood"], "neutral")
        self.assertEqual(emotion["energy"], 100.0)
        self.assertNotIn("affection", emotion)
        self.assertEqual(relationship, {"affection": 0.0, "trust": 55.0, "familiarity": 10})
        self.assertEqual(messages, [{"role": "user", "content": "hi"}])
        self.assertEqual(record["importance"], 0.0)
        self.assertIsNone(record["embedding"])

    def test_config_model_normalizes_types_and_ranges(self):
        config = normalize_app_config({
            "api_key": " key ",
            "model": " model ",
            "assistant_name": " name ",
            "proactive_check_interval_minutes": 0,
            "proactive_max_per_day": "500",
            "live2d_expression_map": [],
        }, DEFAULT_CONFIG)
        self.assertEqual(config["api_key"], "key")
        self.assertEqual(config["proactive_check_interval_minutes"], 0.1)
        self.assertEqual(config["proactive_max_per_day"], 100)
        self.assertEqual(config["live2d_expression_map"], {})


class AIValidationIntegrationTests(unittest.TestCase):
    def test_intent_manager_validates_ai_json(self):
        client = fake_client_with_content(
            '```json\n{"intent":"get_profile","confidence":8,"slots":[]}\n```'
        )
        with patch("intent_manager.create_ai_client", return_value=client):
            result = intent_manager.detect_intent(
                "key", "model", "你还记得昨天那件事吗", {}, {}, "https://example.invalid"
            )
        self.assertEqual(result, {"intent": "get_profile", "confidence": 1.0, "slots": {}})

    def test_profile_extractor_rejects_unknown_action(self):
        client = fake_client_with_content('{"action":"delete_profile","value":"all"}')
        with patch("profile_extractor.create_ai_client", return_value=client):
            result = profile_extractor.extract_profile_info("key", "model", "text")
        self.assertEqual(result, {"action": "none", "value": ""})

    def test_event_manager_validates_ai_json_before_persistable_record(self):
        client = fake_client_with_content(
            '{"is_event":true,"event":" plan ","emotion":"invalid",'
            '"impact":"invalid","importance":"5"}'
        )
        with (
            patch("event_manager.create_ai_client", return_value=client),
            patch("event_manager.embed_text", return_value=None),
        ):
            event = event_manager.extract_event("key", "model", "user", "reply")
        self.assertEqual(event["event"], "plan")
        self.assertEqual(event["emotion"], "neutral")
        self.assertEqual(event["impact"], "none")
        self.assertEqual(event["importance"], 1.0)


class PersistedMigrationIntegrationTests(unittest.TestCase):
    def test_managers_migrate_invalid_json_without_replacing_shared_objects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = {
                "profile": root / "profile.json",
                "emotion": root / "emotion.json",
                "relationship": root / "relationship.json",
                "memory": root / "memory.json",
            }
            paths["profile"].write_text(json.dumps({"name": " A ", "likes": ["x", "x"]}), encoding="utf-8")
            paths["emotion"].write_text(json.dumps({"mood": "bad", "energy": 300}), encoding="utf-8")
            paths["relationship"].write_text(json.dumps({"affection": -1}), encoding="utf-8")
            paths["memory"].write_text(json.dumps([{"role": "system", "content": "drop"}]), encoding="utf-8")

            with (
                patch.object(profile_manager, "PROFILE_PATH", str(paths["profile"])),
                patch.object(emotion_manager, "EMOTION_PATH", str(paths["emotion"])),
                patch.object(relationship_manager, "RELATIONSHIP_PATH", str(paths["relationship"])),
                patch.object(memory_manager, "MEMORY_PATH", str(paths["memory"])),
            ):
                profile = profile_manager.load_profile()
                emotion = emotion_manager.load_emotion()
                relationship = relationship_manager.load_relationship()
                history = memory_manager.load_memory()

                profile_identity = profile
                emotion_identity = emotion
                relationship_identity = relationship
                profile_manager.save_profile(profile)
                emotion_manager.save_emotion(emotion)
                relationship_manager.save_relationship(relationship)

        self.assertIs(profile, profile_identity)
        self.assertIs(emotion, emotion_identity)
        self.assertIs(relationship, relationship_identity)
        self.assertEqual(profile["name"], "A")
        self.assertEqual(profile["likes"], ["x"])
        self.assertEqual(emotion["mood"], "neutral")
        self.assertEqual(emotion["energy"], 100.0)
        self.assertEqual(relationship["affection"], 0.0)
        self.assertEqual(history, [])


if __name__ == "__main__":
    unittest.main()
