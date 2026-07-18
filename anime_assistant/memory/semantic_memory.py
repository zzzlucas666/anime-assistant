"""
语义记忆检索 —— 用本地 embedding 模型给事件记忆生成向量，
检索时按"语义相关性"而不是单纯按时间找出相关的过往事件。

为什么用本地模型而不是调 API：
- DeepSeek 目前没有公开的 embedding 接口
- 本地模型不产生额外的网络调用成本，离线也能跑
- 缺点是要多装一个比较重的依赖（sentence-transformers + torch），
  首次加载模型需要几秒钟，之后常驻内存复用

用的模型是 BAAI/bge-small-zh-v1.5——专门做中文语义优化的小模型，
比通用多语言模型更适合这个项目（对话内容基本都是中文）。

依赖：pip install sentence-transformers
"""

import math
import re
import threading
import time
from anime_assistant.infrastructure.logging import get_logger

logger = get_logger(__name__)

MODEL_NAME = "BAAI/bge-small-zh-v1.5"

_model = None
_model_state = "idle"  # idle / loading / ready / failed
_model_lock = threading.Lock()
_model_ready = threading.Event()
_warmup_thread = None


def _load_model_worker():
    global _model, _model_state
    started_at = time.perf_counter()
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("正在后台加载语义检索模型 %s...", MODEL_NAME)
        loaded_model = SentenceTransformer(MODEL_NAME)
    except Exception as e:
        with _model_lock:
            _model = None
            _model_state = "failed"
        logger.error("加载语义检索模型失败：%s", e)
    else:
        with _model_lock:
            _model = loaded_model
            _model_state = "ready"
        logger.info(
            "[PERF] 语义检索模型后台加载完成 duration=%.3fs",
            time.perf_counter() - started_at,
        )
    finally:
        _model_ready.set()


def warmup_model_async():
    """在 daemon 线程中预热语义模型，返回 True 表示本次启动了加载。"""
    global _model_state, _warmup_thread
    with _model_lock:
        if _model_state != "idle":
            return False
        _model_state = "loading"
        _model_ready.clear()
        _warmup_thread = threading.Thread(
            target=_load_model_worker,
            name="semantic-model-warmup",
            daemon=True,
        )
        _warmup_thread.start()
    return True


def _get_model(wait=False):
    with _model_lock:
        state = _model_state
        model = _model

    if state == "ready":
        return model
    if state == "failed":
        return None
    if state == "idle":
        warmup_model_async()

    if wait:
        _model_ready.wait()
        with _model_lock:
            return _model if _model_state == "ready" else None
    return None


def is_model_ready():
    with _model_lock:
        return _model_state == "ready"


def embed_text(text, wait_for_model=False):
    """
    把一段文本转成向量（list[float]）。
    模型加载失败或编码出错时返回 None，调用方需要妥善处理这个情况
    （语义检索不是关键路径，失败了就跳过，不能影响主流程）。
    """
    model = _get_model(wait=wait_for_model)
    if model is None:
        return None

    try:
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()
    except Exception as e:
        logger.warning("文本向量化失败：%s", e)
        return None


def _lexical_similarity(text_a, text_b):
    """语义模型未就绪时的轻量中文字符 + bigram Jaccard 相似度。"""
    def normalize(text):
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(text or "").lower())

    a = normalize(text_a)
    b = normalize(text_b)
    if not a or not b:
        return 0.0
    chars_a, chars_b = set(a), set(b)
    char_union = chars_a | chars_b
    char_score = len(chars_a & chars_b) / len(char_union) if char_union else 0.0
    bigrams_a = {a[i:i + 2] for i in range(max(0, len(a) - 1))}
    bigrams_b = {b[i:i + 2] for i in range(max(0, len(b) - 1))}
    bigram_union = bigrams_a | bigrams_b
    bigram_score = len(bigrams_a & bigrams_b) / len(bigram_union) if bigram_union else 0.0
    return 0.35 * char_score + 0.65 * bigram_score


def _lexical_scores(query_text, candidates):
    return {
        event.get("id"): _lexical_similarity(query_text, event.get("event", ""))
        for event in candidates
        if isinstance(event, dict) and event.get("id")
    }


def cosine_similarity(vec_a, vec_b):
    """计算两个向量的余弦相似度。已经做过 normalize 的向量其实就是点积。"""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    # 已经 normalize 过的话 dot 本身就是 cosine similarity，
    # 这里还是稳妥地除一下范数，防止哪天换了没 normalize 的模型
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def find_semantically_relevant(query_text, candidates, top_k=3, min_similarity=0.35):
    """
    在候选事件列表里，找出跟 query_text 语义最相关的几条。

    candidates: event_manager 里的事件字典列表，每条要带 "embedding" 字段
                （没有 embedding 字段的旧数据会被自动跳过，不会报错）
    返回：按相似度从高到低排序的事件列表（不超过 top_k 条，且相似度要 >= min_similarity）
    """
    query_vector = embed_text(query_text)
    if query_vector is None:
        scores = _lexical_scores(query_text, candidates)
        scored = [
            (scores.get(event.get("id"), 0.0), event)
            for event in candidates
            if isinstance(event, dict) and scores.get(event.get("id"), 0.0) >= min_similarity
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [event for _, event in scored[:top_k]]

    scored = []
    for event in candidates:
        if not isinstance(event, dict):
            continue
        event_vector = event.get("embedding")
        if not event_vector:
            sim = _lexical_similarity(query_text, event.get("event", ""))
        else:
            sim = cosine_similarity(query_vector, event_vector)
        if sim >= min_similarity:
            scored.append((sim, event))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [event for _, event in scored[:top_k]]


def compute_similarity_scores(query_text, candidates):
    """
    计算 query_text 跟每条候选事件的语义相似度，返回 {event_id: similarity} 字典。

    跟 find_semantically_relevant 的区别：这个函数不做 top_k 截断、不做阈值过滤，
    单纯把"每条事件的语义相似度"算出来，交给调用方（比如 context_builder 的
    Hybrid Retrieval）跟其他维度（重要度、时间衰减）一起加权综合排序。

    query_text 为空或模型加载失败时返回空字典，调用方应当将其视为
    "所有事件的语义分数都是0"，不影响其他维度照常工作。
    """
    if not query_text:
        return {}

    started_at = time.perf_counter()
    query_vector = embed_text(query_text)
    if query_vector is None:
        scores = _lexical_scores(query_text, candidates)
        logger.info(
            "[PERF] 记忆检索 mode=lexical candidates=%d duration=%.4fs",
            len(candidates),
            time.perf_counter() - started_at,
        )
        return scores

    scores = {}
    used_lexical_fallback = False
    for event in candidates:
        if not isinstance(event, dict):
            continue
        event_id = event.get("id")
        event_vector = event.get("embedding")
        if not event_id:
            continue
        if event_vector:
            scores[event_id] = cosine_similarity(query_vector, event_vector)
        else:
            scores[event_id] = _lexical_similarity(query_text, event.get("event", ""))
            used_lexical_fallback = True

    logger.info(
        "[PERF] 记忆检索 mode=%s candidates=%d duration=%.4fs",
        "hybrid" if used_lexical_fallback else "embedding",
        len(candidates),
        time.perf_counter() - started_at,
    )
    return scores
