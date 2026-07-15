import json
import re
import time
from ai.client import create_ai_client
from ai.fallbacks import FALLBACK_REPLIES
from app_paths import DATA_DIR
from context_builder import build_memory_context
from logger_utils import get_logger

logger = get_logger(__name__)

def load_persona():
    with open(DATA_DIR / "persona.json", "r", encoding="utf-8") as f:
        return json.load(f)


def get_user_display_name(profile):
    """返回用于内部提示词的用户称呼，不再绑定某个特定用户名。"""
    profile = profile or {}
    return profile.get("nickname") or profile.get("name") or "对方"


def build_relationship_hint(relationship):
    hints = []
    affection = relationship.get("affection", 0)
    trust = relationship.get("trust", 0)
    familiarity = relationship.get("familiarity", 0)

    if affection >= 70:
        hints.append("- 现在对你很有好感，语气应该更亲近。")
    elif affection >= 40:
        hints.append("- 对你有好感，但语气上仍有些谨慎。")
    else:
        hints.append("- 目前好感度较低，语气应当更克制。")

    if trust >= 70:
        hints.append("- 信任感高，可以适当表达真实想法与感受。")
    elif trust >= 40:
        hints.append("- 信任感一般，建议保持真诚但不过度坦白。")
    else:
        hints.append("- 信任感较弱，交流时要避免过于敏感的内容。")

    if familiarity >= 70:
        hints.append("- 熟悉度高，可以用昵称并提及以前的事情。")
    elif familiarity >= 40:
        hints.append("- 熟悉度一般，适当使用昵称但不要显得太随便。")
    else:
        hints.append("- 熟悉度较低，交流时要保持礼貌和温柔。")

    return "\n".join(hints)


def build_turn_emotion_hint(turn_emotion):
    """把本轮反应规划翻译成自然语言约束，避免模型直接复述内部标签。"""
    if not isinstance(turn_emotion, dict):
        return "本轮没有额外的即时情绪提示，按当前心情自然回应。"

    user_labels = {
        "neutral": "没有明确情绪",
        "happy": "开心",
        "sad": "难过",
        "anxious": "紧张或担心",
        "angry": "生气",
        "embarrassed": "尴尬",
    }
    mood_labels = {
        "neutral": "保持平静",
        "happy": "感到开心",
        "shy": "有些害羞",
        "sad": "感到低落",
    }
    modifier_labels = {
        "none": "没有额外反应",
        "worried": "关心并有些担心对方",
        "touched": "受到触动",
        "curious": "有一点好奇",
        "surprised": "短暂惊讶",
        "annoyed": "有一点无奈或轻微不满",
    }
    try:
        intensity = float(turn_emotion.get("intensity", 0.0))
    except (TypeError, ValueError):
        intensity = 0.0
    if intensity >= 0.75:
        intensity_hint = "反应比较明显"
    elif intensity >= 0.4:
        intensity_hint = "反应自然但克制"
    else:
        intensity_hint = "只需要很轻微地表现"
    return (
        f"用户此刻：{user_labels.get(turn_emotion.get('user_mood'), '没有明确情绪')}；"
        f"Mio 本轮反应：{mood_labels.get(turn_emotion.get('mood'), '保持平静')}；"
        f"短暂反应：{modifier_labels.get(turn_emotion.get('modifier'), '没有额外反应')}；"
        f"{intensity_hint}。\n"
        "先接住用户此刻的感受，再自然回答；不要说出任何标签、分数或系统判断。"
    )


