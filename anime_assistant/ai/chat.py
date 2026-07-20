import json
import re
import time
from anime_assistant.ai.client import create_ai_client
from anime_assistant.ai.fallbacks import FALLBACK_REPLIES
from anime_assistant.infrastructure.paths import DATA_DIR
from anime_assistant.conversation.context_builder import build_memory_context
from anime_assistant.infrastructure.models import ALLOWED_VOICE_STYLES
from anime_assistant.infrastructure.logging import get_logger
from anime_assistant.character.relationship_behavior import build_relationship_hint
from anime_assistant.ai.prompts import build_five_layer_prompt, build_turn_emotion_hint

logger = get_logger(__name__)

EMOTION_CONTROL_PREFIX = "<mio:"
EMOTION_CONTROL_USER_MOODS = {
    "neutral", "happy", "sad", "anxious", "angry", "lonely",
    "bored", "stressed", "tired", "disappointed",
}
EMOTION_CONTROL_REACTIONS = {
    "neutral", "happy", "shy", "sad", "worried", "touched",
    "curious", "surprised", "annoyed",
}
EMOTION_CONTROL_PATTERN = re.compile(
    r"<mio:([a-z_]+)\|([a-z_]+)\|([a-z_]+)\|"
    r"([01](?:\.\d+)?)\|([01](?:\.\d+)?)>"
)


def parse_emotion_control_tag(tag):
    """解析主回复末尾的内部控制标签；无效标签不会进入情绪系统。"""
    if not isinstance(tag, str):
        return None
    match = EMOTION_CONTROL_PATTERN.fullmatch(tag.strip().lower())
    if not match:
        return None
    user_mood, reaction, voice_style, strength_text, confidence_text = match.groups()
    if (
        user_mood not in EMOTION_CONTROL_USER_MOODS
        or reaction not in EMOTION_CONTROL_REACTIONS
        or voice_style not in ALLOWED_VOICE_STYLES
    ):
        return None
    strength = float(strength_text)
    confidence = float(confidence_text)
    if not (0.0 <= strength <= 1.0 and 0.0 <= confidence <= 1.0):
        return None
    return {
        "user_mood": user_mood,
        "reaction": reaction,
        "voice_style": voice_style,
        "strength": strength,
        "confidence": confidence,
    }


class EmotionControlStreamFilter:
    """跨流式分块隐藏控制标签，避免它闪到 GUI 或被 TTS 读出。"""
    def __init__(self):
        self._pending = ""
        self._hidden = ""
        self._hiding = False
        self.control = None

    @property
    def saw_control_prefix(self):
        return self._hiding

    def _consume_hidden(self, text):
        self._hidden += text
        end_index = self._hidden.find(">")
        if end_index >= 0 and self.control is None:
            self.control = parse_emotion_control_tag(self._hidden[:end_index + 1])

    def feed(self, text):
        if not isinstance(text, str) or not text:
            return ""
        if self._hiding:
            self._consume_hidden(text)
            return ""

        self._pending += text
        marker_index = self._pending.find(EMOTION_CONTROL_PREFIX)
        if marker_index >= 0:
            visible = self._pending[:marker_index]
            hidden = self._pending[marker_index:]
            self._pending = ""
            self._hiding = True
            self._consume_hidden(hidden)
            return visible

        overlap = 0
        max_overlap = min(len(self._pending), len(EMOTION_CONTROL_PREFIX) - 1)
        for size in range(max_overlap, 0, -1):
            if self._pending.endswith(EMOTION_CONTROL_PREFIX[:size]):
                overlap = size
                break
        if overlap:
            visible = self._pending[:-overlap]
            self._pending = self._pending[-overlap:]
        else:
            visible = self._pending
            self._pending = ""
        return visible

    def finish(self):
        if self._hiding:
            return ""
        visible = self._pending
        self._pending = ""
        return visible

def load_persona():
    with open(DATA_DIR / "persona.json", "r", encoding="utf-8") as f:
        return json.load(f)


def get_user_display_name(profile):
    """返回用于内部提示词的用户称呼，不再绑定某个特定用户名。"""
    profile = profile or {}
    return profile.get("nickname") or profile.get("name") or "对方"


