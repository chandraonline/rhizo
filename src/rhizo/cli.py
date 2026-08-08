"""Rhizo CLI entry point."""

from __future__ import annotations

from pathlib import Path

import typer

from datetime import date

from rhizo import __version__ as RHIZO_VERSION
from rhizo import config as config_mod
from rhizo import migrations as migrations_mod
from rhizo import people as people_mod
from rhizo import vault as vault_mod

app = typer.Typer(help="Rhizo — personal 2nd brain engine", no_args_is_help=True)
person_app = typer.Typer(help="Look up and log interactions with People notes.")
app.add_typer(person_app, name="person")


@app.command()
def init(
    vault_path: Path = typer.Option(
        None, "--vault-path", help="Where to create the vault (prompted if omitted)"
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-run setup even if a vault is already linked"
    ),
) -> None:
    """Interactively bootstrap a new vault and configure connectors."""
    if vault_path is None:
        raw = typer.prompt(
            "Vault path", default=str(config_mod.DEFAULT_VAULT_PATH)
        )
        vault_path = Path(raw)

    try:
        resolved = vault_mod.bootstrap_vault(vault_path, force=force)
    except vault_mod.VaultAlreadyExistsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    typer.secho(f"Vault created at {resolved}", fg=typer.colors.GREEN)
    typer.echo(f"Linked as {vault_mod.symlink_path()}")

    typer.echo()
    typer.echo("Which connectors do you want to enable?")
    connectors = {
        name: typer.confirm(f"  Enable {name}?", default=True)
        for name in ("gmail", "calendar")
    }

    typer.echo()
    typer.echo(
        "So connectors can tell you apart from the people you interact with, "
        "tell us who you are:"
    )
    owner_name = typer.prompt("  Your name")
    emails_raw = typer.prompt("  Your email address(es), comma-separated")
    owner_emails = [e.strip() for e in emails_raw.split(",") if e.strip()]

    cfg = config_mod.Config(
        vault=config_mod.VaultConfig(path=resolved),
        owner=config_mod.OwnerConfig(name=owner_name, emails=owner_emails),
        connectors=connectors,
    )
    config_mod.write_config(cfg)

    typer.echo()
    typer.secho("Setup complete.", fg=typer.colors.GREEN)
    typer.echo("Next: see docs/WORKFLOW.md to pull in data via the enabled connectors.")


def _load_config_or_exit() -> config_mod.Config:
    try:
        return config_mod.load_config()
    except config_mod.ConfigNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc


def _require_up_to_date_vault() -> tuple[config_mod.Config, Path]:
    """Shared setup for commands that operate on the vault (ingest, person): load
    config, resolve the vault path, and refuse to proceed if the vault's schema is
    behind what this engine build understands."""
    cfg = _load_config_or_exit()
    vault_root = config_mod.resolve_vault_path(cfg)
    if not migrations_mod.is_up_to_date(vault_root):
        typer.secho(
            "Vault schema is out of date. Run `rhizo upgrade` first.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    return cfg, vault_root


@app.command()
def status() -> None:
    """Show vault path, schema version, connectors, and basic stats."""
    cfg = _load_config_or_exit()
    vault_root = config_mod.resolve_vault_path(cfg)
    meta = migrations_mod.read_meta(vault_root)

    typer.echo(f"Vault: {vault_root}")
    version_line = (
        f"Schema version: {meta['schema_version']} "
        f"(engine supports up to {migrations_mod.CURRENT_SCHEMA_VERSION})"
    )
    if meta["schema_version"] < migrations_mod.CURRENT_SCHEMA_VERSION:
        typer.secho(version_line + " — run `rhizo upgrade`", fg=typer.colors.YELLOW)
    else:
        typer.echo(version_line)
    typer.echo(f"Rhizo package version: {RHIZO_VERSION}")
    typer.echo(f"Vault created with: {meta['created_with_rhizo_version']}")

    typer.echo()
    typer.echo("Connectors:")
    for name, enabled in cfg.connectors.items():
        typer.echo(f"  {name}: {'enabled' if enabled else 'disabled'}")

    typer.echo()
    typer.echo("Notes per folder:")
    for folder in vault_mod.VAULT_FOLDERS:
        folder_path = vault_root / folder
        count = len(list(folder_path.rglob("*.md"))) if folder_path.exists() else 0
        typer.echo(f"  {folder}: {count}")


@app.command()
def upgrade(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show pending migrations without applying them"
    ),
) -> None:
    """Apply any pending vault schema migrations."""
    cfg = _load_config_or_exit()
    vault_root = config_mod.resolve_vault_path(cfg)
    applied = migrations_mod.run_migrations(vault_root, cfg, dry_run=dry_run)

    if not applied:
        typer.secho("Already at latest version, nothing to do.", fg=typer.colors.GREEN)
        return

    verb = "Would apply" if dry_run else "Applied"
    for migration in applied:
        typer.echo(f"{verb} migration {migration.version}: {migration.description}")
    if not dry_run:
        typer.secho(
            f"Vault upgraded to schema version {applied[-1].version}.",
            fg=typer.colors.GREEN,
        )


@person_app.command("show")
def person_show(query: str = typer.Argument(..., help="Name, email, or phone")) -> None:
    """Show a person's note."""
    _, vault_root = _require_up_to_date_vault()
    index = people_mod.PeopleIndex.load(vault_root)
    path = people_mod.resolve_person(vault_root, index, query)
    if path is None:
        typer.secho(f'No person found matching "{query}".', fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.echo(f"# {path.relative_to(vault_root)}\n")
    typer.echo(path.read_text(encoding="utf-8"))


@person_app.command("log")
def person_log(
    query: str = typer.Argument(..., help="Name, email, or phone"),
    text: str = typer.Argument(..., help="Interaction note text"),
) -> None:
    """Log a manual interaction with an existing person. Does not create new people —
    only connector ingestion auto-creates stubs; use `rhizo person show` to check
    whether someone already has a note first."""
    _, vault_root = _require_up_to_date_vault()
    index = people_mod.PeopleIndex.load(vault_root)
    path = people_mod.resolve_person(vault_root, index, query)
    if path is None:
        typer.secho(
            f'No person found matching "{query}". '
            "person log only updates existing people.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    people_mod.log_interaction(vault_root, path, date.today(), text)
    typer.secho(f"Logged interaction with {path.stem}.", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
