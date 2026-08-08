"""Shared markdown/frontmatter helpers used by connectors and people.py."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import frontmatter

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 40) -> str:
    """Lowercase, hyphenate, and truncate text for use in filenames."""
    slug = _SLUG_STRIP_RE.sub("-", text.lower()).strip("-")
    return slug[:max_len].strip("-") or "untitled"


def short_id(source_id: str, n: int = 8) -> str:
    """Stable short suffix for a source id, used to keep filenames unique and idempotent."""
    return hashlib.sha1(source_id.encode("utf-8")).hexdigest()[:n]


def render_note(frontmatter_fields: dict[str, Any], body: str) -> str:
    """Render frontmatter + body into a markdown string."""
    post = frontmatter.Post(body, **frontmatter_fields)
    return frontmatter.dumps(post)


def read_note(path: Path) -> frontmatter.Post:
    return frontmatter.load(path)


def write_note(path: Path, post: frontmatter.Post) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
