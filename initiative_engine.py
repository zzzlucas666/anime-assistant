"""
InitiativeEngine —— 负责判断"要不要主动找用户说话"，以及触发后生成内容。

设计原则：
- "要不要触发"用规则判断（便宜、可控、可预测）
- "触发后说什么"交给 AI 生成（自然、符合人设）
- 按优先级依次判断，命中第一个满足的条件就触发，不会同时触发多条

触发优先级：
    1. 有重要事件还没主动提起过（importance >= 0.7 且未 notified）
    2. 很久没互动 + 情绪低落（mood=sad 或 energy 很低）
    3. 单纯很久没互动 + 熟悉度够高（"好久不见"类）

线程安全：
    这个类的 check_and_trigger() 会读写共享状态（emotion/profile/relationship/
    conversation_history 以及它们对应的文件），调用前必须持有跟主循环共用的同一把锁，
    避免和用户那边的对话流程同时写文件。
"""

import threading
import datetime

from event_manager import get_unnotified_important_events, mark_event_notified
from interaction_tracker import load_last_interaction_time, update_last_interaction_time
from ai.chat import generate_proactive_message
from memory_manager import save_memory


class InitiativeEngine:
    def __init__(
        self,
        config,
        context,
        conversation_history,
        emotion,
        profile,
        relationship,
        lock,
        check_interval_minutes=5,
        idle_threshold_minutes=30,
    ):
        self.config = config
        self.context = context
        self.conversation_history = conversation_history
        self.emotion = emotion
        self.profile = profile
        self.relationship = relationship
        self.lock = lock
        self.check_interval_minutes = check_interval_minutes
        self.idle_threshold_minutes = idle_threshold_minutes
        self._stop_flag = threading.Event()

    # ------------------------------------------------------------------
    # 触发条件判断（纯规则，不调用AI，便宜且可控）
    # ------------------------------------------------------------------

    def _minutes_since_last_interaction(self):
        last_time = load_last_interaction_time()
        if last_time is None:
            return None
        delta = datetime.datetime.now() - last_time
        return delta.total_seconds() / 60

    def _check_event_trigger(self):
        """优先级1：有没有重要事件还没主动提起过"""
        events = get_unnotified_important_events(min_importance=0.7)
        if not events:
            return None
        # 取最近的一条（列表本身按时间顺序追加，最后一条最新）
        event = events[-1]
        reason_hint = f"你想起了之前发生的一件事：{event.get('event', '')}，想主动跟他提起这件事。"
        return event, reason_hint

    def _check_emotion_trigger(self, idle_minutes):
        """优先级2：很久没互动 + 情绪低落"""
        if idle_minutes is None or idle_minutes < self.idle_threshold_minutes:
            return None

        mood = self.emotion.get("mood")
        energy = self.emotion.get("energy", 100)

        if mood == "sad" or energy < 30:
            return (
                f"你已经有一段时间没和Lucas聊天了（约 {int(idle_minutes)} 分钟），"
                f"而且你现在心情不太好（mood={mood}，energy={energy}），"
                f"你有点想找他说说话。"
            )
        return None

    def _check_idle_trigger(self, idle_minutes):
        """优先级3：纯粹很久没聊 + 熟悉度够高"""
        if idle_minutes is None or idle_minutes < self.idle_threshold_minutes:
            return None

        familiarity = self.relationship.get("familiarity", 0)
        if familiarity >= 30:
            return (
                f"你已经有一段时间没和Lucas聊天了（约 {int(idle_minutes)} 分钟），"
                f"你们已经比较熟悉了，你有点想他了，想主动找他说句话。"
            )
        return None

    # ------------------------------------------------------------------
    # 触发后的处理
    # ------------------------------------------------------------------

    def _record_message(self, message):
        self.conversation_history.append({"role": "assistant", "content": message})
        save_memory(self.conversation_history)
        # 主动消息本身也算一次"互动"，避免下一次检查又立刻重复触发
        update_last_interaction_time()

    def check_and_trigger(self):
        """
        按优先级依次判断，命中一个就生成消息并返回；都没命中返回 None。
        调用前必须持有 self.lock（这个方法内部不加锁，由外部 run_loop 统一管理）。
        """
        idle_minutes = self._minutes_since_last_interaction()

        # 优先级1：未提及的重要事件
        event_hit = self._check_event_trigger()
        if event_hit:
            event, reason_hint = event_hit
            message = generate_proactive_message(self.context.get_context(), reason_hint)
            mark_event_notified(event["id"])
            self._record_message(message)
            return message

        # 优先级2：情绪触发
        emotion_reason = self._check_emotion_trigger(idle_minutes)
        if emotion_reason:
            message = generate_proactive_message(self.context.get_context(), emotion_reason)
            self._record_message(message)
            return message

        # 优先级3：纯粹很久没聊 + 熟悉度高
        idle_reason = self._check_idle_trigger(idle_minutes)
        if idle_reason:
            message = generate_proactive_message(self.context.get_context(), idle_reason)
            self._record_message(message)
            return message

        return None

    # ------------------------------------------------------------------
    # 后台线程主循环
    # ------------------------------------------------------------------

    def run_loop(self):
        """
        后台线程入口：每隔 check_interval_minutes 检查一次。
        命中触发条件时直接打印到终端（会和用户当前的输入提示交错显示，
        这是控制台程序的已知限制，后续如果换成图形界面/网页前端可以更优雅地处理）。
        """
        while not self._stop_flag.is_set():
            # wait() 既能精确等待，又能在 stop() 被调用时立刻提前结束等待
            triggered_stop = self._stop_flag.wait(self.check_interval_minutes * 60)
            if triggered_stop:
                break

            try:
                with self.lock:
                    message = self.check_and_trigger()
            except Exception as e:
                print(f"[initiative_engine] 后台检查出错（已忽略，下次继续尝试）：{e}")
                continue

            if message:
                print(f"\n\n[Mio 突然找你说话]\nMio:\n{message}\n\nYou: ", end="", flush=True)

    def stop(self):
        self._stop_flag.set()