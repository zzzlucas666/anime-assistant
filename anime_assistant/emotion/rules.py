"""Local lexical rules shared by emotion candidate scoring and turn planning."""

import re


POSITIVE_MOODS = {"happy", "shy"}
DISTRESS_USER_MOODS = {
    "sad", "anxious", "angry", "lonely", "stressed", "tired", "disappointed",
}
SUPPORT_VOICE_STYLES = {"concerned", "reassuring", "serious", "thoughtful"}

PERSONAL_COMPLIMENT_MARKERS = (
    "你好可爱", "你很可爱", "真可爱", "太可爱", "觉得你可爱",
    "你好漂亮", "你很漂亮", "真漂亮", "太漂亮", "觉得你漂亮",
    "你好看", "你很美", "很有魅力", "声音好听", "声音真好听",
    "我喜欢你", "最喜欢你", "我爱你", "对你心动",
)
ABILITY_COMPLIMENT_MARKERS = (
    "弹得真好", "弹得很好", "弹得好", "唱得真好", "唱得很好", "唱得好",
    "演奏得真好", "演奏得很好", "贝斯很棒", "贝斯真棒",
    "做得真好", "做得很好", "做得不错", "进步很大", "进步好多",
    "很厉害", "真厉害", "太厉害", "很优秀", "真优秀", "了不起",
)
GENERAL_PRAISE_MARKERS = (
    "真棒", "太棒", "很棒", "干得好", "表现很好", "表现不错", "值得夸",
)
DIRECT_AFFECTION_MARKERS = ("我喜欢你", "最喜欢你", "我爱你", "对你心动")
DIRECT_AFFECTION_PATTERN = re.compile(
    r"我(?:真的|真|一直|还是|越来越)?(?:很|非常|特别|最)?喜欢你"
)
CARE_MARKERS = ("辛苦了", "谢谢你陪", "谢谢你一直", "有你真好", "我会陪你", "别勉强自己")
USER_SAD_MARKERS = (
    "我好难过", "我很难过", "我不开心", "我很伤心", "我想哭",
    "我难受", "我好难受", "我很难受", "感觉很难受", "今天很难受",
    "我好失落", "我很失落", "我心情不好", "今天很糟糕",
)
USER_LONELY_MARKERS = (
    "孤单", "孤独", "寂寞", "空落落", "没人陪", "没人找我",
    "没人和我聊天", "没人跟我聊天", "一个人好难受", "感觉很冷清",
)
USER_BORED_MARKERS = (
    "好无聊", "很无聊", "挺无聊", "感到无聊", "觉得无聊",
    "没意思", "没什么事做", "不知道做什么", "提不起兴趣",
)
USER_ANXIOUS_MARKERS = (
    "我好紧张", "我很紧张", "我好担心", "我很担心", "我害怕",
    "我好焦虑", "我很焦虑", "我不安", "我慌了",
)
USER_STRESSED_MARKERS = (
    "压力很大", "压力好大", "压力太大", "忙不过来", "忙得喘不过气",
    "最近很忙", "最近挺忙", "挺忙的", "太忙了", "事情好多",
    "工作压得", "实习很累", "实习挺忙", "快撑不住",
)
USER_TIRED_MARKERS = (
    "我好累", "我很累", "累死了", "累坏了", "身心疲惫",
    "没睡好", "睡不够", "困死了", "精疲力尽",
)
USER_DISAPPOINTED_MARKERS = (
    "我很失望", "我好失望", "太失望了", "失败了", "搞砸了",
    "没考好", "不顺利", "被拒绝了", "白努力了",
)
USER_ANGRY_MARKERS = ("我生气", "我很生气", "气死我", "我好火大", "烦死了")
USER_HAPPY_MARKERS = (
    "我好开心", "我很开心", "太好了", "我成功了", "我通过了",
    "我做到了", "我考得很好", "今天很顺利",
)
DIRECTED_NEGATIVE_MARKERS = ("讨厌你", "你真烦", "不想理你", "你让我失望")
ANNOYED_MARKERS = ("你真笨", "笨蛋", "逗你的", "开玩笑的")
SURPRISE_MARKERS = ("没想到", "居然", "告诉你个秘密", "你猜怎么着", "我中奖了")
QUESTION_MARKERS = ("为什么", "怎么会", "你觉得", "你知道", "真的吗", "是不是")
ADVICE_MARKERS = (
    "怎么办", "有什么办法", "有什么好办法", "有什么建议", "该怎么做",
    "怎么调整", "要怎么改善", "能帮我想想", "要不要试试",
)
SHY_REPLY_MARKERS = (
    "害羞", "脸红", "红着脸", "移开视线", "低下头", "别这样说",
    "突然说什么", "让人不好意思", "不知道怎么办", "才不可爱", "哪有那么",
)
HAPPY_REPLY_MARKERS = (
    "好开心", "很开心", "太好了", "谢谢你夸", "谢谢你这么说", "我会继续努力",
)
STAMMER_PATTERN = re.compile(r"(?:^|[（(，,。！？!?、\s])[你我这那]\s*[、,，]")
USER_SAD_PATTERN = re.compile(
    r"我(?:(?!你).){0,10}(?:难受|难过|伤心|不开心|失落|想哭|心情不好)"
)
USER_ANXIOUS_PATTERN = re.compile(r"我(?:(?!你).){0,8}(?:紧张|担心|害怕|焦虑|不安|慌)")
USER_ANGRY_PATTERN = re.compile(r"我(?:(?!你).){0,8}(?:生气|火大|恼火)")
USER_HAPPY_PATTERN = re.compile(r"我(?:(?!你).){0,8}(?:开心|高兴|成功了|通过了|做到了)")
NEGATED_EMOTION_PATTERN = re.compile(
    r"(?:不|没|没有|并不|不再)(?:是|觉得|感到)?(?:很|太|怎么|那么|特别|非常|有点)?"
    r"(?:难受|难过|伤心|失落|孤单|孤独|寂寞|无聊|紧张|担心|害怕|焦虑|生气|失望|疲惫|累)"
)
PROACTIVE_CONCERN_MARKERS = (
    "还好吗", "没事吧", "怎么了", "担心你", "有点担心", "我很担心",
    "别太勉强", "不要勉强", "休息一下", "难过", "不开心", "孤单", "孤独",
)
PROACTIVE_WARM_MARKERS = (
    "想和你聊", "想找你说", "好久没聊", "陪我聊", "有空吗", "在忙吗",
    "突然想和你", "突然想找你",
)
PROACTIVE_HAPPY_MARKERS = (
    "好消息", "太好了", "真开心", "很开心", "想告诉你", "一起庆祝",
)
PROACTIVE_SURPRISE_MARKERS = ("吓了一跳", "没想到", "居然", "你猜怎么着")
GREETING_WARM_MARKERS = (
    "你来了", "你来啦", "来了啊", "欢迎回来", "回来啦", "好久不见",
    "早上好", "下午好", "晚上好", "见到你", "今天怎么样", "今天过得",
)
GREETING_HAPPY_MARKERS = (
    "太好了", "真开心", "很开心", "好高兴", "终于来了", "等你好久",
)
GREETING_TIRED_MARKERS = ("好困", "有点困", "没睡醒", "我好累", "我有点累")


def contains_any(text, markers):
    return any(marker in text for marker in markers)


def has_personal_compliment(text):
    return contains_any(text, PERSONAL_COMPLIMENT_MARKERS) or bool(
        DIRECT_AFFECTION_PATTERN.search(text)
    )


def has_direct_affection(text):
    return contains_any(text, DIRECT_AFFECTION_MARKERS) or bool(
        DIRECT_AFFECTION_PATTERN.search(text)
    )


def emotion_text(text):
    """移除“没那么孤单”等明确否定片段，减少简单关键词的反向误判。"""
    return NEGATED_EMOTION_PATTERN.sub("", text)
