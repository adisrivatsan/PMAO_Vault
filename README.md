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
```

That's it. Three commands from zero to an updated dashboard.

## Commands

| Command | Description |
|---------|-------------|
| `pmao init <vault> [--roster FILE]` | Create vault; optionally seed initiatives from CSV |
| `pmao ingest <vault> --source FILE [--yes] [--backend claude\|codex]` | Extract updates from source; show diff; confirm; apply |
| `pmao status <vault> [--backend ...]` | LLM-rendered status dashboard |
| `pmao summarize <vault> [--backend ...]` | Executive summary |
| `pmao export <vault>` | Regenerate `workbook.xlsx` |
| `pmao config <vault>` | Print `project-config.yaml` |

## Vault Layout

```
vault/
  project-config.yaml   # project_name, owner, llm_backend, llm_timeout_seconds
  initiatives.json      # source of truth (10 fields: id, name, status, priority,
                        #   owner, current_state, next_steps, last_touched,
                        #   last_touch_comment, notes)
  actions.json          # open action items
  meetings.json         # meetings to schedule
  decisions.json        # recorded decisions
  hypotheses.json       # tracked hypotheses
  facts.json            # extracted facts
  workbook.xlsx         # derived artifact (regenerate with `pmao export`)
  transcripts/          # drop source files here
  roster.yaml           # OPTIONAL: name + aliases for owner canonicalization
```

## Roster (Optional)

Create `roster.yaml` in your vault to canonicalize owner names during ingest:

```yaml
people:
  - name: Jane Smith
    aliases: [Jane, JS]
  - name: Alex Jordan
    aliases: [Alex]
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
