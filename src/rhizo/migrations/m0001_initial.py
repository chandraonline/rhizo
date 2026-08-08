"""Baseline schema version. New vaults are bootstrapped directly at this version (see
migrations.init_meta), so this migration's upgrade() never actually runs in practice —
it exists to establish the pattern for the next real migration."""

from __future__ import annotations

from pathlib import Path

from rhizo.config import Config
from rhizo.migrations import Migration


def upgrade(vault_root: Path, config: Config) -> None:
    return None


MIGRATION = Migration(version=1, description="Initial baseline schema", upgrade=upgrade)
