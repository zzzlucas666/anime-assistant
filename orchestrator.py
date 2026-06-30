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

from concurrent.futures import ThreadPoolExecutor
import re
import threading

from intent_manager import detect_intent
from profile_extractor import extract_profile_info
from router import handle_intent
from ai.chat import chat_with_ai_stream
from emotion_manager import update_emotion, save_emotion
from event_manager import extract_event, save_event
from relationship_manager import update_relationship, save_relationship
from profile_manager import save_profile
from memory_manager import save_memory
from interaction_tracker import update_last_interaction_time
from long_term_memory import summarize_overflow


def clean_reply(reply):
    reply = re.sub(r'（.*?）', '', reply)
    return reply.strip()


class ConversationOrchestrator:
    def __init__(self, config, context, conversation_history, emotion, profile, relationship, lock=None):
        self.config = config
        self.context = context
        self.conversation_history = conversation_history
        self.emotion = emotion
        self.profile = profile
        self.relationship = relationship
        # 跟 InitiativeEngine 共用同一把锁，避免两边同时读写状态文件。
        # 如果没传进来（比如单独测试这个类），就自己建一把，保证不报错。
        self.lock = lock if lock is not None else threading.Lock()
        # 给意图识别 + 资料提取并行用的小线程池，常驻即可，不用每轮新建
        self._executor = ThreadPoolExecutor(max_workers=2)
        # 累积本轮（用户消息+助手消息）产生的溢出消息，finalize_turn 结束时统一交给长期摘要
        self._pending_overflow = []

    @staticmethod
    def _clean_input(user_message):
        return (
            user_message
            .replace("？", "")
            .replace("?", "")
            .strip()
        )

    def _apply_profile_update(self, intent, confidence, profile_info):
        """根据 profile_extractor 的结果更新 profile（如果置信度够高）"""
        action = profile_info.get("action")
        value = profile_info.get("value")

        if intent != "set_profile" or confidence <= 0.5:
            return

        if action == "add_like":
            if value and value not in self.profile["likes"]:
                self.profile["likes"].append(value)

        elif action == "add_dislike":
            if value and value not in self.profile["dislikes"]:
                self.profile["dislikes"].append(value)

        elif action == "set_name":
            if value:
                self.profile["name"] = value

        elif action == "set_nickname":
            if value:
                self.profile["nickname"] = value

        save_profile(self.profile)

    def prepare_turn(self, user_message):
        """
        处理输入清洗、意图识别、资料提取（并行执行），
        并判断本轮要不要走 router 精确回复。
        返回一个 dict，供 stream_reply / finalize_turn 使用。
        """
        clean_message = self._clean_input(user_message)

        # detect_intent 和 extract_profile_info 互不依赖，并行执行省一次往返延迟
        intent_future = self._executor.submit(
            detect_intent,
            self.config['api_key'],
            self.config['model'],
            clean_message,
            self.emotion,
            self.profile
        )
        profile_future = self._executor.submit(
            extract_profile_info,
            self.config['api_key'],
            self.config['model'],
            clean_message
        )

        intent_result = intent_future.result()
        profile_info = profile_future.result()

        intent = intent_result.get("intent", "")
        confidence = intent_result.get("confidence", 0)

        # 接下来要修改共享状态（profile/conversation_history）和写文件，
        # 跟 InitiativeEngine 的后台检查共用同一把锁，避免并发写冲突。
        # AI调用本身（上面的 intent/profile_info）不占锁，不阻塞后台线程。
        with self.lock:
            self._apply_profile_update(intent, confidence, profile_info)

            # 记录用户消息
            self.conversation_history.append({"role": "user", "content": clean_message})
            self.conversation_history, overflow = save_memory(self.conversation_history)
            self._pending_overflow.extend(overflow)

            # 用户刚说了话，更新"上次互动时间"
            update_last_interaction_time()

        # 精确查表类回复（询问喜好/昵称/情绪状态等），优先查表，查不到再退回 AI
        router_reply = None
        if intent in ("get_profile", "emotion_query") and confidence > 0.5:
            router_reply = handle_intent(intent, clean_message, self.profile, self.emotion, self.relationship)

        return {
            "clean_message": clean_message,
            "intent": intent,
            "confidence": confidence,
            "router_reply": router_reply
        }

    def stream_reply(self, prepared):
        """
        生成回复内容，逐块 yield。
        命中 router 时直接整句 yield 一次；否则走 AI 流式生成。
        """
        router_reply = prepared["router_reply"]

        if router_reply:
            yield router_reply
            return

        for chunk in chat_with_ai_stream(
            self.conversation_history,
            self.context.get_context()
        ):
            yield chunk

    def finalize_turn(self, prepared, raw_reply):
        """
        回复打印完之后的收尾工作：
        - 清洗回复文本
        - 更新情绪
        - 提取事件、更新关系（这两步不影响用户已经看到的回复，放在打印之后做即可）
        - 记录助手消息、同步 context

        返回清洗后的 reply，方便 main.py 需要时使用。
        """
        router_reply = prepared["router_reply"]
        clean_message = prepared["clean_message"]

        reply = router_reply if router_reply else (clean_reply(raw_reply) if raw_reply else "")

        # extract_event 是 AI 调用，可能要等几秒，不应该占着锁不放，
        # 否则会让 InitiativeEngine 的后台检查白等。先在锁外面把结果算出来。
        event = None
        if not router_reply:
            event = extract_event(
                self.config['api_key'],
                self.config['model'],
                clean_message,
                reply
            )

        with self.lock:
            # 更新情绪状态（依据 event 的 AI 判断结果，而不是关键词匹配）
            self.emotion = update_emotion(self.emotion, event)
            save_emotion(self.emotion)

            # 更新关系状态（router 命中的精确回复不算"事件"，event 为 None 时也安全跳过）
            if not router_reply:
                save_event(event)
                self.relationship = update_relationship(self.relationship, event)
                save_relationship(self.relationship)

            # 记录助手消息
            self.conversation_history.append({"role": "assistant", "content": reply})
            self.conversation_history, overflow = save_memory(self.conversation_history)
            self._pending_overflow.extend(overflow)

            self.context.update(self.emotion, self.profile, self.relationship)

        # 长期摘要是个AI调用，挪到锁外、回复已经显示给用户之后才做，
        # 不阻塞下一轮输入，也不占着锁让 InitiativeEngine 白等。
        if self._pending_overflow:
            summarize_overflow(
                self.config['api_key'],
                self.config['model'],
                self._pending_overflow
            )
            self._pending_overflow = []

        return reply

    def shutdown(self):
        self._executor.shutdown(wait=False)