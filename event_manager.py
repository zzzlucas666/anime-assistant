import uuid
import datetime
import os
import threading
import time
from ai.client import create_ai_client
from app_paths import DATA_DIR
from data_models import normalize_event_extraction, normalize_event_record, parse_json_object
from Storage_utils import safe_load_json, safe_save_json
from logger_utils import get_logger
from semantic_memory import embed_text, find_semantically_relevant

logger = get_logger(__name__)

EVENT_PATH = str(DATA_DIR / "event_memory.json")
_event_cache_lock = threading.RLock()
_event_cache_path = None
_event_cache_signature = None
_event_cache = None


def default_events():
    return []


def _normalize_event(event, seen_ids=None):
    """把旧版事件补齐为当前结构。

    旧数据没有可靠的发生时间时保留为 None，不用迁移时间伪装成
    刚发生的事件。embedding 也只补 None，避免一次数据迁移意外触发
    本地模型下载或大批量向量计算。

    返回 (normalized_event, changed)。非字典项返回 (None, True)。
    """
    if not isinstance(event, dict):
        return None, True

    normalized = normalize_event_record(event)
    if normalized is None:
        return None, True
    changed = normalized != event

    event_id = normalized.get("id")
    if not event_id or (seen_ids is not None and event_id in seen_ids):
        normalized["id"] = uuid.uuid4().hex
        changed = True

    if seen_ids is not None:
        seen_ids.add(normalized["id"])

    return normalized, changed


def _event_file_signature():
    try:
        stat = os.stat(EVENT_PATH)
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def _replace_event_cache(events):
    global _event_cache_path, _event_cache_signature, _event_cache
    _event_cache_path = EVENT_PATH
    _event_cache_signature = _event_file_signature()
    _event_cache = events


def clear_event_cache():
    """清空进程内事件缓存，主要供测试和显式重载使用。"""
    global _event_cache_path, _event_cache_signature, _event_cache
    with _event_cache_lock:
        _event_cache_path = None
        _event_cache_signature = None
        _event_cache = None


def _load_events():
    """统一读取事件。文件未变化时直接返回进程内缓存的浅拷贝。"""
    started_at = time.perf_counter()
    with _event_cache_lock:
        signature = _event_file_signature()
        if (
            _event_cache is not None
            and _event_cache_path == EVENT_PATH
            and _event_cache_signature == signature
        ):
            logger.info(
                "[PERF] 事件存储 cache=hit events=%d duration=%.4fs",
                len(_event_cache),
                time.perf_counter() - started_at,
            )
            return list(_event_cache)

        raw_events = safe_load_json(EVENT_PATH, default_events)
        if not isinstance(raw_events, list):
            raw_events = []
            changed = True
        else:
            changed = False

        events = []
        seen_ids = set()
        for event in raw_events:
            normalized, item_changed = _normalize_event(event, seen_ids=seen_ids)
            changed = changed or item_changed
            if normalized is not None:
                events.append(normalized)

        if changed:
            safe_save_json(EVENT_PATH, events)
            logger.info("已将旧版事件数据迁移到当前结构，共 %d 条。", len(events))

        _replace_event_cache(events)
        logger.info(
            "[PERF] 事件存储 cache=miss events=%d duration=%.4fs",
            len(events),
            time.perf_counter() - started_at,
        )
        return list(events)


