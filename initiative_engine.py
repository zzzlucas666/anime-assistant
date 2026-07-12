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
    check_and_trigger() 内部自己管理跟主循环共用的状态锁。
    触发判断和最终提交在锁内，网络 AI 请求在锁外，避免慢请求
    阻塞用户那边的对话流程。
"""

import threading
import datetime
import copy

from event_manager import get_unnotified_important_events, mark_event_notified
from interaction_tracker import load_last_interaction_time, update_last_interaction_time
from proactive_tracker import can_trigger_proactive, record_proactive_trigger
from ai.chat import generate_proactive_message, get_user_display_name
from logger_utils import get_logger

logger = get_logger(__name__)
from memory_manager import save_memory
from long_term_memory import queue_summary_messages, summarize_pending_if_ready

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
        on_message=None,
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
        # on_message：触发主动消息时的回调，签名为 on_message(message_text)。
        # 控制台模式不传，run_loop 会退回直接 print；GUI模式传入一个会
        # emit Qt信号的函数，让消息能安全地从后台线程传回界面主线程。
        self.on_message = on_message
        self._stop_flag = threading.Event()

    # ------------------------------------------------------------------
    # 触发条件判断（纯规则，不调用AI，便宜且可控）
    # ------------------------------------------------------------------

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
        user_display_name = get_user_display_name(self.profile)

        top_event = signals["top_event"]
        if top_event and top_event.get("importance", 0) >= MIN_EVENT_IMPORTANCE_TO_MENTION:
            reasons.append(f"你想起了之前发生的一件事：{top_event.get('event', '')}，想跟他提起这件事。")

        idle_minutes = signals["idle_minutes"]
        if signals["emotion_score"] > 0.1:
            reasons.append(
                f"你已经有一段时间没和{user_display_name}聊天了（约 {int(idle_minutes or 0)} 分钟），"
                f"而且你现在心情不太好（mood={signals['mood']}，energy={signals['energy']}），"
                f"有点想找他说说话。"
            )

        if signals["idle_score"] > 0.1 and signals["emotion_score"] <= 0.1:
            # 只在情绪信号没有贡献的情况下，才单独提"纯粹很久没聊"，
            # 避免同时出现"情绪不好"和"单纯想聊"两条听起来重复的理由
            reasons.append(
                f"你已经有一段时间没和{user_display_name}聊天了（约 {int(idle_minutes or 0)} 分钟），"
                f"你们已经比较熟悉了（熟悉度 {signals['familiarity_pct']}），有点想他了。"
            )

        if not reasons:
            # 理论上不会发生（总分够才会走到这里），留个兜底避免空提示
            reasons.append(f"你突然有点想主动找{user_display_name}说句话。")

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
        return overflow

    def check_and_trigger(self):
        """
        计算加权综合评分，超过阈值才触发；否则返回 None。

        分三段执行：
        1. 锁内计算触发条件并取上下文快照；
        2. 锁外生成 AI 消息；
        3. 锁内复核用户没有在此期间说话，然后提交状态。

        这样一次慢网络请求不会阻塞正常对话的文件和状态更新。
        """
        cooldown_kwargs = {}
        if self.proactive_min_interval_minutes is not None:
            cooldown_kwargs["min_interval_minutes"] = self.proactive_min_interval_minutes
        if self.proactive_max_per_day is not None:
            cooldown_kwargs["max_per_day"] = self.proactive_max_per_day

        with self.lock:
            # 全局冷却闸：即使触发条件持续满足，也不会无限期频繁触发。
            if not can_trigger_proactive(**cooldown_kwargs):
                return None

            interaction_snapshot = load_last_interaction_time()
            if interaction_snapshot is None:
                idle_minutes = None
            else:
                idle_minutes = (datetime.datetime.now() - interaction_snapshot).total_seconds() / 60

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
            context_snapshot = copy.deepcopy(self.context.get_context())

        # 慢 AI 请求必须在锁外。
        message = generate_proactive_message(context_snapshot, reason_hint)

        with self.lock:
            if self._stop_flag.is_set():
                return None

            # AI 生成期间如果用户已经说话，就不再把这条过时的主动消息
            # 插到新对话中。时间戳来自同一个持久化字段，可直接比较。
            if load_last_interaction_time() != interaction_snapshot:
                logger.info("主动消息生成期间用户已互动，已放弃过时消息。")
                return None

            # 生成期间可能已跨过日界或冷却状态被其他进程更新，
            # 提交前再做一次廉价复核。
            if not can_trigger_proactive(**cooldown_kwargs):
                return None

            top_event = signals["top_event"]
            if top_event and top_event.get("importance", 0) >= MIN_EVENT_IMPORTANCE_TO_MENTION:
                event_id = top_event.get("id")
                if event_id:
                    mark_event_notified(event_id)
                else:
                    logger.warning("待通知事件缺少 id，已跳过通知标记：%s", top_event.get("event", ""))

            overflow = self._record_message(message)

        # 溢出历史先持久化到待处理队列，累计到批量阈值再调一次 AI。
        if overflow:
            queue_summary_messages(overflow)
        summarize_pending_if_ready(
            self.config['api_key'],
            self.config['model'],
            self.config.get("base_url"),
        )

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
                message = self.check_and_trigger()
            except Exception as e:
                logger.error("后台检查出错（已忽略，下次继续尝试）：%s", e)
                continue

            # stop() 可能在消息已提交、但长期摘要仍在生成时被调用。
            # 退出后不再向 GUI 的 QObject 投递回调，避免窗口销毁后还有信号到达。
            if message and not self._stop_flag.is_set():
                if self.on_message:
                    self.on_message(message)
                else:
                    print(f"\n\n[Mio 突然找你说话]\nMio:\n{message}\n")

    def stop(self):
        self._stop_flag.set()
