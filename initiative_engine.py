"""
InitiativeEngine —— 负责判断"要不要主动找用户说话"，以及触发后生成内容。

设计原则：
- "要不要触发"用规则判断（便宜、可控、可预测）
- "触发后说什么"交给 AI 生成（自然、符合人设）
- 用多信号加权评分代替严格优先级：几个信号可以叠加，
  而不是"命中第一个就触发、后面全部忽略"

评分信号（每个信号先归一化到 0~1，再按权重加权求和）：
    - event_score：未提及的重要事件里，importance 最高的那一条的重要度
    - emotion_score：情绪低落程度（mood=sad / energy 过低），
      并随"空闲时间是否接近阈值"平滑放大（idle_factor）
    - idle_score：纯粹很久没聊 + 熟悉度，同样按 idle_factor 平滑放大

    总分 = event_score * EVENT_WEIGHT
         + emotion_score * EMOTION_WEIGHT
         + idle_score * IDLE_WEIGHT

    总分 >= TRIGGER_THRESHOLD 才会真正触发。

这样设计的好处：比如"情绪有点低落 + 刚好有一条还没提起的事"，
这两个单独看可能都没强到能触发，但叠加起来分数够了，也会触发——
而旧版严格优先级下，命中优先级1（事件）就直接返回，根本不会让
情绪信号有"参与判断"的机会。

线程安全：
    这个类的 check_and_trigger() 会读写共享状态（emotion/profile/relationship/
    conversation_history 以及它们对应的文件），调用前必须持有跟主循环共用的同一把锁，
    避免和用户那边的对话流程同时写文件。
"""

import threading
import datetime

from event_manager import get_unnotified_important_events, mark_event_notified
from interaction_tracker import load_last_interaction_time, update_last_interaction_time
from proactive_tracker import can_trigger_proactive, record_proactive_trigger
from ai.chat import generate_proactive_message
from logger_utils import get_logger

logger = get_logger(__name__)
from memory_manager import save_memory
from long_term_memory import summarize_overflow

# 各信号的权重，加起来不要求恰好是1，但保持在同一量级方便理解和调参
EVENT_WEIGHT = 0.5
EMOTION_WEIGHT = 0.3
IDLE_WEIGHT = 0.2

# 总分超过这个阈值才真正触发。可以理解成"综合渴望聊天程度"的及格线。
TRIGGER_THRESHOLD = 0.4

# 事件的重要度至少要到这个程度，才会被写进 reason_hint 里、并在触发后标记为"已提及"
# （重要度太低的事件，即使凑够了分数触发，也不适合被当作"主动提起的具体内容"）
MIN_EVENT_IMPORTANCE_TO_MENTION = 0.5

