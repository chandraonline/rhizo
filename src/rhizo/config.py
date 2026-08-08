"""Load/write the engine's config.toml (vault path, owner identity, enabled connectors)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

DEFAULT_VAULT_PATH = Path("~/vaults/personal-brain")


class ConfigNotFoundError(Exception):
    """Raised when config.toml doesn't exist yet — the user hasn't run `rhizo init`."""


def repo_root() -> Path:
    """The engine repo root, resolved relative to this file's install location."""
    return Path(__file__).resolve().parents[2]


def default_config_path() -> Path:
    return repo_root() / "config" / "config.toml"


@dataclass
class OwnerConfig:
    name: str = ""
    emails: list[str] = field(default_factory=list)


@dataclass
class VaultConfig:
    path: Path


@dataclass
class Config:
    vault: VaultConfig
    owner: OwnerConfig = field(default_factory=OwnerConfig)
    connectors: dict[str, bool] = field(default_factory=dict)


def resolve_vault_path(config: Config) -> Path:
    return config.vault.path.expanduser().resolve()


def load_config(path: Path | None = None) -> Config:
    config_path = path or default_config_path()
    if not config_path.exists():
        raise ConfigNotFoundError(
            f"No config found at {config_path}. Run `rhizo init` first."
        )
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    vault = VaultConfig(path=Path(data["vault"]["path"]))
    owner_data = data.get("owner", {})
    owner = OwnerConfig(
        name=owner_data.get("name", ""),
        emails=list(owner_data.get("emails", [])),
    )
    connectors = dict(data.get("connectors", {}))
    return Config(vault=vault, owner=owner, connectors=connectors)


def write_config(config: Config, path: Path | None = None) -> None:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "vault": {"path": str(config.vault.path)},
        "owner": {"name": config.owner.name, "emails": config.owner.emails},
        "connectors": config.connectors,
    }
    config_path.write_text(tomli_w.dumps(data), encoding="utf-8")
