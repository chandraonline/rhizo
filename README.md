# Rhizo

A personal 2nd-brain engine: connectors and CLI tooling that feed an Obsidian vault.
This repo is the engine only — it never contains vault data. A vault is bootstrapped at
an external path and linked into the repo as a gitignored `brain` symlink.

## Quickstart

```sh
uv venv
uv pip install -e ".[dev]"
rhizo init
```

`rhizo init` walks you through creating a vault, choosing which connectors to enable, and
recording your identity so connectors can tell you apart from the people you interact
with.

See `docs/WORKFLOW.md` for how to pull data in from Gmail/Calendar today (before a formal
agent-skill wrapper exists), and `templates/vault/README.md` for the vault's own
organization scheme (PARA + a first-class People area) once you've bootstrapped one.

## Commands

```
rhizo init [--vault-path PATH]
rhizo status
rhizo upgrade [--dry-run]
rhizo ingest gmail --input PATH [--dry-run]
rhizo ingest calendar --input PATH [--dry-run]
rhizo person show <name-or-alias>
rhizo person log <name> <text>
```
