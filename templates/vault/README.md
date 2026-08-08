# This vault

Organized as PARA plus a first-class People area:

- `00-Inbox/` — everything lands here first: quick captures, and everything connectors
  ingest (emails, calendar events). Triage into the right place below over time.
- `01-Projects/` — things with a goal and an end date.
- `02-Areas/` — ongoing responsibilities with no end date.
- `03-Resources/` — reference material, topics of interest.
- `04-Archive/` — inactive items from any of the above.
- `People/` — one note per person. Frontmatter tracks aliases (names/emails/phones used
  to recognize them), relationship, and interaction dates. Body has an `## Interactions`
  log that grows over time. This is deliberately top-level, not nested under Areas — it's
  a primary way this vault differs from stock PARA, since keeping track of who you know
  and how you relate to them is a first-class goal here.
- `Journal/YYYY/YYYY-MM-DD.md` — daily notes.

## Recommended Obsidian setup

This vault ships without a preconfigured `.obsidian/` folder — Obsidian will create its
own defaults on first open. Recommended manual setup:

- Core plugin **Daily notes**: point it at `Journal/YYYY/` using the `_templates/daily.md`
  template.
- Community plugin **Dataview**: for querying notes by frontmatter (e.g. listing people by
  `relationship` or recent `last_interaction`).
- Community plugin **Templater**: for the `_templates/` folder.
