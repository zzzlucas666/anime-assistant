"""
ConversationOrchestrator —— 负责编排"处理一轮对话"需要的所有步骤。

main.py 不再直接调用各个 manager，只负责：
    1. 读取用户输入
    2. 调用 orchestrator.prepare_turn() 做意图/资料判断
    3. 调用 orchestrator.stream_reply() 拿到回复（流式打印）
    4. 调用 orchestrator.finalize_turn() 做收尾（事件提取、状态更新、存历史）

这样 main.py 只剩"输入-输出-循环"的壳子，业务流程都收在这里，
以后 Initiative Engine 需要"生成一轮回复"时，也能直接复用这个类，
不用再复制一遍 main.py 里的逻辑。
"""

import copy
import queue
import re
import threading
import time

from anime_assistant.conversation.intent_manager import plan_local_route
from anime_assistant.ai.fallbacks import is_transient_fallback
from anime_assistant.character.profile_extractor import extract_profile_info
from anime_assistant.conversation.router import handle_intent
from anime_assistant.ai.chat import chat_with_ai_stream
from anime_assistant.emotion.manager import (
    apply_ai_emotion_control,
    has_interaction_signal,
    infer_interaction_emotion,
    plan_turn_emotion,
    update_emotion,
    save_emotion,
)
from anime_assistant.memory.event_manager import extract_event, save_event
from anime_assistant.character.relationship_manager import update_relationship, save_relationship
from anime_assistant.character.profile_manager import apply_profile_action, save_profile
from anime_assistant.memory.memory_manager import save_memory
from anime_assistant.proactive.interaction_tracker import update_last_interaction_time
from anime_assistant.memory.long_term_memory import queue_summary_messages, summarize_pending_if_ready
from anime_assistant.infrastructure.logging import get_logger
from anime_assistant.memory.policy import can_event_affect_state


logger = get_logger(__name__)


def clean_reply(reply):
    reply = re.sub(r'（.*?）', '', reply)
    reply = re.sub(r'<mio:[^>]*>', '', reply, flags=re.IGNORECASE)
    return reply.strip()


