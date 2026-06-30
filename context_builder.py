"""
Context Builder —— 统一组装"记忆相关"的上下文内容，喂给 chat.py 的 system prompt。

之前的做法是 chat.py 直接调用 event_manager.load_recent_events，拼接成一段文字。
现在多了两个新的记忆来源（语义检索 + 长期摘要），如果还是各自直接拼到 system prompt
里、没有统一的长度控制，prompt 会随着记忆越积累越长，token成本和AI注意力分散的
问题会越来越严重。

这个模块负责：
- 决定这一轮到底该带哪些记忆内容（近期重要事件 + 跟当前话题语义相关的事件 + 长期摘要）
- 去重（同一条事件可能同时命中"近期"和"语义相关"，不能重复出现两次）
- 控制总字符数上限，超出就优先保留更重要/更相关的内容，砍掉次要的
"""

from event_manager import load_recent_events, get_semantically_relevant_events
from long_term_memory import get_summary_text
from logger_utils import get_logger

logger = get_logger(__name__)

# 记忆上下文部分的总字符数预算，避免随着记忆积累让 prompt 无限变长
DEFAULT_MAX_CHARS = 800


def build_memory_context(
    query_text=None,
    recent_limit=5,
    semantic_top_k=3,
    summary_limit=5,
    max_chars=DEFAULT_MAX_CHARS
):
    """
    组装记忆相关的上下文文本，供 chat.py 拼进 system prompt。

    query_text: 当前这轮用户说的话，用来做语义检索（找出跟话题相关的过往事件）。
                如果是 None（比如生成开场白/主动消息时还没有用户输入），就只用"近期事件"。

    返回一个 dict：
        {
            "event_memory_hint": "...",      # 近期+语义相关的事件，去重后的文字
            "long_term_summary_hint": "..."   # 长期摘要文字
        }
    """
    recent_events = load_recent_events(limit=recent_limit, min_importance=0.5)

    semantic_events = []
    if query_text:
        try:
            semantic_events = get_semantically_relevant_events(query_text, top_k=semantic_top_k)
        except Exception as e:
            logger.warning("语义检索出错（已跳过，只使用近期事件）：%s", e)
            semantic_events = []

    # 去重：同一条事件可能同时出现在"近期"和"语义相关"里，按 id 去重，
    # 语义相关的事件排在前面（更贴合当前话题，优先级更高）
    seen_ids = set()
    merged_events = []
    for e in semantic_events + recent_events:
        event_id = e.get("id")
        if event_id and event_id in seen_ids:
            continue
        if event_id:
            seen_ids.add(event_id)
        merged_events.append(e)

    event_memory_hint = _build_event_hint_with_budget(merged_events, max_chars)

    summary_text = get_summary_text(limit=summary_limit)
    long_term_summary_hint = summary_text if summary_text else "（暂时没有需要回顾的长期记忆）"

    return {
        "event_memory_hint": event_memory_hint,
        "long_term_summary_hint": long_term_summary_hint
    }


def _build_event_hint_with_budget(events, max_chars):
    """把事件列表拼成文字，超过字符预算就停止添加（保留前面更重要/更相关的）"""
    if not events:
        return "（暂时没有特别值得记住的事情）"

    lines = []
    total_chars = 0
    for e in events:
        desc = e.get("event", "")
        if not desc:
            continue
        line = f"- {desc}"
        if total_chars + len(line) > max_chars:
            break
        lines.append(line)
        total_chars += len(line)

    return "\n".join(lines) if lines else "（暂时没有特别值得记住的事情）"