"""Shared connector pipeline: dedup -> write -> link people.

Fetching (calling the Gmail/Calendar MCP tools) happens at the agent level, not here —
a Python script can't call MCP tools itself. This module only knows how to turn
already-normalized items into vault writes and People updates. See docs/WORKFLOW.md for
the end-to-end loop until a formal agent skill wraps step 1-2 of it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from rhizo import markdown
from rhizo import people as people_mod
from rhizo.people import PersonRef

STATE_DIRNAME = ".rhizo-state"


@dataclass
class NormalizedItem:
    source: str  # "gmail" | "calendar"
    source_id: str  # dedup key: Gmail message id / Calendar event id
    kind: str  # "email" | "event"
    title: str
    timestamp: datetime
    people: list[PersonRef]
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)


class Fetcher(Protocol):
    """Not implemented in this pass. Documents the interface a future direct-API
    connector (no MCP access, e.g. Codex) would implement to plug into the same
    normalize/write pipeline used by the MCP-fed path today."""

    def fetch(self, since: datetime | None = None, **kwargs: Any) -> list[dict]: ...


class IngestState:
    """Backed by <vault>/.rhizo-state/<source>.json. Dedups by source_id so re-running
    ingest on the same raw data is a no-op."""

    def __init__(self, path: Path, data: dict | None = None) -> None:
        self._path = path
        self._data = data or {"seen_ids": {}, "last_ingest_at": None}

    @classmethod
    def load(cls, vault_root: Path, source: str) -> IngestState:
        path = vault_root / STATE_DIRNAME / f"{source}.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if not data or "seen_ids" not in data:
            data = {"seen_ids": {}, "last_ingest_at": None}
        return cls(path, data)

    def has_seen(self, source_id: str) -> bool:
        return source_id in self._data["seen_ids"]

    def mark_seen(self, source_id: str, vault_path: str) -> None:
        self._data["seen_ids"][source_id] = {
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "vault_path": vault_path,
        }

    def save(self) -> None:
        self._data["last_ingest_at"] = datetime.now(timezone.utc).isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2) + "\n", encoding="utf-8"
        )


@dataclass
class IngestReport:
    created: int = 0
    skipped: int = 0
    people_created: int = 0
    people_updated: int = 0
    created_paths: list[Path] = field(default_factory=list)


def write_item(item: NormalizedItem, vault_root: Path, target_path: Path) -> Path:
    frontmatter_fields = {
        "source": item.source,
        "source_id": item.source_id,
        "kind": item.kind,
        "title": item.title,
        "timestamp": item.timestamp.isoformat(),
        "tags": [item.kind],
        **item.metadata,
    }
    content = markdown.render_note(frontmatter_fields, item.body)
    path = vault_root / target_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def ingest(
    items: list[NormalizedItem],
    *,
    vault_root: Path,
    state: IngestState,
    people_index: people_mod.PeopleIndex,
    target_path_fn: Callable[[NormalizedItem], Path],
    owner_emails: set[str],
    dry_run: bool = False,
) -> IngestReport:
    """Shared driver used by every connector's `ingest <source>` CLI command: skip
    already-seen items, write markdown, link non-owner people (creating stub Person
    notes and logging an interaction), and persist state."""
    report = IngestReport()
    owner_emails_lower = {e.lower() for e in owner_emails}

    for item in items:
        if state.has_seen(item.source_id):
            report.skipped += 1
            continue

        target_path = target_path_fn(item)

        if dry_run:
            report.created += 1
            report.created_paths.append(target_path)
            continue

        written_path = write_item(item, vault_root, target_path)
        report.created += 1
        report.created_paths.append(written_path)

        rel_link = str(target_path)
        interaction_text = f'{item.kind.capitalize()}: "{item.title}"'
        for ref in item.people:
            if ref.email and ref.email.lower() in owner_emails_lower:
                continue
            existing = people_mod.find_person(vault_root, people_index, ref)
            person_path = people_mod.get_or_create_person(vault_root, people_index, ref)
            if existing is None:
                report.people_created += 1
            else:
                report.people_updated += 1
            people_mod.log_interaction(
                vault_root,
                person_path,
                item.timestamp.date(),
                interaction_text,
                link=rel_link,
                link_label=item.kind,
            )

        state.mark_seen(item.source_id, rel_link)

    if not dry_run:
        state.save()
        people_index.save()

    return report
