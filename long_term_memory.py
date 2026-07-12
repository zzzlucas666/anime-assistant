"""
长期摘要 —— conversation_history 超过上限（50条）时，
不能让被截断的旧对话彻底消失，而是把它们压缩成一段摘要长期保留，
之后随 system prompt 一起喂给AI，让AI能记得"很久以前聊过的事的大致内容"，
即使具体原文已经不在 conversation_history 里了。

设计为"延后处理"：摘要生成是个AI调用，不应该卡住当前这轮的回复，
应该在用户已经看到回复之后，在后台/锁外悄悄完成。
"""

import datetime
import threading
import time
import uuid
from ai.client import create_ai_client
from app_paths import DATA_DIR
from data_models import normalize_messages, normalize_summaries
from Storage_utils import safe_load_json, safe_save_json
from logger_utils import get_logger

logger = get_logger(__name__)

SUMMARY_PATH = str(DATA_DIR / "long_term_summary.json")
PENDING_SUMMARY_PATH = str(DATA_DIR / "pending_summary.json")

# 最多保留多少条摘要（每条摘要本身已经是浓缩过的内容，
# 这个上限是防止摘要本身无限堆积）
MAX_SUMMARIES = 30
SUMMARY_BATCH_MESSAGE_COUNT = 10
_pending_lock = threading.RLock()
_summary_flush_lock = threading.Lock()


def default_summaries():
    return []


def default_pending_messages():
    return []


def load_summaries():
    raw_summaries = safe_load_json(SUMMARY_PATH, default_summaries)
    summaries = normalize_summaries(raw_summaries)
    if summaries != raw_summaries:
        safe_save_json(SUMMARY_PATH, summaries)
    return summaries


def save_summaries(summaries):
    # 摘要也不能无限增长，只保留最近的 MAX_SUMMARIES 条
    normalized = normalize_summaries(summaries)[-MAX_SUMMARIES:]
    summaries[:] = normalized
    return safe_save_json(SUMMARY_PATH, summaries)


def get_summary_text(limit=5):
    """
    取最近 limit 条摘要，拼成一段文字，供 chat.py 的 system prompt 使用。
    """
    summaries = load_summaries()
    recent = summaries[-limit:]
    if not recent:
        return ""

    lines = [f"- {s.get('summary', '')}" for s in recent if s.get("summary")]
    return "\n".join(lines)


def load_pending_summary_messages():
    with _pending_lock:
        raw_messages = safe_load_json(PENDING_SUMMARY_PATH, default_pending_messages)
        messages = normalize_messages(raw_messages)
        if messages != raw_messages:
            safe_save_json(PENDING_SUMMARY_PATH, messages)
        return messages


def queue_summary_messages(messages):
    """把溢出历史先持久化，达到批量阈值后再发起摘要 API。"""
    normalized = normalize_messages(messages)
    if not normalized:
        return len(load_pending_summary_messages())
    with _pending_lock:
        pending = load_pending_summary_messages()
        pending.extend(normalized)
        safe_save_json(PENDING_SUMMARY_PATH, pending)
        logger.info("长期摘要待处理消息：%d/%d", len(pending), SUMMARY_BATCH_MESSAGE_COUNT)
        return len(pending)


def summarize_pending_if_ready(api_key, model, base_url=None, batch_size=SUMMARY_BATCH_MESSAGE_COUNT):
    """如果待处理消息达到 batch_size，在当前后台线程中生成一批摘要。"""
    with _summary_flush_lock:
        with _pending_lock:
            pending = load_pending_summary_messages()
            if len(pending) < batch_size:
                return False
            batch = pending[:batch_size]

        result = summarize_overflow(api_key, model, batch, base_url)
        if result is None:
            # API 失败时保留待处理数据，下次再试。
            return False

        with _pending_lock:
            current = load_pending_summary_messages()
            if current[:len(batch)] == batch:
                del current[:len(batch)]
                safe_save_json(PENDING_SUMMARY_PATH, current)
        return True


def summarize_overflow(api_key, model, overflow_messages, base_url=None):
    """
    把即将被截断丢弃的旧对话压缩成一段摘要。

    overflow_messages: [{"role": "user"/"assistant", "content": "..."}] 格式的消息列表

    这是个AI调用，失败了就跳过（不影响主流程），调用方应该在锁外、
    回复已经显示给用户之后才调用这个函数，避免拖慢当前这轮的响应。
    """
    if not overflow_messages:
        return None

    conversation_text = "\n".join(
        f"{'用户' if m.get('role') == 'user' else 'AI'}: {m.get('content', '')}"
        for m in overflow_messages
        if m.get("content")
    )

    if not conversation_text.strip():
        return None

    started_at = time.perf_counter()
    try:
        client = create_ai_client(api_key, base_url)

        prompt = f"""
请把下面这段对话历史压缩成一段简短的摘要（100字以内），
保留对理解用户、维系长期关系有价值的信息（比如用户提到的喜好、
计划、烦恼、重要经历），省略掉没有实质内容的寒暄。

如果这段对话整体上没有任何值得保留的信息，直接返回空字符串。

对话内容：
{conversation_text}

只返回摘要文字本身，不要解释，不要加引号或其他格式。
"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt}
            ],
            temperature=0
        )

        summary_text = response.choices[0].message.content.strip()

    except Exception as e:
        logger.warning("生成长期摘要失败（已跳过本次摘要）：%s", e)
        return None

    if not summary_text:
        logger.info(
            "[PERF] 长期摘要 messages=%d duration=%.3fs result=empty",
            len(overflow_messages),
            time.perf_counter() - started_at,
        )
        return {}

    summary = {
        "id": uuid.uuid4().hex,
        "summary": summary_text,
        "created_at": datetime.datetime.now().isoformat(),
        "covers_message_count": len(overflow_messages)
    }

    summaries = load_summaries()
    summaries.append(summary)
    save_summaries(summaries)

    logger.info("已生成长期摘要：%s", summary_text)
    logger.info(
        "[PERF] 长期摘要 messages=%d duration=%.3fs result=saved",
        len(overflow_messages),
        time.perf_counter() - started_at,
    )
    return summary
