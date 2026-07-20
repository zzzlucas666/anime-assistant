"""
Context Builder —— 统一组装"记忆相关"的上下文内容，喂给 chat.py 的 system prompt。

这是 Hybrid Retrieval 的实现位置：不再是"先查语义、再查近期、简单拼接去重"，
而是给每条事件算一个综合分数：

    综合分 = 语义相似度 * SEMANTIC_WEIGHT
           + 重要度     * IMPORTANCE_WEIGHT
           + 时间衰减   * RECENCY_WEIGHT

时间衰减用指数衰减模拟"记忆随时间变模糊"：刚发生的事件衰减分接近1，
超过 RECENCY_HALF_LIFE_DAYS 后衰减到0.5，再往后继续指数下降，但不会衰减到0
（很久以前的事依然有机会被想起来，只是权重很低）。

没有 query_text 时（比如生成开场白），语义维度直接是0，
权重会自动按比例分配给"重要度+时间衰减"这两项，不会让"没有语义信号"
拖累整体排序的合理性。

同时负责控制记忆上下文的总字符预算，避免随着记忆积累让 prompt 无限变长。
"""

import datetime
import math
import time

from anime_assistant.memory.event_manager import load_all_events
from anime_assistant.memory.semantic_memory import compute_similarity_scores
from anime_assistant.memory.long_term_memory import get_summary_text
from anime_assistant.infrastructure.logging import get_logger
from anime_assistant.memory.policy import event_context_text, is_event_retrievable

logger = get_logger(__name__)

# Hybrid Retrieval 三个维度的权重
SEMANTIC_WEIGHT = 0.4
IMPORTANCE_WEIGHT = 0.35
RECENCY_WEIGHT = 0.25

# 时间衰减的半衰期：超过这么多天，衰减分降到0.5
RECENCY_HALF_LIFE_DAYS = 7

# 记忆上下文部分的总字符数预算，避免随着记忆积累让 prompt 无限变长
DEFAULT_MAX_CHARS = 800

# 综合分低于这个值的事件，即使凑数也不值得放进 prompt（避免噪音事件被硬塞进去）
MIN_SCORE_TO_INCLUDE = 0.15

# 当确实执行了语义检索（有 query_text）时，单条事件的语义相似度如果低于这个值，
# 直接排除，不允许"重要度+时间衰减"单独把它捞回来。
# 这是为了修复一个真实出现过的问题：用户问一句具体的话（比如追问某个话题细节），
# 但那个话题在记忆里根本没有真实记录，语义检索理应"查无结果"；如果没有这道门槛，
# 一条完全不相关但"重要度高、发生得比较近"的旧记忆会被硬凑进 prompt，
# AI会把这条不相关的记忆当成"该顺着聊的内容"，导致答非所问、前后矛盾。
MIN_SEMANTIC_RELEVANCE_WHEN_QUERY = 0.25


def _recency_score(created_at_str, now):
    """指数衰减：越久以前的事件，分数越低，但不会衰减到0"""
    if not created_at_str:
        return 0.3  # 没有时间信息的旧数据，给一个中等偏低的默认分，不至于完全被排除
    try:
        created_at = datetime.datetime.fromisoformat(created_at_str)
    except Exception:
        return 0.3

    days_elapsed = max((now - created_at).total_seconds() / 86400, 0)
    decay_rate = math.log(2) / RECENCY_HALF_LIFE_DAYS
    return math.exp(-decay_rate * days_elapsed)


def _rank_events(events, query_text):
    """
    给每条事件算综合分，按分数从高到低排序返回（不做数量截断，
    截断交给调用方按字符预算来做）。
    """
    events = [event for event in events if is_event_retrievable(event)]
    if not events:
        return []

    now = datetime.datetime.now()
    semantic_scores = compute_similarity_scores(query_text, events) if query_text else {}

    has_semantic_signal = bool(semantic_scores)
    if has_semantic_signal:
        w_semantic, w_importance, w_recency = SEMANTIC_WEIGHT, IMPORTANCE_WEIGHT, RECENCY_WEIGHT
    else:
        # 没有语义信号时，把语义的权重按比例分给重要度和时间衰减，
        # 避免"权重总和变小"导致所有分数系统性偏低
        total = IMPORTANCE_WEIGHT + RECENCY_WEIGHT
        w_semantic = 0.0
        w_importance = IMPORTANCE_WEIGHT / total
        w_recency = RECENCY_WEIGHT / total

    scored = []
    for e in events:
        if not isinstance(e, dict):
            continue
        semantic = semantic_scores.get(e.get("id"), 0.0)

        # 关键修复：确实执行了语义检索（有query_text）时，如果这条事件跟
        # 当前话题的语义相关度太低，说明它就是不相关，不能靠"重要度+时间"
        # 硬凑分数把它捞进来——那样只会让AI被不相关的旧记忆带偏话题。
        if has_semantic_signal and semantic < MIN_SEMANTIC_RELEVANCE_WHEN_QUERY:
            continue

        importance = e.get("importance", 0.0)
        recency = _recency_score(e.get("created_at"), now)

        combined = semantic * w_semantic + importance * w_importance + recency * w_recency
        if combined >= MIN_SCORE_TO_INCLUDE:
            scored.append((combined, e))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [e for _, e in scored]


def build_memory_context(
    query_text=None,
    summary_limit=5,
    max_chars=DEFAULT_MAX_CHARS
):
    """
    组装记忆相关的上下文文本，供 chat.py 拼进 system prompt。

    query_text: 当前这轮用户说的话，用来做语义检索。
                如果是 None（比如生成开场白时还没有用户输入），
                综合评分会自动退化为只用"重要度+时间衰减"两个维度。

    返回一个 dict：
        {
            "event_memory_hint": "...",      # 按综合分排序、控制过预算的事件文字
            "long_term_summary_hint": "..."   # 长期摘要文字
        }
    """
    started_at = time.perf_counter()
    all_events = load_all_events()
    loaded_at = time.perf_counter()
    ranked_events = _rank_events(all_events, query_text)
    ranked_at = time.perf_counter()

    event_memory_hint = _build_event_hint_with_budget(ranked_events, max_chars)

    summary_text = get_summary_text(limit=summary_limit)
    long_term_summary_hint = summary_text if summary_text else "（暂时没有需要回顾的长期记忆）"

    result = {
        "event_memory_hint": event_memory_hint,
        "long_term_summary_hint": long_term_summary_hint
    }
    logger.info(
        "[PERF] build_memory_context events_load=%.4fs rank=%.4fs total=%.4fs events=%d",
        loaded_at - started_at,
        ranked_at - loaded_at,
        time.perf_counter() - started_at,
        len(all_events),
    )
    return result


def _build_event_hint_with_budget(events, max_chars):
    """把按综合分排好序的事件列表拼成文字，超过字符预算就停止添加（保留分数更高的）"""
    if not events:
        return "（暂时没有特别值得记住的事情）"

    lines = []
    total_chars = 0
    for e in events:
        desc = event_context_text(e)
        if not desc:
            continue
        line = f"- {desc}"
        if total_chars + len(line) > max_chars:
            break
        lines.append(line)
        total_chars += len(line)

    return "\n".join(lines) if lines else "（暂时没有特别值得记住的事情）"
