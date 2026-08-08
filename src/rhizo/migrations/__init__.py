"""Vault schema versioning: meta.json handling + the migration registry/runner.

The vault's structural format (folders, frontmatter fields, state file shapes) is
versioned independently of the installed rhizo package version. Each migration module
registers a Migration for the schema version it upgrades *to*; `run_migrations` applies
any pending ones in order and persists progress after each one succeeds.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from rhizo import __version__ as RHIZO_VERSION
from rhizo.config import Config

STATE_DIRNAME = ".rhizo-state"
META_FILENAME = "meta.json"


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    upgrade: Callable[[Path, Config], None]


def _state_dir(vault_root: Path) -> Path:
    return vault_root / STATE_DIRNAME


def meta_path(vault_root: Path) -> Path:
    return _state_dir(vault_root) / META_FILENAME


def read_meta(vault_root: Path) -> dict:
    return json.loads(meta_path(vault_root).read_text(encoding="utf-8"))


def write_meta(vault_root: Path, meta: dict) -> None:
    path = meta_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def init_meta(vault_root: Path) -> dict:
    """Write the initial meta.json for a freshly bootstrapped vault, at the current
    schema version — new vaults never need to run migrations from scratch."""
    meta = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "vault_id": str(uuid.uuid4()),
        "created_with_rhizo_version": RHIZO_VERSION,
        "last_upgraded_at": None,
    }
    write_meta(vault_root, meta)
    return meta


def is_up_to_date(vault_root: Path) -> bool:
    return read_meta(vault_root)["schema_version"] == CURRENT_SCHEMA_VERSION


def pending_migrations(vault_root: Path) -> list[Migration]:
    current = read_meta(vault_root)["schema_version"]
    return sorted(
        (m for m in MIGRATIONS if m.version > current), key=lambda m: m.version
    )


def run_migrations(
    vault_root: Path, config: Config, *, dry_run: bool = False
) -> list[Migration]:
    """Apply pending migrations in order. Returns the list of migrations applied (or, if
    dry_run, that would be applied). Persists schema_version after each individual
    migration succeeds, so a failure partway through resumes from that point on retry."""
    to_apply = pending_migrations(vault_root)
    if dry_run:
        return to_apply

    for migration in to_apply:
        migration.upgrade(vault_root, config)
        meta = read_meta(vault_root)
        meta["schema_version"] = migration.version
        meta["last_upgraded_at"] = datetime.now(timezone.utc).isoformat()
        write_meta(vault_root, meta)
    return to_apply


from rhizo.migrations.m0001_initial import MIGRATION as _M0001  # noqa: E402

CURRENT_SCHEMA_VERSION = 1
MIGRATIONS: list[Migration] = [_M0001]
