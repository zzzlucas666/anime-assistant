"""Shared text normalization helpers for provenance checks."""

import re


def normalize_grounding_text(value):
    """Normalize text before checking whether evidence occurs in user input."""
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(value or "").casefold())
