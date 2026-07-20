import datetime
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from anime_assistant.ai import chat
from anime_assistant.character import profile_extractor, profile_manager, relationship_behavior, relationship_manager
from anime_assistant.conversation.context_builder import _build_event_hint_with_budget, _rank_events
from anime_assistant.conversation.context_manager import ContextManager
from anime_assistant.conversation.orchestrator import ConversationOrchestrator
from anime_assistant.memory import event_manager
from anime_assistant.memory.policy import (
    can_event_affect_state,
    event_context_text,
    is_event_retrievable,
)


def fake_client(content):
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    return client


def event_record(**overrides):
    base = {
        "schema_version": 2,
        "id": "event-1",
        "event": "AI summary",
        "emotion": "neutral",
        "user_emotion": "neutral",
        "impact": "increase_affinity",
        "importance": 0.8,
        "notified": False,
        "created_at": "2026-07-19T12:00:00",
        "updated_at": "2026-07-19T12:00:00",
        "type": "general",
        "status": "confirmed",
        "source": "user_explicit",
        "confidence": 0.9,
        "evidence": ["我喜欢爵士乐"],
        "expires_at": None,
        "embedding": None,
        "embedding_model": "",
        "embedding_version": "",
    }
    base.update(overrides)
    return base


class RelationshipPolicyTests(unittest.TestCase):
    def test_chat_and_context_use_the_same_relationship_policy(self):
        relationship = {"affection": 45, "trust": 75, "familiarity": 20}
        policy = relationship_behavior.build_relationship_policy(relationship, {"mood": "happy"})
        context = ContextManager({}, {"mood": "happy"}, {}, relationship)

        self.assertIs(chat.build_relationship_hint, relationship_behavior.build_relationship_hint)
        self.assertEqual(policy["closeness"], "friendly")
        self.assertEqual(policy["openness"], "open")
        self.assertEqual(context.get_behavior(), policy)


class EventProvenanceTests(unittest.TestCase):
    def test_exact_user_evidence_confirms_event(self):
        content = json.dumps({
            "is_event": True,
            "event": "对方喜欢爵士乐",
            "emotion": "curious",
            "user_emotion": "happy",
            "impact": "increase_affinity",
            "importance": 0.7,
            "type": "preference",
            "source": "user_explicit",
            "evidence": "喜欢爵士乐",
            "confidence": 0.92,
            "expires_at": None,
        }, ensure_ascii=False)
        with (
            patch("anime_assistant.memory.event_manager.create_ai_client", return_value=fake_client(content)),
            patch("anime_assistant.memory.event_manager.embed_text", return_value=None),
        ):
            event = event_manager.extract_event("key", "model", "我最近很喜欢爵士乐", "听起来不错")

        self.assertEqual(event["status"], "confirmed")
        self.assertEqual(event["source"], "user_explicit")
        self.assertEqual(event["evidence"], ["喜欢爵士乐"])
        self.assertTrue(can_event_affect_state(event))

    def test_unverifiable_ai_claim_stays_candidate(self):
        content = json.dumps({
            "is_event": True,
            "event": "对方下周三有数学考试",
            "emotion": "worried",
            "user_emotion": "anxious",
            "impact": "increase_bond",
            "importance": 0.9,
            "type": "plan",
            "source": "user_explicit",
            "evidence": "下周三有数学考试",
            "confidence": 0.99,
        }, ensure_ascii=False)
        with patch(
            "anime_assistant.memory.event_manager.create_ai_client",
            return_value=fake_client(content),
        ):
            event = event_manager.extract_event("key", "model", "最近有点忙", "考试要加油")

        self.assertEqual(event["status"], "candidate")
        self.assertEqual(event["source"], "ai_inferred")
        self.assertFalse(is_event_retrievable(event))
        self.assertFalse(can_event_affect_state(event))

    def test_context_uses_evidence_and_excludes_candidates(self):
        confirmed = event_record()
        candidate = event_record(
            id="event-2", status="candidate", source="ai_inferred", evidence=[], event="invented"
        )
        ranked = _rank_events([candidate, confirmed], query_text=None)
        hint = _build_event_hint_with_budget(ranked, 800)

        self.assertEqual(ranked, [confirmed])
        self.assertIn("我喜欢爵士乐", hint)
        self.assertNotIn("AI summary", hint)
        self.assertEqual(event_context_text(confirmed), "对方曾明确说：我喜欢爵士乐")

    def test_expired_event_is_not_retrievable(self):
        expired = event_record(
            type="temporary_context",
            expires_at="2020-01-01T00:00:00",
        )
        self.assertFalse(is_event_retrievable(expired, now="2026-07-19T00:00:00"))

    def test_confirmed_user_source_without_evidence_is_still_rejected(self):
        ungrounded = event_record(evidence=[])
        self.assertFalse(is_event_retrievable(ungrounded))
        self.assertFalse(can_event_affect_state(ungrounded))

    def test_relationship_manager_has_its_own_trust_gate(self):
        relationship = {"affection": 30, "trust": 30, "familiarity": 10}
        candidate = event_record(status="candidate", source="ai_inferred", evidence=[])
        relationship_manager.update_relationship(relationship, candidate)
        self.assertEqual(relationship, {"affection": 30.0, "trust": 30.0, "familiarity": 10.0})


