"""对话主回复失败时使用的短暂兜底话术。"""


FALLBACK_REPLIES = (
    "嗯…网络好像有点不稳定，刚才走神了，能再说一次吗？",
    "抱歉…刚刚好像没听清，可以再说一遍吗？",
    "嗯？信号好像有点问题…你刚才说什么？",
)


def is_transient_fallback(message):
    """判断内容是否为系统生成的短暂故障兜底，而非真实角色回复。"""
    return isinstance(message, str) and message.strip() in FALLBACK_REPLIES
