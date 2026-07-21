"""Text normalization and sentence segmentation for speech synthesis."""

import re


DEFAULT_MAX_CHARS = 56
_STAGE_DIRECTION_RE = re.compile(r"\([^()]{1,80}\)|（[^（）]{1,80}）")
# 只在一整组句末标点之后切分。旧写法会把“えっ？！”拆成
# “えっ？”和“！”，后者进入 GPT-SoVITS 后会被判定为无有效文本。
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。！？!?])(?=[^。！？!?])")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_SPEAKABLE_TEXT_RE = re.compile(r"[A-Za-z0-9\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def prepare_spoken_text(text):
    """Remove stage directions and whitespace that should not be spoken."""
    if not isinstance(text, str):
        return ""
    cleaned = _STAGE_DIRECTION_RE.sub("", text)
    return " ".join(cleaned.split()).strip()


def contains_japanese_kana(text):
    """Return whether the text already contains Japanese kana."""
    return bool(_KANA_RE.search(text or ""))


def split_sentences(text, maximum_chars=DEFAULT_MAX_CHARS):
    """Split Chinese/Japanese speech text while respecting a maximum length."""
    text = prepare_spoken_text(text)
    if not text or not _SPEAKABLE_TEXT_RE.search(text):
        return []

    sentences = []
    for part in _SENTENCE_BOUNDARY_RE.split(text):
        part = part.strip()
        if not part or not _SPEAKABLE_TEXT_RE.search(part):
            continue
        if len(part) <= maximum_chars:
            sentences.append(part)
            continue

        current = ""
        for piece in re.split(r"(?<=[、，,；;])", part):
            if current and len(current) + len(piece) > maximum_chars:
                sentences.append(current.strip())
                current = ""
            while len(piece) > maximum_chars:
                available = maximum_chars - len(current)
                current += piece[:available]
                piece = piece[available:]
                if current.strip():
                    sentences.append(current.strip())
                current = ""
            current += piece
        if current.strip():
            sentences.append(current.strip())
    # 长句二次切分也做最终防御，禁止把纯标点片段交给语音后端。
    return [sentence for sentence in sentences if _SPEAKABLE_TEXT_RE.search(sentence)]