# 情绪/熟悉度这类信号依赖"空闲时间"，这里限制 idle_factor 的上限，
# 避免空闲特别久之后分数无限膨胀（比如挂机一整周，分数也不该比挂机一天高太多）
MAX_IDLE_FACTOR = 1.5


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
        proactive_min_interval_minutes=None,
        proactive_max_per_day=None,
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
        # 没传就用 proactive_tracker 里的默认值
        self.proactive_min_interval_minutes = proactive_min_interval_minutes
        self.proactive_max_per_day = proactive_max_per_day
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

    def _compute_signals(self, idle_minutes):
        """
        计算三个信号的原始分数（0~1）以及相关的中间数据，
        供 check_and_trigger 统一加权、统一决定要不要触发。
        """
        # idle_factor：随空闲时间逼近阈值平滑放大，封顶 MAX_IDLE_FACTOR。
        # 刚互动完（idle_minutes 很小）时这个因子接近0，
        # 自然压低 emotion_score / idle_score，不需要再额外加硬门槛。
        if idle_minutes is None:
            idle_factor = 0.0
        else:
            idle_factor = min(idle_minutes / self.idle_threshold_minutes, MAX_IDLE_FACTOR)

        # 信号1：未提及的重要事件，取重要度最高的一条
        unnotified_events = get_unnotified_important_events(min_importance=0.5)
        top_event = None
        if unnotified_events:
            top_event = max(unnotified_events, key=lambda e: e.get("importance", 0))
        event_score = top_event.get("importance", 0.0) if top_event else 0.0

        # 信号2：情绪低落程度，随空闲时间放大
        mood = self.emotion.get("mood")
        energy = self.emotion.get("energy", 100)
        if mood == "sad":
            base_emotion_score = 1.0
        elif energy < 30:
            base_emotion_score = 0.7
        else:
            base_emotion_score = 0.0
        emotion_score = base_emotion_score * idle_factor

        # 信号3：纯粹很久没聊 + 熟悉度，随空闲时间放大
        familiarity = self.relationship.get("familiarity", 0) / 100
        idle_score = idle_factor * familiarity

        return {
            "event_score": event_score,
            "emotion_score": emotion_score,
            "idle_score": idle_score,
            "top_event": top_event,
            "idle_minutes": idle_minutes,
            "mood": mood,
            "energy": energy,
            "familiarity_pct": self.relationship.get("familiarity", 0),
        }

    def _build_reason_hint(self, signals):
        """
        把贡献明显的信号拼成一段自然语言提示，给AI生成主动消息时参考。
        可能同时包含多条理由（这正是加权评分相对严格优先级的优势：
        信号可以叠加着一起说明，而不是只能挑一个"最优先"的理由）。
        """
        reasons = []

        top_event = signals["top_event"]
        if top_event and top_event.get("importance", 0) >= MIN_EVENT_IMPORTANCE_TO_MENTION:
            reasons.append(f"你想起了之前发生的一件事：{top_event.get('event', '')}，想跟他提起这件事。")

        idle_minutes = signals["idle_minutes"]
        if signals["emotion_score"] > 0.1:
            reasons.append(
                f"你已经有一段时间没和Lucas聊天了（约 {int(idle_minutes or 0)} 分钟），"
                f"而且你现在心情不太好（mood={signals['mood']}，energy={signals['energy']}），"
                f"有点想找他说说话。"
            )

        if signals["idle_score"] > 0.1 and signals["emotion_score"] <= 0.1:
            # 只在情绪信号没有贡献的情况下，才单独提"纯粹很久没聊"，
            # 避免同时出现"情绪不好"和"单纯想聊"两条听起来重复的理由
            reasons.append(
                f"你已经有一段时间没和Lucas聊天了（约 {int(idle_minutes or 0)} 分钟），"
                f"你们已经比较熟悉了（熟悉度 {signals['familiarity_pct']}），有点想他了。"
            )

        if not reasons:
            # 理论上不会发生（总分够才会走到这里），留个兜底避免空提示
            reasons.append("你突然有点想主动找Lucas说句话。")

        return " ".join(reasons)

    # ------------------------------------------------------------------
    # 触发后的处理
    # ------------------------------------------------------------------

    def _record_message(self, message):
        self.conversation_history.append({"role": "assistant", "content": message})
        self.conversation_history, overflow = save_memory(self.conversation_history)
        # 主动消息本身也算一次"互动"，避免下一次检查又立刻重复触发
        update_last_interaction_time()
        # 记录冷却状态（今日计数 + 上次触发时间）
        record_proactive_trigger()

        # 注意：这里是在 self.lock 持有期间调用的AI请求，理论上不是最优实践
        # （正常对话流程里我们都把AI调用挪到锁外做），但主动消息本身受冷却限制，
        # 触发频率很低（几小时一次），这个权衡是可以接受的，不值得为此增加复杂度。
        if overflow:
            summarize_overflow(self.config['api_key'], self.config['model'], overflow)

    def check_and_trigger(self):
        """
        计算加权综合评分，超过阈值才触发；否则返回 None。
        调用前必须持有 self.lock（这个方法内部不加锁，由外部 run_loop 统一管理）。
        """
        # 全局冷却闸：即使触发条件持续满足，也不会无限期频繁触发
        cooldown_kwargs = {}
        if self.proactive_min_interval_minutes is not None:
            cooldown_kwargs["min_interval_minutes"] = self.proactive_min_interval_minutes
        if self.proactive_max_per_day is not None:
            cooldown_kwargs["max_per_day"] = self.proactive_max_per_day

        if not can_trigger_proactive(**cooldown_kwargs):
            return None

        idle_minutes = self._minutes_since_last_interaction()
        signals = self._compute_signals(idle_minutes)

        total_score = (
            signals["event_score"] * EVENT_WEIGHT
            + signals["emotion_score"] * EMOTION_WEIGHT
            + signals["idle_score"] * IDLE_WEIGHT
        )

        logger.info(
            "主动消息评分：event=%.2f emotion=%.2f idle=%.2f -> 总分=%.2f（阈值=%.2f）",
            signals["event_score"], signals["emotion_score"], signals["idle_score"],
            total_score, TRIGGER_THRESHOLD
        )

        if total_score < TRIGGER_THRESHOLD:
            return None

        reason_hint = self._build_reason_hint(signals)
        message = generate_proactive_message(self.context.get_context(), reason_hint)

        top_event = signals["top_event"]
        if top_event and top_event.get("importance", 0) >= MIN_EVENT_IMPORTANCE_TO_MENTION:
            mark_event_notified(top_event["id"])

        self._record_message(message)
        return message

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
                logger.error("后台检查出错（已忽略，下次继续尝试）：%s", e)
                continue

            if message:
                print(f"\n\n[Mio 突然找你说话]\nMio:\n{message}\n")

    def stop(self):
        self._stop_flag.set()