"""Text normalization and sentence segmentation for speech synthesis."""

import re


DEFAULT_MAX_CHARS = 56
_STAGE_DIRECTION_RE = re.compile(r"\([^()]{1,80}\)|（[^（）]{1,80}）")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。！？!?])")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")


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
    if not text:
        return []

    sentences = []
    for part in _SENTENCE_BOUNDARY_RE.split(text):
        part = part.strip()
        if not part:
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
    return sentences