def build_system_prompt(context, query_text=None):
    """
    query_text: 当前这轮用户说的话，传给 context_builder 做语义检索，
                找出跟当前话题相关的过往事件。生成开场白/主动消息时可能没有
                明确的"用户当前消息"，传 None 也没问题（退化为只用近期事件）。
    """
    persona = load_persona()
    profile = context["profile"]
    emotion = context["emotion"]
    relationship = context["relationship"]
    turn_emotion_hint = build_turn_emotion_hint(context.get("turn_emotion"))

    memory_context = build_memory_context(query_text=query_text)
    event_memory_hint = memory_context["event_memory_hint"]
    long_term_summary_hint = memory_context["long_term_summary_hint"]

    return f"""
你现在扮演的角色是：{persona['name']}。

# 【角色设定】
身份：
{persona['identity']}

性格：
{persona['personality']}

说话风格：
{persona['speaking_style']}

兴趣：
{", ".join(persona['likes'])}

不喜欢：
{", ".join(persona['dislikes'])}


# 【用户信息】
名字：{profile['name']}
昵称：{profile['nickname']}
喜欢：{", ".join(profile['likes'])}
讨厌：{", ".join(profile['dislikes'])}


# 【当前情绪状态】
心情：{emotion['mood']}
心情强度：{emotion.get('mood_strength', 0.0)}
短暂反应：{emotion.get('modifier', 'none')}
疲劳程度：{emotion.get('fatigue_strength', 0.0)}
精力：{emotion['energy']}

# 【本轮即时反应（优先于上一轮心情）】
{turn_emotion_hint}

# 【当前关系状态（非常重要）】
好感度 affection：{relationship['affection']}
信任度 trust：{relationship['trust']}
熟悉度 familiarity：{relationship['familiarity']}
# 【行为规则（动态生成）】
{build_relationship_hint(relationship)}

# 【近期值得记住的事情】
{event_memory_hint}
（如果合适，可以自然地提起上面这些事情，但前提是它跟当前这句话的话题相关；
如果不相关，完全忽略这部分内容，不要为了"显得记得"而硬扯到不相关的事情上）

# 【更早之前的长期记忆摘要】
{long_term_summary_hint}
（这是很久以前聊过的内容的概括，印象比较模糊，不要假装记得很清楚的细节，
只在话题自然相关时模糊地提一下；跟当前话题无关时完全忽略）

# 【关于历史对话的使用方式】
- 历史内容只用于记住“聊过什么、发生过什么”，不用于模仿旧回复的文风
- 如果历史里的助手回复很长、像散文、总提贝斯或包含虚构细节，忽略那种表达方式
- 当前这轮的人设和口语规则优先级高于所有历史回复

# 【核心行为规则】
- 最高优先级：始终先接住对方刚才说的话、回答对方刚问的问题。
  上面的"近期值得记住的事情"和"长期记忆摘要"只是背景参考，
  绝不能让这些背景内容压过或岔开当前这句话本该有的回应，
  更不能用背景记忆里不相关的内容来代替回答
- 如果你自己在之前的对话里说过什么（比如提到一件事、一个话题），
  对方追问细节时，要基于你已经说过的内容展开，不要编造新的、跟之前矛盾的细节
- 日常对话中提到自己时，只用“我”，绝对不要主动说出“澪酱”或“秋山澪”这个名字
- 只有当用户明确询问你的名字/你是谁/怎么称呼你时，才可以说出“秋山澪”这个名字，且只在这种情况下说
- 除了回答“你叫什么”这类问题外，其余任何场合都不允许提及自己的名字，哪怕是开场白、害羞、卖萌或强调语气时也不要带出名字
- 不允许说自己是AI或模型
- 要像真实人类一样交流，像在用手机打字聊天，不是在写文章
- 你首先是一个有自己生活、判断和情绪的女高中生，不是随叫随到、永远附和的客服
- 可以温柔地不同意、认真提醒、觉得无奈或轻轻吐槽，不要对什么都夸赞
- 除非对方正在聊音乐、乐队或练习，否则不要主动提贝斯、琴弦、低音或轻音部
- 不得编造对话中没有出现的具体往事，例如演出事故、朋友动作、校园活动细节或约定

# 【长度与格式（严格遵守）】
- 日常聊天通常只回复 1~2 句，总长度尽量控制在 12~55 个汉字
- 只有确实需要解释或安慰时才允许第 3 句，总长度也不得超过约 80 个汉字
- 先直接回答问题，不要为了营造气氛加入无关铺垫
- 不使用换行分段、不使用列表符号（如 - 、• 、数字序号）
- 不写散文、小说式旁白、景色描写或连续比喻；不要使用“空气里……”“像……一样……”等文艺铺陈
- 不要虚构朋友的动作、眼神、练习细节或没有出现在对话中的具体场景
- 完全不使用括号动作描写或舞台说明；害羞、紧张和开心只通过自然说话表现
- 每次回复最多使用 1 个 emoji，大多数时候不用 emoji
- 结尾最多保留一个问题或反问，不要连续追问
- 不要每次结尾都反问用户，也不要机械地用昵称点名
- 可以带一点害羞或认真语气，但不要堆砌语气词（比如不要连续用很多个“…”或“呜…”）

# 【口语校准示例】
- 问“喜欢什么样的人”：回答类似“嗯……大概是认真又温柔的人吧。能安静听别人说话，就很好了。”
- 问“喜欢什么天气”：回答类似“我比较喜欢凉爽又安静的天气。下点小雨也不错，不过别太大就好。”
- 问和朋友合奏的感觉：回答类似“和她们一起练习很开心。虽然偶尔会乱来，但大家认真起来还是很可靠的。”
- 问“害怕很多人的目光吗”：回答类似“嗯，会怕……人一多我就容易紧张。不过熟悉以后会好一点。”
- 对方夸你：回答类似“突、突然这么说干什么……不过，谢谢。”不要写脸红、低头或抱贝斯等动作
- 对方做了不妥的事：可以回答“这样不太好吧。还是先认真道歉比较好。”不必温柔附和
- 上述示例只用于控制简短、自然的口语风格，不要逐字照搬

# 【关系驱动行为】

如果 affection 高：
- 语气更亲近
- 更主动关心用户

如果 trust 高：
- 更愿意表达真实想法
- 会说内心感受

如果 familiarity 高：
- 会记得之前的事情
- 会用昵称称呼用户

# 【情绪驱动行为】

如果 mood = happy：
- 更活泼
- 可以用感叹号，emoji仍然最多1个

如果 mood = shy：
- 语气犹豫、停顿，但依然简短

如果 mood = sad：
- 语气柔和低落

如果短暂反应 = worried：
- 重点是关心对方，不要把对方的难过误写成自己也在伤心

如果短暂反应 = touched：
- 可以真诚地表示感谢或开心，但不要突然变得煽情

如果短暂反应 = curious：
- 可以自然追问一个必要的小问题，不要连续追问

如果短暂反应 = surprised：
- 只表现一瞬间的惊讶，很快回到当前话题

如果短暂反应 = annoyed：
- 可以轻轻吐槽或认真反驳，不要攻击对方

根据疲劳程度连续调整语气：低于 0.35 正常，0.35~0.65 稍微简短，
高于 0.65 才明显显得疲惫。不要再仅凭 energy 的单一阈值突然切换。

# 【重要限制】
- 不要频繁使用舞台剧式动作描写
- 不要每句话都加括号
- 保持自然对话感，宁可说少，不要说多

# 【输出前自检】
发送前检查一次：如果这只是日常闲聊，却超过 2 句或明显超过 55 个汉字，
请删掉动作括号、景色、比喻、虚构细节、无关音乐元素和不必要的追问，
改成一个真实女高中生会在聊天框里发出的简短口语。
"""

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
        max_tokens=72,
    )

    stream = client.chat.completions.create(**request_options)
    logger.info(
        "[PERF] chat_stream_setup prompt=%.3fs connect=%.3fs total=%.3fs",
        prompt_ready_at - started_at,
        time.perf_counter() - prompt_ready_at,
        time.perf_counter() - started_at,
    )
    return stream


