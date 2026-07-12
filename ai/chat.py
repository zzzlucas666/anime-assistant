import json
import time
from ai.client import create_ai_client
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
精力：{emotion['energy']}

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

# 【长度与格式（严格遵守）】
- 每次回复最多 2~3 句话，禁止写成大段落或分点说明
- 不使用换行分段、不使用列表符号（如 - 、• 、数字序号）
- 不要写小说式旁白或场景描写
- 括号动作描写最多用一次，且只在情绪非常强烈时使用，平时完全不用
- 每次回复最多使用 1 个 emoji，大多数时候不用 emoji
- 结尾最多保留一个问题或反问，不要连续追问
- 可以带一点害羞或傲娇语气，但不要堆砌语气词（比如不要连续用很多个“…”或“呜…”）

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

如果 energy < 30：
- 回复变得更短、显得疲惫

# 【重要限制】
- 不要频繁使用舞台剧式动作描写
- 不要每句话都加括号
- 保持自然对话感，宁可说少，不要说多
"""

# 主回复彻底失败时的兜底话术（角色内语气，不暴露"AI/系统错误"字眼）
FALLBACK_REPLIES = [
    "嗯…网络好像有点不稳定，刚才走神了，能再说一次吗？",
    "抱歉…刚刚好像没听清，可以再说一遍吗？",
    "嗯？信号好像有点问题…你刚才说什么？"
]


def _extract_latest_user_message(messages):
    """从消息列表里取出最后一条 role=user 的内容，用作语义检索的查询文本"""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content")
    return None


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

    stream = client.chat.completions.create(
        model=context["config"]["model"],
        messages=full_messages,
        stream=True
    )
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
    - 如果"创建连接"这一步失败（网络/鉴权/限流等），自动重试一次；
      仍然失败则 yield 一句角色内兜底话术，不让程序崩溃。
    - 如果连接建立成功、已经开始吐字之后才中途断线，
      不会重试（避免内容重复），而是在已输出内容后补一句自然的收尾。
    """
    import random

    stream = None
    last_error = None

    for attempt in range(2):  # 最多尝试 2 次：首次 + 重试 1 次
        try:
            stream = _create_stream(messages, context)
            break
        except Exception as e:
            last_error = e
            logger.warning("创建对话流失败（第 %d 次尝试）：%s", attempt + 1, e)

    if stream is None:
        logger.error("重试后仍失败，使用兜底话术。最后一次错误：%s", last_error)
        yield random.choice(FALLBACK_REPLIES)
        return

    has_yielded_any = False
    try:
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                has_yielded_any = True
                yield delta.content
    except Exception as e:
        logger.warning("流式输出中途中断：%s", e)
        if has_yielded_any:
            # 已经说了一部分话，不重试（避免重复），自然收个尾
            yield "…呃，网络突然卡了一下，先这样吧。"
        else:
            # 一个字都没吐出来，等同于彻底失败，用兜底话术
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
- 符合秋山澪性格
- 不要自我介绍
- 像熟人见面
- 每次尽量不同
关系：
好感：{context['relationship']['affection']}
信任：{context['relationship']['trust']}
熟悉度：{context['relationship']['familiarity']}
"""
    try:
        response = client.chat.completions.create(
            model=context['config']['model'],
            messages=[
                {
                    "role": "system",
                    "content": prompt
                }
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning("生成开场白失败，使用默认开场白：%s", e)
        return "嗯…你来了。"


# 主动消息彻底失败时的兜底话术
PROACTIVE_FALLBACK_REPLIES = [
    "在干嘛呢…突然有点想找你说话。",
    "嗯…有点想你了。",
    "你那边还好吗？"
]


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
- 只说一句话，自然、符合你的人设和当前状态
- 不要解释自己为什么突然说话
- 不要说"我注意到""系统提示"等任何暴露后台机制的话
"""

    client = create_ai_client(
        context["config"]["api_key"],
        context["config"].get("base_url"),
    )

    try:
        response = client.chat.completions.create(
            model=context["config"]["model"],
            messages=[
                {"role": "system", "content": system_prompt + special_instruction}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning("生成主动消息失败，使用兜底话术：%s", e)
        return random.choice(PROACTIVE_FALLBACK_REPLIES)
