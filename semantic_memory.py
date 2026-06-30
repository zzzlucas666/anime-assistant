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
from logger_utils import get_logger

logger = get_logger(__name__)

MODEL_NAME = "BAAI/bge-small-zh-v1.5"

_model = None  # 懒加载的单例，避免每次调用都重新加载模型（很慢）


def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("正在加载语义检索模型 %s（首次加载会慢一些）...", MODEL_NAME)
            _model = SentenceTransformer(MODEL_NAME)
            logger.info("语义检索模型加载完成。")
        except Exception as e:
            logger.error("加载语义检索模型失败：%s", e)
            _model = False  # 标记为"加载失败"，避免每次都重试加载浪费时间
    return _model if _model is not False else None


def embed_text(text):
    """
    把一段文本转成向量（list[float]）。
    模型加载失败或编码出错时返回 None，调用方需要妥善处理这个情况
    （语义检索不是关键路径，失败了就跳过，不能影响主流程）。
    """
    model = _get_model()
    if model is None:
        return None

    try:
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()
    except Exception as e:
        logger.warning("文本向量化失败：%s", e)
        return None


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
        return []

    scored = []
    for event in candidates:
        if not isinstance(event, dict):
            continue
        event_vector = event.get("embedding")
        if not event_vector:
            continue
        sim = cosine_similarity(query_vector, event_vector)
        if sim >= min_similarity:
            scored.append((sim, event))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [event for _, event in scored[:top_k]]