class ProfileGovernanceTests(unittest.TestCase):
    def test_untrusted_profile_fact_cannot_materialize_top_level_name(self):
        profile = {
            "schema_version": 2,
            "name": "Invented",
            "nickname": "",
            "likes": [],
            "dislikes": [],
            "facts": [{
                "id": "candidate-name",
                "category": "identity.name",
                "value": "Invented",
                "status": "candidate",
                "source": "ai_inferred",
                "confidence": 0.2,
                "evidence": [],
            }],
        }
        profile_manager.materialize_profile(profile)
        self.assertEqual(profile["name"], "")

    def test_profile_extractor_rejects_value_not_present_in_user_message(self):
        client = fake_client('{"action":"add_like","value":"咖啡"}')
        with patch(
            "anime_assistant.character.profile_extractor.create_ai_client",
            return_value=client,
        ):
            result = profile_extractor.extract_profile_info("key", "model", "我喜欢爵士乐")
        self.assertEqual(result, {"action": "none", "value": ""})

    def test_legacy_profile_migrates_to_auditable_facts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(
                json.dumps({"name": "Lucas", "likes": ["爵士乐"], "dislikes": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch.object(profile_manager, "PROFILE_PATH", str(path)):
                profile = profile_manager.load_profile()

        self.assertEqual(profile["schema_version"], 2)
        self.assertEqual(profile["name"], "Lucas")
        self.assertEqual(profile["likes"], ["爵士乐"])
        self.assertTrue(all(fact["source"] == "legacy_import" for fact in profile["facts"]))

    def test_correction_supersedes_old_name_without_deleting_history(self):
        profile = {"name": "Lucas", "nickname": "", "likes": [], "dislikes": []}
        profile_manager.materialize_profile(profile)
        changed = profile_manager.apply_profile_action(
            profile,
            "set_name",
            "Luc",
            source="user_corrected",
            evidence=["更正一下，我叫 Luc"],
        )

        self.assertTrue(changed)
        self.assertEqual(profile["name"], "Luc")
        self.assertIn("Lucas", profile["names"])
        old = next(fact for fact in profile["facts"] if fact["value"] == "Lucas")
        self.assertEqual(old["status"], "superseded")

    def test_opposite_preference_resolves_conflict(self):
        profile = profile_manager.default_profile()
        profile_manager.apply_profile_action(profile, "add_like", "咖啡", evidence=["我喜欢咖啡"])
        profile_manager.apply_profile_action(
            profile,
            "add_dislike",
            "咖啡",
            source="user_corrected",
            evidence=["我现在不喜欢咖啡了"],
        )

        self.assertNotIn("咖啡", profile["likes"])
        self.assertIn("咖啡", profile["dislikes"])
        old_like = next(fact for fact in profile["facts"] if fact["category"] == "preference.like")
        self.assertEqual(old_like["status"], "superseded")

    def test_lower_priority_merge_cannot_override_explicit_name(self):
        profile = profile_manager.default_profile()
        profile_manager.apply_profile_action(profile, "set_name", "Luc", evidence=["我叫 Luc"])
        profile_manager.merge_profile_facts(profile, [{
            "id": "legacy-name",
            "category": "identity.name",
            "value": "Lucas",
            "status": "legacy",
            "source": "legacy_import",
            "confidence": 0.6,
            "evidence": [],
        }])
        self.assertEqual(profile["name"], "Luc")


class EmbeddingBackfillTests(unittest.TestCase):
    def test_backfill_updates_only_retrievable_records(self):
        records = [
            event_record(),
            event_record(id="candidate", status="candidate", source="ai_inferred", evidence=[]),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.json"
            path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
            with (
                patch.object(event_manager, "EVENT_PATH", str(path)),
                patch("anime_assistant.memory.event_manager.embed_text", return_value=[0.1, 0.2]),
            ):
                event_manager.clear_event_cache()
                count = event_manager.backfill_missing_embeddings(batch_size=2)
                updated = event_manager.load_all_events()
                event_manager.clear_event_cache()

        self.assertEqual(count, 1)
        self.assertEqual(updated[0]["embedding"], [0.1, 0.2])
        self.assertTrue(updated[0]["embedding_model"])
        self.assertIsNone(updated[1]["embedding"])

    def test_due_status_is_persisted_during_migration(self):
        record = event_record(
            type="temporary_context",
            expires_at="2020-01-01T00:00:00",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.json"
            path.write_text(json.dumps([record], ensure_ascii=False), encoding="utf-8")
            with patch.object(event_manager, "EVENT_PATH", str(path)):
                event_manager.clear_event_cache()
                loaded = event_manager.load_all_events()
                persisted = json.loads(path.read_text(encoding="utf-8"))
                event_manager.clear_event_cache()

        self.assertEqual(loaded[0]["status"], "expired")
        self.assertEqual(persisted[0]["status"], "expired")


class OrchestratorTrustGateTests(unittest.TestCase):
    def test_candidate_event_is_saved_for_audit_but_cannot_change_relationship(self):
        config = {"api_key": "key", "model": "model", "base_url": None}
        emotion = {"mood": "neutral", "energy": 80}
        profile = profile_manager.default_profile()
        relationship = {"affection": 30, "trust": 30, "familiarity": 10}
        context = ContextManager(config, emotion, profile, relationship)
        orchestrator = ConversationOrchestrator(
            config, context, [], emotion, profile, relationship
        )
        candidate = event_record(status="candidate", source="ai_inferred", evidence=[])
        task = {
            "clean_message": "最近有点忙",
            "reply": "那就先休息一下吧",
            "router_reply": None,
            "interaction_emotion": {},
            "immediate_emotion_applied": True,
        }
        try:
            with (
                patch("anime_assistant.conversation.orchestrator.extract_event", return_value=candidate),
                patch("anime_assistant.conversation.orchestrator.save_event") as save_event,
                patch("anime_assistant.conversation.orchestrator.update_relationship") as update_relationship,
                patch("anime_assistant.conversation.orchestrator.summarize_pending_if_ready", return_value=False),
            ):
                orchestrator._postprocess_turn(task)
            save_event.assert_called_once_with(candidate)
            update_relationship.assert_not_called()
            self.assertEqual(relationship["affection"], 30)
        finally:
            orchestrator.shutdown()


if __name__ == "__main__":
    unittest.main()