class ConversationOrchestrator:
    def __init__(
        self,
        config,
        context,
        conversation_history,
        emotion,
        profile,
        relationship,
        lock=None,
        on_state_updated=None,
    ):
        self.config = config
        self.context = context
        self.conversation_history = conversation_history
        self.emotion = emotion
        self.profile = profile
        self.relationship = relationship
        # 跟 InitiativeEngine 共用同一把锁，避免两边同时读写状态文件。
        # 如果没传进来（比如单独测试这个类），就自己建一把，保证不报错。
        self.lock = lock if lock is not None else threading.Lock()
        self.on_state_updated = on_state_updated
        # 累积本轮（用户消息+助手消息）产生的溢出消息，finalize_turn 结束时统一交给长期摘要
        self._pending_overflow = []
        # 事件提取、情绪/关系更新和长期摘要按对话顺序在单一 daemon
        # 线程中处理。这保留了状态顺序，又不阻塞 GUI 恢复输入。
        self._postprocess_queue = queue.Queue()
        self._postprocess_accepting = True
        self._postprocess_thread = threading.Thread(
            target=self._postprocess_loop,
            name="conversation-postprocess",
            daemon=True,
        )
        self._postprocess_thread.start()

    @staticmethod
    def _clean_input(user_message):
        return (
            user_message
            .replace("？", "")
            .replace("?", "")
            .strip()
        )

    def _apply_profile_update(self, profile_info, confidence, user_message=""):
        """Apply a user-evidenced profile action and report whether state changed."""
        if not isinstance(profile_info, dict) or confidence <= 0.5:
            return False

        action = profile_info.get("action")
        value = profile_info.get("value")
        if action == "none" or not value:
            return False

        correction_markers = ("不再", "现在不", "更正", "记错", "改成", "不是")
        source = (
            "user_corrected"
            if action.startswith("remove_") or any(marker in user_message for marker in correction_markers)
            else "user_explicit"
        )
        changed = apply_profile_action(
            self.profile,
            action,
            value,
            source=source,
            confidence=confidence,
            evidence=[user_message] if user_message else [value],
        )
        if changed:
            save_profile(self.profile)
        return changed

    def prepare_turn(self, user_message):
        """
        处理输入清洗和纯本地路由，并判断本轮要不要走 router 精确回复。

        首字前不允许进行额外 AI 意图识别或资料提取。明确资料直接本地
        解析；模糊资料只登记为回复后的后台任务。
        返回一个 dict，供 stream_reply / finalize_turn 使用。
        """
        started_at = time.perf_counter()
        clean_message = self._clean_input(user_message)
        route = plan_local_route(user_message)
        with self.lock:
            intent_emotion_snapshot = copy.deepcopy(self.emotion)
            relationship_snapshot = copy.deepcopy(self.relationship)

        # 回复生成前先规划“用户现在是什么感受、Mio 本轮该如何反应”。
        # 这是纯本地判断，不增加网络等待；生成后的校准只允许细化该计划，
        # 不会再让 Mio 因为自己上一句的语气而无限续期同一种情绪。
        emotion_message = user_message.strip() if isinstance(user_message, str) else clean_message
        turn_emotion = plan_turn_emotion(
            emotion_message,
            intent_emotion_snapshot,
            relationship_snapshot,
        )

        intent = route.intent
        confidence = route.confidence

        # 接下来要修改共享状态（profile/conversation_history）和写文件，
        # 跟 InitiativeEngine 的后台检查共用同一把锁，避免并发写冲突。
        # 这里没有 AI 调用；锁只保护短暂的内存/文件状态变更。
        with self.lock:
            profile_changed = False
            if route.profile_strategy == "local" and route.profile_update is not None:
                profile_changed = self._apply_profile_update(
                    route.profile_update.as_result(),
                    route.profile_update.confidence,
                    str(user_message or "").strip(),
                )
                if profile_changed:
                    self.context.update(self.emotion, self.profile, self.relationship)

            # 记录用户消息
            self.conversation_history.append({"role": "user", "content": clean_message})
            self.conversation_history, overflow = save_memory(self.conversation_history)
            self._pending_overflow.extend(overflow)

            # 用户刚说了话，更新"上次互动时间"
            update_last_interaction_time()

            # 生成回复时不持有全局状态锁，否则一次流式 AI 请求会把
            # InitiativeEngine 整个阻塞住。在锁内取不可变快照，锁外只读快照，
            # 也避免后台主动消息在流式生成期间改动正在使用的列表。
            history_limit = self.config.get("chat_history_max_messages", 8)
            conversation_snapshot = copy.deepcopy(
                self.conversation_history[-history_limit:]
            )
            context_snapshot = copy.deepcopy(self.context.get_context())
            context_snapshot["turn_emotion"] = copy.deepcopy(turn_emotion)
            router_profile_snapshot = copy.deepcopy(self.profile)
            router_emotion_snapshot = copy.deepcopy(self.emotion)
            router_relationship_snapshot = copy.deepcopy(self.relationship)

        # 精确查表类回复（询问喜好/昵称/情绪状态等），优先查表，查不到再退回 AI
        router_reply = None
        if route.router_eligible and confidence > 0.5:
            router_reply = handle_intent(
                intent,
                clean_message,
                router_profile_snapshot,
                router_emotion_snapshot,
                router_relationship_snapshot,
            )

        prepared = {
            "clean_message": clean_message,
            "emotion_message": emotion_message,
            "intent": intent,
            "confidence": confidence,
            "router_reply": router_reply,
            "conversation_snapshot": conversation_snapshot,
            "context_snapshot": context_snapshot,
            "turn_emotion": turn_emotion,
            "route_source": route.source,
            "route_reason": route.reason,
            "profile_strategy": route.profile_strategy,
            "profile_changed": profile_changed,
        }
        logger.info(
            "[PERF] prepare_turn intent=%s route_source=%s route_reason=%s "
            "profile_strategy=%s preflight_ai=0 duration=%.3fs",
            intent,
            route.source,
            route.reason,
            route.profile_strategy,
            time.perf_counter() - started_at,
        )
        return prepared

    def stream_reply(self, prepared):
        """
        生成回复内容，逐块 yield。
        命中 router 时直接整句 yield 一次；否则走 AI 流式生成。
        """
        started_at = time.perf_counter()
        first_chunk_at = None
        router_reply = prepared["router_reply"]

        if router_reply:
            logger.info("[PERF] stream_reply source=router ttft=0.000s total=0.000s")
            yield router_reply
            return

        def capture_emotion_control(control):
            prepared["ai_emotion_control"] = copy.deepcopy(control)

        try:
            for chunk in chat_with_ai_stream(
                prepared["conversation_snapshot"],
                prepared["context_snapshot"],
                on_emotion_control=capture_emotion_control,
            ):
                if first_chunk_at is None:
                    first_chunk_at = time.perf_counter()
                    logger.info(
                        "[PERF] stream_reply first_chunk ttft=%.3fs",
                        first_chunk_at - started_at,
                    )
                yield chunk
        finally:
            logger.info(
                "[PERF] stream_reply complete total=%.3fs had_chunk=%s",
                time.perf_counter() - started_at,
                first_chunk_at is not None,
            )

    def finalize_turn(self, prepared, raw_reply):
        """
        快速收尾：清洗回复并立即保存助手消息，然后把慢后处理放入
        顺序后台队列。返回后 GUI 即可恢复输入。

        返回清洗后的 reply，方便 main.py 需要时使用。
        """
        started_at = time.perf_counter()
        router_reply = prepared["router_reply"]
        clean_message = prepared["clean_message"]

        reply = router_reply if router_reply else (clean_reply(raw_reply) if raw_reply else "")
        transient_fallback = is_transient_fallback(reply)

        # 即时情绪不再等待“长期事件提取”。这一步只做本地轻量判断，
        # 能让本轮状态、Live2D 和 TTS 在回复展示时就保持一致。
        if transient_fallback:
            interaction_emotion = {
                "mood": "neutral",
                "intensity": 0.0,
                "reason": "skipped",
            }
        elif router_reply:
            # 精确查表回复没有模型措辞可供二次校准，但仍应使用本轮本地
            # 计划，避免沿用上一句话的害羞、担心等语气。
            interaction_emotion = dict(prepared.get("turn_emotion") or {})
        else:
            interaction_emotion = infer_interaction_emotion(
                prepared.get("emotion_message", clean_message),
                raw_reply or reply,
                relationship=self.relationship,
                planned=prepared.get("turn_emotion"),
            )
            interaction_emotion = apply_ai_emotion_control(
                interaction_emotion,
                prepared.get("ai_emotion_control"),
            )
        logger.info(
            "本轮情绪决策 source=%s reason=%s user=%s mood=%s modifier=%s voice=%s local_conf=%.2f ai_conf=%.2f",
            interaction_emotion.get("decision_source", "local"),
            interaction_emotion.get("reason", "unknown"),
            interaction_emotion.get("user_mood", "neutral"),
            interaction_emotion.get("mood", "neutral"),
            interaction_emotion.get("modifier", "none"),
            interaction_emotion.get("voice_style", "conversational"),
            float(interaction_emotion.get("confidence", 0.0) or 0.0),
            float(interaction_emotion.get("ai_confidence", 0.0) or 0.0),
        )
        immediate_emotion_applied = has_interaction_signal(interaction_emotion)

        with self.lock:
            # 短暂故障兜底只展示给用户，不写入角色历史；否则模型会把它
            # 当成 Mio 的正常说话示例，在网络恢复后继续模仿。
            if not transient_fallback:
                self.conversation_history.append({"role": "assistant", "content": reply})
            self.conversation_history, overflow = save_memory(self.conversation_history)
            self._pending_overflow.extend(overflow)
            overflow_to_queue = list(self._pending_overflow)
            self._pending_overflow.clear()

            if immediate_emotion_applied:
                self.emotion = update_emotion(
                    self.emotion,
                    interaction=interaction_emotion,
                )
                save_emotion(self.emotion)
                self.context.update(self.emotion, self.profile, self.relationship)

        if overflow_to_queue:
            queue_summary_messages(overflow_to_queue)

        if immediate_emotion_applied and self.on_state_updated:
            try:
                self.on_state_updated()
            except Exception as e:
                logger.warning("通知界面即时情绪更新失败：%s", e)

        if self._postprocess_accepting and not transient_fallback:
            self._postprocess_queue.put({
                "clean_message": clean_message,
                "reply": reply,
                "router_reply": router_reply,
                "interaction_emotion": interaction_emotion,
                "immediate_emotion_applied": immediate_emotion_applied,
                "profile_strategy": prepared.get("profile_strategy", "none"),
            })

        logger.info(
            "[PERF] finalize_turn fast_commit duration=%.4fs queued_postprocess=%s transient_fallback=%s",
            time.perf_counter() - started_at,
            self._postprocess_accepting and not transient_fallback,
            transient_fallback,
        )

        return reply

    def _postprocess_loop(self):
        while True:
            task = self._postprocess_queue.get()
            try:
                if task is None:
                    return
                self._postprocess_turn(task)
            except Exception as e:
                logger.error("对话后处理失败（已忽略，继续下一轮）：%s", e)
            finally:
                self._postprocess_queue.task_done()

    def _postprocess_turn(self, task):
        started_at = time.perf_counter()
        router_reply = task["router_reply"]
        profile_info = None
        profile_duration = 0.0
        if task.get("profile_strategy") == "deferred_ai":
            profile_started_at = time.perf_counter()
            profile_info = extract_profile_info(
                self.config['api_key'],
                self.config['model'],
                task["clean_message"],
                self.config.get("base_url"),
            )
            profile_duration = time.perf_counter() - profile_started_at

        event = None
        event_duration = 0.0
        if not router_reply:
            event_started_at = time.perf_counter()
            event = extract_event(
                self.config['api_key'],
                self.config['model'],
                task["clean_message"],
                task["reply"],
                self.config.get("base_url"),
            )
            event_duration = time.perf_counter() - event_started_at

        state_changed = False
        event_can_mutate_state = can_event_affect_state(event)
        with self.lock:
            if profile_info is not None:
                profile_changed = self._apply_profile_update(
                    profile_info,
                    0.8,
                    task["clean_message"],
                )
                state_changed = state_changed or profile_changed

            # 即时信号已在 finalize_turn 应用时，不再让稍后返回的长期事件
            # 标签覆盖它，也避免同一轮重复消耗精力。
            if not task.get("immediate_emotion_applied", False) and event_can_mutate_state:
                self.emotion = update_emotion(self.emotion, event)
                save_emotion(self.emotion)
                state_changed = True

            if not router_reply:
                save_event(event)
                if event_can_mutate_state:
                    relationship_before = copy.deepcopy(self.relationship)
                    self.relationship = update_relationship(self.relationship, event)
                    save_relationship(self.relationship)
                    state_changed = state_changed or self.relationship != relationship_before

            self.context.update(self.emotion, self.profile, self.relationship)

        if state_changed and self.on_state_updated:
            try:
                self.on_state_updated()
            except Exception as e:
                logger.warning("通知界面状态更新失败：%s", e)

        summary_started_at = time.perf_counter()
        summarized = summarize_pending_if_ready(
            self.config['api_key'],
            self.config['model'],
            self.config.get("base_url"),
        )
        logger.info(
            "[PERF] postprocess_turn profile=%.3fs event=%.3fs "
            "summary_check=%.3fs summarized=%s total=%.3fs",
            profile_duration,
            event_duration,
            time.perf_counter() - summary_started_at,
            summarized,
            time.perf_counter() - started_at,
        )

    def shutdown(self):
        if self._postprocess_accepting:
            self._postprocess_accepting = False
            self.on_state_updated = None
            self._postprocess_queue.put(None)
        self._postprocess_thread.join(timeout=2)
