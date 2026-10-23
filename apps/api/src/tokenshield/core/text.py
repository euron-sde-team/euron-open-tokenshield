"""Small text helpers."""

from __future__ import annotations

import re

_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(value: str, max_len: int = 64) -> str:
    slug = _SLUG.sub("-", value.lower()).strip("-")
    return slug[:max_len] or "item"