def build_system_prompt(
    context,
    query_text=None,
    include_emotion_control=True,
    mode="chat",
    purpose_hint=None,
):
    """Build the shared five-layer system prompt for every conversation mode.

    query_text is used only to retrieve relevant trusted memories. Greeting
    mode may pass None; proactive mode passes its internal topic or motive.
    """
    persona = load_persona()
    memory_context = build_memory_context(query_text=query_text)
    return build_five_layer_prompt(
        context=context,
        persona=persona,
        memory_context=memory_context,
        mode=mode,
        include_emotion_control=include_emotion_control,
        purpose_hint=purpose_hint,
    )


def _extract_latest_user_message(messages):
    """从消息列表里取出最后一条 role=user 的内容，用作语义检索的查询文本"""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content")
    return None


def _daily_chat_request_options(context, **options):
    """为面向用户的角色对话补充 DeepSeek 日常聊天参数。"""
    result = dict(options)
    base_url = str(context["config"].get("base_url") or "").lower()
    if "api.deepseek.com" in base_url:
        thinking_enabled = context["config"].get("chat_thinking_enabled", False)
        result["extra_body"] = {
            "thinking": {"type": "enabled" if thinking_enabled else "disabled"}
        }
    return result


def _normalize_short_character_line(text, max_chars=70):
    """清掉舞台动作和多余换行，并为开场/主动消息提供最后一道长度保护。"""
    if not isinstance(text, str):
        return ""
    text = re.sub(r"（.*?）|\(.*?\)", "", text, flags=re.DOTALL)
    text = " ".join(text.split()).strip()
    if len(text) <= max_chars:
        return text

    boundary = max(
        (text.rfind(mark, 0, max_chars + 1) for mark in "。！？!?"),
        default=-1,
    )
    if boundary >= 12:
        return text[:boundary + 1]
    return text[:max_chars].rstrip("，、；：… ") + "。"


def _create_stream(messages, context):
    """单次创建一个流式请求，失败时直接抛出异常，由上层决定是否重试"""
    started_at = time.perf_counter()
    query_text = _extract_latest_user_message(messages)
    system_prompt = build_system_prompt(context, query_text=query_text)
    prompt_ready_at = time.perf_counter()

    client = create_ai_client(
        context["config"]["api_key"],
        context["config"].get("base_url"),
    )

    full_messages = [
        {"role": "system", "content": system_prompt}
    ] + messages

    request_options = _daily_chat_request_options(
        context,
        model=context["config"]["model"],
        messages=full_messages,
        stream=True,
        max_tokens=112,
    )

    stream = client.chat.completions.create(**request_options)
    logger.info(
        "[PERF] chat_stream_setup prompt=%.3fs connect=%.3fs total=%.3fs",
        prompt_ready_at - started_at,
        time.perf_counter() - prompt_ready_at,
        time.perf_counter() - started_at,
    )
    return stream