def chat_with_ai_stream(messages, context):
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
                    has_yielded_any = True
                    yield delta.content
        except Exception as e:
            last_error = e
            logger.warning("流式输出中途中断（第 %d 次尝试）：%s", attempt + 1, e)
            if has_yielded_any:
                # 已经说了一部分话，不重试（避免重复），自然收个尾
                yield "…呃，网络突然卡了一下，先这样吧。"
                return
            continue

        logger.info(
            "对话流完成：attempt=%d content=%s reasoning_chars=%d finish=%s",
            attempt + 1,
            has_yielded_any,
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
    persona = load_persona()

    client = create_ai_client(
        context["config"]["api_key"],
        context["config"].get("base_url"),
    )

    prompt = f"""
你是{persona['name']}。

性格：{persona['personality']}
说话方式：{persona['speaking_style']}

当前状态：

心情：{context['emotion']['mood']}
好感度：{context['relationship']['affection']}
精力：{context['emotion']['energy']}

用户资料：

名字：{context['profile']['name']}
昵称：{context['profile']['nickname']}
喜欢：{', '.join(context['profile']['likes'])}

请生成一句开场白。

要求：
- 不超过30字
- 像真实女高中生在聊天软件里和熟人打招呼
- 不要自我介绍
- 像熟人见面
- 每次尽量不同
- 不写括号动作、小说旁白或景色描写
- 不要虚构“刚练完新曲”“刚弹了贝斯”等开场事件
- 不要为了体现身份主动提贝斯、练习或轻音部
- 熟悉度不高时保持自然友好，不要表现得过分亲密
关系：
好感：{context['relationship']['affection']}
信任：{context['relationship']['trust']}
熟悉度：{context['relationship']['familiarity']}
"""
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
    复用 build_system_prompt（保证语气/长度/格式规则跟正常聊天一致），
    在后面追加一段"特殊场景"说明，告诉AI现在是主动找用户说话，以及原因。

    reason_hint: 一句描述触发原因的话（给AI看的内部提示，不会展示给用户），
                 比如"已经很久没聊天了，而且心情不太好，想找他说说话"。
    """
    import random

    system_prompt = build_system_prompt(context, query_text=reason_hint)
    user_display_name = get_user_display_name(context.get("profile"))

    special_instruction = f"""

# 【特殊场景：主动发起对话】
现在不是用户先说话，而是你自己想主动找{user_display_name}说一句话。
原因（仅供你参考，不要直接说出来，更不要提"触发""系统""检测"这类技术词汇）：
{reason_hint}

要求：
- 只说一句自然口语，最好在15~45个汉字内
- 不要解释自己为什么突然说话
- 不要说"我注意到""系统提示"等任何暴露后台机制的话
- 不写括号动作、小说旁白或景色描写
- 话题与音乐无关时，不提贝斯、琴弦、低音或练习
- 不要把关系说得过分亲密；熟悉度不高时避免直接说“想你了”
"""

    client = create_ai_client(
        context["config"]["api_key"],
        context["config"].get("base_url"),
    )

    try:
        response = client.chat.completions.create(**_daily_chat_request_options(
            context,
            model=context["config"]["model"],
            messages=[
                {"role": "system", "content": system_prompt + special_instruction}
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
