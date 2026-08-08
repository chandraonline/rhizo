"""Vault bootstrap: folder structure from the template, the `brain` symlink, and the
engine repo's .gitignore management. Never overwrites existing vault files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from rhizo import migrations
from rhizo.config import repo_root

VAULT_FOLDERS = [
    "00-Inbox",
    "01-Projects",
    "02-Areas",
    "03-Resources",
    "04-Archive",
    "People",
    "Journal",
]

STATE_FILES = ("gmail.json", "calendar.json", "people-index.json")


class VaultAlreadyExistsError(Exception):
    pass


def template_dir() -> Path:
    return repo_root() / "templates" / "vault"


def symlink_path() -> Path:
    return repo_root() / "brain"


def bootstrap_vault(vault_path: Path, *, force: bool = False) -> Path:
    """Create the vault at vault_path from the template, seed state, and link it in as
    ./brain. Idempotent: existing vault files are never overwritten. Raises
    VaultAlreadyExistsError if `brain` is already linked and force=False."""
    vault_path = vault_path.expanduser().resolve()
    link = symlink_path()

    if link.exists() and not force:
        raise VaultAlreadyExistsError(
            f"{link} already points at a vault ({link.resolve()}). "
            "Use --force to re-run setup (existing vault files are never overwritten)."
        )

    vault_path.mkdir(parents=True, exist_ok=True)
    _copy_template(template_dir(), vault_path)
    _seed_state(vault_path)
    _ensure_symlink(link, vault_path)
    ensure_gitignore_entries(repo_root(), ["/brain", "/config/config.toml"])
    return vault_path


def _copy_template(src: Path, dst: Path) -> None:
    for item in src.rglob("*"):
        if item.name == ".gitkeep":
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())


def _seed_state(vault_path: Path) -> None:
    state_dir = vault_path / migrations.STATE_DIRNAME
    state_dir.mkdir(parents=True, exist_ok=True)
    for fname in STATE_FILES:
        fpath = state_dir / fname
        if not fpath.exists():
            fpath.write_text("{}\n", encoding="utf-8")
    if not migrations.meta_path(vault_path).exists():
        migrations.init_meta(vault_path)


def _ensure_symlink(link: Path, target: Path) -> None:
    if link.is_symlink() or link.exists():
        if link.is_symlink() and link.resolve() == target.resolve():
            return
        link.unlink()
    link.symlink_to(target, target_is_directory=True)


def ensure_gitignore_entries(repo_root_path: Path, entries: list[str]) -> None:
    gitignore = repo_root_path / ".gitignore"
    existing = (
        gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    )
    changed = False
    for entry in entries:
        if entry not in existing:
            existing.append(entry)
            changed = True
    if changed:
        gitignore.write_text("\n".join(existing) + "\n", encoding="utf-8")


def get_or_create_daily_note(vault_root: Path, day: date) -> Path:
    path = vault_root / "Journal" / str(day.year) / f"{day.isoformat()}.md"
    if not path.exists():
        template = (template_dir() / "_templates" / "daily.md").read_text(
            encoding="utf-8"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(template.replace("{{date}}", day.isoformat()), encoding="utf-8")
    return path
