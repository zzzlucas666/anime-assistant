"""
长期摘要 —— conversation_history 超过上限（50条）时，
不能让被截断的旧对话彻底消失，而是把它们压缩成一段摘要长期保留，
之后随 system prompt 一起喂给AI，让AI能记得"很久以前聊过的事的大致内容"，
即使具体原文已经不在 conversation_history 里了。

设计为"延后处理"：摘要生成是个AI调用，不应该卡住当前这轮的回复，
应该在用户已经看到回复之后，在后台/锁外悄悄完成。
"""

from openai import OpenAI
import datetime
import uuid
from Storage_utils import safe_load_json, safe_save_json
from logger_utils import get_logger

logger = get_logger(__name__)

SUMMARY_PATH = "data/long_term_summary.json"

# 最多保留多少条摘要（每条摘要本身已经是浓缩过的内容，
# 这个上限是防止摘要本身无限堆积）
MAX_SUMMARIES = 30


def default_summaries():
    return []


def load_summaries():
    return safe_load_json(SUMMARY_PATH, default_summaries)


def save_summaries(summaries):
    # 摘要也不能无限增长，只保留最近的 MAX_SUMMARIES 条
    safe_save_json(SUMMARY_PATH, summaries[-MAX_SUMMARIES:])


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


def summarize_overflow(api_key, model, overflow_messages):
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

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )

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
        return None

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
    return summary