def chat_with_ai_stream(messages, context, on_emotion_control=None):
    """
    流式调用 AI，逐块 yield 文本片段。

    容错策略：
    - 如果"创建连接"失败，或者连接正常结束却没有返回任何文字，
      都会自动重试一次；仍然失败则 yield 一句角色内兜底话术。
    - 如果连接建立成功、已经开始吐字之后才中途断线，
      不会重试（避免内容重复），而是在已输出内容后补一句自然的收尾。
    """
    import random

    last_error = None

    for attempt in range(2):  # 最多尝试 2 次：首次 + 空流/异常重试 1 次
        try:
            stream = _create_stream(messages, context)
        except Exception as e:
            last_error = e
            logger.warning("创建对话流失败（第 %d 次尝试）：%s", attempt + 1, e)
            continue

        has_yielded_any = False
        control_filter = EmotionControlStreamFilter()
        reasoning_chars = 0
        finish_reasons = []
        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                reasoning_chars += len(
                    getattr(delta, "reasoning_content", None) or ""
                )
                if choice.finish_reason:
                    finish_reasons.append(choice.finish_reason)
                if delta and delta.content:
                    visible = control_filter.feed(delta.content)
                    if visible:
                        has_yielded_any = True
                        yield visible
        except Exception as e:
            last_error = e
            logger.warning("流式输出中途中断（第 %d 次尝试）：%s", attempt + 1, e)
            tail = control_filter.finish()
            if tail:
                has_yielded_any = True
                yield tail
            if has_yielded_any:
                if control_filter.control and callable(on_emotion_control):
                    try:
                        on_emotion_control(control_filter.control)
                    except Exception as callback_error:
                        logger.warning("提交回复情绪控制信息失败：%s", callback_error)
                if control_filter.saw_control_prefix:
                    # 可见回复已经完整，只是末尾内部标签被截断，不给用户
                    # 追加“网络卡顿”之类无关话术，直接回退本地情绪计划。
                    return
                # 已经说了一部分话，不重试（避免重复），自然收个尾
                yield "…呃，网络突然卡了一下，先这样吧。"
                return
            continue

        tail = control_filter.finish()
        if tail:
            has_yielded_any = True
            yield tail
        if control_filter.control and callable(on_emotion_control):
            try:
                on_emotion_control(control_filter.control)
            except Exception as e:
                logger.warning("提交回复情绪控制信息失败：%s", e)

        logger.info(
            "对话流完成：attempt=%d content=%s emotion_control=%s reasoning_chars=%d finish=%s",
            attempt + 1,
            has_yielded_any,
            control_filter.control is not None,
            reasoning_chars,
            finish_reasons or ["unknown"],
        )

        if has_yielded_any:
            return

        # 有些兼容 OpenAI 协议的服务会以“成功”状态结束请求，
        # 但所有 delta.content 都为空。此前这里会让 GUI 静默结束。
        last_error = RuntimeError("对话流正常结束但未返回文字")
        logger.warning("对话流为空（第 %d 次尝试），准备重试", attempt + 1)

    logger.error("重试后仍未获得回复，使用兜底话术。最后一次错误：%s", last_error)
    yield random.choice(FALLBACK_REPLIES)


def chat_with_ai(messages, context):
    """
    非流式版本，保留作为兜底（比如脚本调用、测试时更方便）。
    内部直接复用流式版本拼接完整结果。
    """
    return "".join(chat_with_ai_stream(messages, context))


def generate_greeting(
    context
):
    client = create_ai_client(
        context["config"]["api_key"],
        context["config"].get("base_url"),
    )

    prompt = build_system_prompt(
        context,
        query_text=None,
        include_emotion_control=False,
        mode="greeting",
    )
    try:
        response = client.chat.completions.create(**_daily_chat_request_options(
            context,
            model=context['config']['model'],
            messages=[
                {
                    "role": "system",
                    "content": prompt
                }
            ],
            max_tokens=40,
        ))
        return _normalize_short_character_line(
            response.choices[0].message.content,
            max_chars=38,
        ) or "嗯…你来了。"
    except Exception as e:
        logger.warning("生成开场白失败，使用默认开场白：%s", e)
        return "嗯…你来了。"


# 主动消息彻底失败时的兜底话术
PROACTIVE_FALLBACK_REPLIES = (
    "现在有空吗？没什么……就是想和你说句话。",
    "今天还顺利吗？别太勉强自己。",
    "你在忙吗？有空的话，陪我聊一会儿吧。",
)


def generate_proactive_message(context, reason_hint):
    """
    生成一句"主动找用户说话"的内容。
    复用五层 build_system_prompt，并通过 mode=proactive 注入主动场景，
    因而与正常聊天、启动问候共享身份、价值观和行为策略。

    reason_hint: 一句描述触发原因的话（给AI看的内部提示，不会展示给用户），
                 比如"已经很久没聊天了，而且心情不太好，想找他说说话"。
    """
    import random

    system_prompt = build_system_prompt(
        context,
        query_text=reason_hint,
        include_emotion_control=False,
        mode="proactive",
        purpose_hint=reason_hint,
    )

    client = create_ai_client(
        context["config"]["api_key"],
        context["config"].get("base_url"),
    )

    try:
        response = client.chat.completions.create(**_daily_chat_request_options(
            context,
            model=context["config"]["model"],
            messages=[
                {"role": "system", "content": system_prompt}
            ],
            max_tokens=48,
        ))
        return _normalize_short_character_line(
            response.choices[0].message.content,
            max_chars=48,
        ) or random.choice(PROACTIVE_FALLBACK_REPLIES)
    except Exception as e:
        logger.warning("生成主动消息失败，使用兜底话术：%s", e)
        return random.choice(PROACTIVE_FALLBACK_REPLIES)
