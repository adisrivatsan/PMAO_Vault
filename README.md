# pmao — Project Management Assistant Orchestrator

Ingest raw text → propose updates to tracked initiatives → confirm → view status.

## Quick Start

```bash
# 1. Create a vault
pmao init my-project

# 2. Ingest source material (transcript, email, notes)
pmao ingest my-project --source meeting-notes.md

# 3. View status dashboard
pmao status my-project

# Upgrading an old JSON vault
pmao migrate my-project
```

Three commands from zero to an updated dashboard.

## Commands

| Command | Description |
|---------|-------------|
| `pmao init <vault> [--roster FILE]` | Create vault; optionally seed projects from CSV |
| `pmao migrate <vault>` | Convert an old JSON vault (initiatives.json etc.) to the folder layout; safe to re-run |
| `pmao ingest <vault> --source FILE [--yes] [--backend claude\|codex]` | Extract updates from source; show diff; confirm; apply |
| `pmao status <vault> [--backend ...]` | LLM-rendered status dashboard |
| `pmao summarize <vault> [--backend ...]` | Executive summary |
| `pmao lint <vault> [--stale-days N]` | Health check |
| `pmao export <vault>` | Regenerate `workbook.xlsx` |
| `pmao config <vault>` | Print `project-config.yaml` |

## Vault Layout

One folder per type, one markdown file (YAML frontmatter + body) per item:

```
vault/
  SCHEMA.md             # vault conventions; the LLM reads it on ingest
  project-config.yaml   # project_name, owner, llm_backend, llm_timeout_seconds
  projects/             # one file per project (status, priority, owner, current state, next steps)
  tasks/                # action items
  people/               # one file per person (name, aliases, role)
  meetings/             # meetings to schedule
  decisions/            # recorded decisions
  notes/                # notes, hypotheses, facts
  docs/                 # source files (transcripts, decks)
  inbox/                # mentions ingest could not match to a project or person
  workbook.xlsx         # derived artifact (regenerate with `pmao export`)
```

The stored key linking an item to its project is `initiative_id`.

## People (Optional)

Add a file per person in `people/` to canonicalize owner names during ingest:

```markdown
---
type: person
name: Jane Smith
aliases: [Jane, JS]
role: PM
---
```

## Seeding Initiatives from CSV

```bash
pmao init my-project --roster initiatives.csv
```

CSV columns: `id` (optional), `name` (required), `owner` (optional), `priority` (optional).

## Initiative Status Values

`not_started` → `in_progress` → `ready` → `complete`

## Priority Values

`high`, `medium`, `low` (or omit for no priority)

## LLM Backend

Set `llm_backend` in `project-config.yaml` to `claude` or `codex`, or pass `--backend` at runtime. If unset, the CLI auto-detects from PATH.

## Installation

```bash
pip install pmao-cli
```