def extract_event(api_key, model, user_message, ai_reply, base_url=None):
    """
    用 AI 判断这轮对话里是否发生了"值得记住的事件"，
    覆盖范围比之前的规则匹配（只认"喜欢"+"吗"）广得多，
    比如：用户提到的计划、烦恼、重要日子、对AI的评价、新信息等。

    事件记忆不是关键路径，任何失败都直接返回 None（不记录这次事件），
    不应该因为这里出错就影响主回复或让程序崩溃。
    """

    try:
        client = create_ai_client(api_key, base_url)

        prompt = f"""
你是一个事件记忆提取器，负责从一轮对话中判断是否发生了"值得长期记住的事件"。

值得记住的事件包括（但不限于）：
- 用户表达了喜欢/讨厌某件事物
- 用户分享了计划、烦恼、心事、重要的事情
- 用户提到了重要日期（生日、纪念日等）
- 用户对AI表达了关心、感谢、夸奖或不满
- 用户透露了新的个人信息或重要经历

不值得记住的事件：
- 单纯的寒暄、闲聊、无实质内容的对话

请分析下面这轮对话，返回严格的JSON格式：

{{
  "is_event": true 或 false,
  "event": "用1-2句话具体描述这件事（如果 is_event 为 false，留空字符串）",
  "user_emotion": "用户本人的情绪，只能是 happy / sad / anxious / angry / embarrassed / neutral",
  "emotion": "Mio 对这件事的情绪，只能是 happy / shy / curious / sad / touched / worried / neutral",
  "impact": "increase_bond 或 increase_affinity 或 none",
  "importance": 0.0到1.0之间的数字，表示这件事的重要程度
}}

关于 "event" 字段的写法要求（很重要，影响后续能否被正确检索到）：
- 不要用"用户提到/表达了xxx"这种空洞的固定句式，要把具体内容写清楚
- 包含具体的人、事、物、时间等细节，让这句话本身就能传达完整信息
- 反例（太空洞）："用户提到下周要考试"
- 正例（够具体）："对方说下周三有一场很重要的数学考试，感到有点紧张，希望考好"
- 反例（太空洞）："用户表达了对某事的喜好"
- 正例（够具体）："对方说他很喜欢摇滚乐，尤其喜欢一些节奏强烈的乐队"

判断标准：
- increase_bond：能显著增进感情的事件（用户表达关心、分享心事、确认情感等），importance 通常 >= 0.7
- increase_affinity：一般的好感类事件（提到喜好等），importance 通常在 0.4~0.7
- none：普通对话，importance 通常 < 0.4
- 用户夸 Mio 可爱、漂亮、声音好听或直接表达喜欢，而且 Mio 的回复明显不好意思、结巴或躲闪时，emotion 应为 shy
- 用户夸 Mio 的贝斯、努力、进步或成果，而且她自然地接受了夸奖时，emotion 应为 happy
- 用户本人难过或紧张时，把 user_emotion 标成 sad 或 anxious；Mio 的 emotion 通常应为 worried，而不是把用户的难过直接复制成 Mio 的 sad

用户说的话：
{user_message}

AI的回复：
{ai_reply}

只返回JSON，不要解释，不要markdown。
"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt}
            ],
            temperature=0
        )

        content = response.choices[0].message.content

    except Exception as e:
        logger.warning("事件提取调用失败（已跳过本轮事件记忆）：%s", e)
        return None

    try:
        result = normalize_event_extraction(parse_json_object(content))
    except Exception as e:
        logger.warning("事件提取结果校验失败（已跳过本轮事件记忆）：%s", e)
        return None

    if not result.get("is_event"):
        return None

    event_text = result["event"]

    return {
        "id": uuid.uuid4().hex,
        "event": event_text,
        "emotion": result["emotion"],
        "user_emotion": result["user_emotion"],
        "impact": result["impact"],
        "importance": result["importance"],
        "notified": False,
        # 创建时间，供 Hybrid Retrieval 计算"时间衰减"分数用
        "created_at": datetime.datetime.now().isoformat(),
        # 语义检索用的向量。embed_text 失败时返回 None，
        # find_semantically_relevant 会自动跳过没有向量的事件，不影响其他功能。
        "embedding": embed_text(event_text) if event_text else None
    }


def save_event(event):
    if not event:
        return

    with _event_cache_lock:
        data = _load_events()
        normalized, _ = _normalize_event(event, seen_ids={e["id"] for e in data})
        if normalized is None:
            return
        data.append(normalized)
        if safe_save_json(EVENT_PATH, data):
            _replace_event_cache(data)


def load_all_events():
    """
    读取全部事件（不做任何过滤），供 context_builder 的 Hybrid Retrieval
    自己综合语义/重要度/时间衰减打分排序。
    """
    return _load_events()


def load_recent_events(limit=5, min_importance=0.5):
    """
    读取近期 + 重要的事件，供 chat.py 拼进 system prompt，
    让 AI 能"记得"并主动提起之前发生过的事。

    - 只挑选 importance >= min_importance 的事件（过滤掉"普通对话"这类噪音）
    - 按时间顺序保留最近 limit 条（越新越靠后）
    """
    data = _load_events()

    important_events = [
        e for e in data
        if isinstance(e, dict) and e.get("importance", 0) >= min_importance
    ]

    return important_events[-limit:]


def get_unnotified_important_events(min_importance=0.7):
    """
    获取"重要且还没被主动提起过"的事件，供 Initiative Engine 判断是否要
    主动找用户聊起某件事。
    """
    data = _load_events()

    return [
        e for e in data
        if isinstance(e, dict)
        and e.get("importance", 0) >= min_importance
        and not e.get("notified", False)
    ]


def mark_event_notified(event_id):
    """把某条事件标记为"已经主动提起过"，避免下次又重复提起同一件事"""
    with _event_cache_lock:
        data = [event.copy() for event in _load_events()]

        changed = False
        for e in data:
            if isinstance(e, dict) and e.get("id") == event_id:
                e["notified"] = True
                changed = True

        if changed and safe_save_json(EVENT_PATH, data):
            _replace_event_cache(data)


def get_semantically_relevant_events(query_text, top_k=3, min_importance=0.0):
    """
    按语义相关性（而不是时间顺序）找出跟 query_text 最相关的过往事件。
    比如用户现在在聊"考试"，即使这是几天前提到的事，只要语义相关
    就能被检索到，而不需要它恰好出现在"最近几条"里。

    语义检索失败（模型没装好、向量缺失等）会安全地返回空列表，
    不影响调用方继续走"按时间"的兜底逻辑。
    """
    if not query_text:
        return []

    data = _load_events()
    candidates = [
        e for e in data
        if isinstance(e, dict) and e.get("importance", 0) >= min_importance
    ]

    return find_semantically_relevant(query_text, candidates, top_k=top_k)
