"""Person notes: create/find/update, alias indexing, and the interaction log.

PersonRef lives here (not in connectors/base.py) so connectors can depend on people.py
without creating a circular import, since people.py has no dependency on connectors.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from rhizo import markdown

STATE_DIRNAME = ".rhizo-state"
PEOPLE_INDEX_FILENAME = "people-index.json"

_NAME_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_name(name: str) -> str:
    return _NAME_NORMALIZE_RE.sub(" ", name.lower()).strip()


@dataclass
class PersonRef:
    name: str
    email: str | None = None
    phone: str | None = None
    role: str = "participant"  # organizer | attendee | sender | recipient | cc


class PeopleIndex:
    """Fast alias -> note-path lookup, backed by <vault>/.rhizo-state/people-index.json.
    Avoids rescanning People/ frontmatter on every ingest run."""

    def __init__(self, path: Path, data: dict | None = None) -> None:
        self._path = path
        self._data = data or {"by_email": {}, "by_phone": {}, "by_name": {}}

    @classmethod
    def load(cls, vault_root: Path) -> PeopleIndex:
        path = vault_root / STATE_DIRNAME / PEOPLE_INDEX_FILENAME
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        return cls(path, data)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2) + "\n", encoding="utf-8"
        )

    def lookup(
        self,
        *,
        email: str | None = None,
        phone: str | None = None,
        name: str | None = None,
    ) -> str | None:
        """Match by the strongest identifier available. Deliberately does NOT fall
        through to a name match when an email/phone was given but didn't match — two
        people can share a display name, and an unmatched email means this is either a
        new person or a name collision, not a name-based merge with someone else."""
        if email:
            return self._data["by_email"].get(email.lower())
        if phone:
            return self._data["by_phone"].get(phone)
        if name:
            return self._data["by_name"].get(_normalize_name(name))
        return None

    def register(
        self,
        rel_path: str,
        *,
        name: str,
        email: str | None = None,
        phone: str | None = None,
    ) -> None:
        self._data["by_name"][_normalize_name(name)] = rel_path
        if email:
            self._data["by_email"][email.lower()] = rel_path
        if phone:
            self._data["by_phone"][phone] = rel_path


def find_person(vault_root: Path, index: PeopleIndex, ref: PersonRef) -> Path | None:
    rel = index.lookup(email=ref.email, phone=ref.phone, name=ref.name)
    if rel is None:
        return None
    path = vault_root / rel
    return path if path.exists() else None


def resolve_person(vault_root: Path, index: PeopleIndex, query: str) -> Path | None:
    """User-facing lookup for `person show`/`person log`: tries an exact match against
    known emails/phones/names first, then falls back to a case-insensitive substring
    match across names. Unlike PeopleIndex.lookup (used during ingestion, where an
    unmatched email must not silently fall back to a name match to avoid merging
    distinct people), this tries every identifier kind since the caller is a human who
    doesn't know which kind of alias they're typing."""
    data = index._data
    rel = (
        data["by_email"].get(query.lower())
        or data["by_phone"].get(query)
        or data["by_name"].get(_normalize_name(query))
    )
    if rel:
        path = vault_root / rel
        if path.exists():
            return path

    query_norm = _normalize_name(query)
    if query_norm:
        for name_key, rel_path in data["by_name"].items():
            if query_norm in name_key:
                path = vault_root / rel_path
                if path.exists():
                    return path
    return None


def _person_filename(ref: PersonRef, vault_root: Path) -> str:
    """Disambiguate distinct people sharing a display name by appending the email
    domain, and fall back to a short id if that's still not unique."""
    people_dir = vault_root / "People"

    candidate = f"{ref.name}.md"
    if not (people_dir / candidate).exists():
        return candidate

    if ref.email and "@" in ref.email:
        domain = ref.email.split("@", 1)[1]
        candidate = f"{ref.name} ({domain}).md"
        if not (people_dir / candidate).exists():
            return candidate

    suffix = markdown.short_id(ref.email or ref.phone or ref.name, n=6)
    return f"{ref.name} ({suffix}).md"


def create_person_stub(vault_root: Path, index: PeopleIndex, ref: PersonRef) -> Path:
    filename = _person_filename(ref, vault_root)
    rel_path = f"People/{filename}"
    path = vault_root / rel_path

    aliases = [a for a in (ref.email, ref.phone) if a]
    frontmatter_fields = {
        "name": ref.name,
        "aliases": aliases,
        "tags": ["person"],
        "relationship": "",
        "first_met": "",
        "last_interaction": "",
    }
    body = f"# {ref.name}\n\n## Notes\n\n## Interactions\n"
    content = markdown.render_note(frontmatter_fields, body)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    index.register(rel_path, name=ref.name, email=ref.email, phone=ref.phone)
    return path


def _insert_sorted_bullet(lines: list[str], new_line: str, new_date: str) -> list[str]:
    """Insert new_line into a list of "- YYYY-MM-DD: ..." bullets kept in descending
    (newest-first) date order. New entries land after any existing same-date entries."""
    for i, line in enumerate(lines):
        existing_date = line[2:12]
        if existing_date < new_date:
            lines.insert(i, new_line)
            return lines
    lines.append(new_line)
    return lines


def get_or_create_person(vault_root: Path, index: PeopleIndex, ref: PersonRef) -> Path:
    existing = find_person(vault_root, index, ref)
    if existing is not None:
        return existing
    return create_person_stub(vault_root, index, ref)


def log_interaction(
    vault_root: Path,
    person_path: Path,
    day: date,
    text: str,
    link: str | None = None,
    link_label: str | None = None,
) -> None:
    """Insert a dated bullet into '## Interactions', keeping the list sorted
    newest-first by date (not by call/processing order — a single ingest batch or a
    later backfill of older data can process an earlier-dated item after a later one).
    Assumes '## Interactions' is the note's final section, per the person template.
    Updates last_interaction (and first_met, if unset) in frontmatter. `link` is a
    vault-relative path (with or without a .md suffix); the suffix is stripped for the
    wikilink since Obsidian resolves links by note name, not filename."""
    post = markdown.read_note(person_path)

    day_str = day.isoformat()
    entry = f"- {day_str}: {text}"
    if link:
        target = link[:-3] if link.endswith(".md") else link
        entry += f" [[{target}|{link_label}]]" if link_label else f" [[{target}]]"

    marker = "## Interactions"
    body = post.content
    idx = body.find(marker)
    if idx == -1:
        header = body.rstrip() + f"\n\n{marker}"
        existing_lines: list[str] = []
    else:
        header = body[: idx + len(marker)]
        remainder = body[idx + len(marker) :].strip("\n")
        existing_lines = [line for line in remainder.split("\n") if line.strip()]

    existing_lines = _insert_sorted_bullet(existing_lines, entry, day_str)
    post.content = header + "\n" + "\n".join(existing_lines) + "\n"

    # Compare rather than overwrite: items aren't guaranteed to arrive in chronological
    # order (a single ingest batch, or a later backfill of older data, can process an
    # earlier-dated item after a later one), so first_met/last_interaction must track the
    # min/max date seen, not just the most recently processed one. ISO date strings
    # compare correctly lexicographically.
    day_str = day.isoformat()
    first_met = post.get("first_met")
    if not first_met or day_str < first_met:
        post["first_met"] = day_str
    last_interaction = post.get("last_interaction")
    if not last_interaction or day_str > last_interaction:
        post["last_interaction"] = day_str

    markdown.write_note(person_path, post)
