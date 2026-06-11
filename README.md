# pmao-cli

**Project Management Assistant Orchestrator** — a CLI-first, LLM-powered initiative tracker.

pmao maintains a local "vault" of JSON files as source of truth and uses an LLM (Claude Code or OpenAI Codex CLI) to extract updates from meeting notes, generate status dashboards, and produce executive summaries. All reasoning lives in plain-text skill files you can read and edit.

## Requirements

- Python 3.9+
- [Claude Code CLI](https://github.com/anthropics/claude-code) (`claude`) **or** [OpenAI Codex CLI](https://github.com/openai/codex) (`codex`) on your PATH
- `pip install pmao-cli`

## Quick start

```bash
# 1. Create a vault
pmao init my-project/

# 2. Seed initiatives from a CSV (optional)
pmao init my-project/ --roster pmao/templates/initiative-template.csv

# 3. Ingest meeting notes or a transcript
pmao ingest my-project/ --source meeting-notes.md

# 4. View a status dashboard
pmao status my-project/

# 5. Produce an executive summary
pmao summarize my-project/

# 6. Regenerate the Excel workbook
pmao export my-project/
```

## Commands

| Command | Description |
|---------|-------------|
| `pmao init <vault> [--roster FILE]` | Initialize a new vault; optionally seed from CSV |
| `pmao ingest <vault> --source FILE [--yes]` | Quick extract: updates applied directly after confirmation |
| `pmao ingest <vault> --source FILE --deep` | Deep extract: facts, signals, meetings, typed actions — staged to `staging/` for review (never applies directly) |
| `pmao update <vault>` | Interactively update an initiative field via LLM |
| `pmao status <vault>` | Print a sorted status dashboard |
| `pmao summarize <vault>` | Produce an executive summary |
| `pmao export <vault>` | Regenerate workbook.xlsx from current state |
| `pmao config <vault>` | View project configuration |
| `pmao review <vault>` | Walk staged extractions: approve/edit/reject, promote to canonical files, learn from verdicts |
| `pmao syndicate <vault> --initiative ID` | Recommend stakeholder pathway + meeting cadence; proposals staged for review |

All LLM commands accept `--backend claude` or `--backend codex` to override auto-detection.

## Vault structure

```
my-project/
  project-config.yaml   # project name, owner, LLM settings
  initiatives.json      # source of truth — all initiative state
  actions.json          # open action items
  questions.json        # open questions
  decisions.json        # recorded decisions
  hypotheses.json       # open hypotheses
  facts.json            # promoted facts (deep ingest + review gate)
  signals.json          # promoted principal signals
  meetings.json         # promoted meetings to schedule
  roster.yaml           # optional people roster (owners, aliases, decision-makers)
  staging/              # deep-ingest extractions awaiting review
  learning/             # calibration lessons fed back into deep ingest (written by review gate)
  workbook.xlsx         # derived Excel artifact (10 tabs)
  transcripts/          # drop .vtt or .txt files here
```

## Initiative fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Unique identifier (e.g., `init-001`) |
| `name` | yes | Initiative name |
| `status` | yes | `not_started` / `in_progress` / `ready` / `complete` |
| `created` | yes | ISO date |
| `last_touched` | yes | ISO date (auto-updated on ingest) |
| `coordination_owner` | no | Person driving coordination |
| `responsible_owner` | no | Person accountable for delivery |
| `priority` | no | `high` / `medium` / `low` |
| `current_state` | no | Free-text state summary |
| `coordination_next_steps` | no | Newline-delimited next steps |
| `outstanding_questions` | no | Unresolved questions |
| `outstanding_meetings` | no | Meetings to schedule |
| `last_touch_comment` | no | Source of last update |
| `last_touch_timestamp` | no | ISO date of last update |
| `syndication_notes` | no | Notes on external communication |
| `materials_link` | no | URL to supporting materials |
| `notes` | no | Freeform notes |

## Skill files

All LLM reasoning is in `pmao/skills/` (shipped inside the installed package). Edit these to change how the LLM interprets your transcripts or formats its output — no Python changes required.

| File | Used by |
|------|---------|
| `pmao/skills/ingest.md` | `pmao ingest` — structured extraction from source material |
| `pmao/skills/ingest-deep.md` | `pmao ingest --deep` — staged rich extraction |
| `pmao/skills/update.md` | `pmao update` — interactive field update flow |
| `pmao/skills/status.md` | `pmao status` — status dashboard rendering |
| `pmao/skills/summarize.md` | `pmao summarize` — executive summary generation |
| `pmao/skills/syndicate.md` | `pmao syndicate` — pathway + cadence recommendation |

## Seeding initiatives from CSV

Use `--roster` with `pmao init`, or provide a CSV with headers:

```
id,name,coordination_owner,responsible_owner,priority
init-001,Customer Data Platform,Jane Smith,John Doe,high
init-002,Market Expansion,,,medium
```

See `pmao/templates/initiative-template.csv` for the full template.

## Deep ingest and the roster

`pmao ingest --deep` runs a richer extraction (facts, hypotheses, decisions, open questions, principal signals, meetings to schedule, typed action items, alias/review flags) and writes the result to `staging/` — canonical files are only changed when a human promotes items via the review gate (`pmao review`).

Add an optional `roster.yaml` to the vault to enable owner/alias resolution and authority calls:

```yaml
people:
  - name: Sarah Klein
    aliases: [Sarah, Sarah K]
    role: VP Finance
    domains: [finance, pricing]
    decision_maker: true
    levers: [budget, pricing]
  - name: Dev Patel
    aliases: [Dev]
    role: Analyst
    domains: [cost model]
```

Without a roster, deep ingest still runs but marks authority `unknown`. A malformed roster is a hard error — fix it before ingesting.

The skill lives at `pmao/skills/ingest-deep.md`; edit it to change extraction behavior, no Python required.

## Review gate

`pmao review` walks every pending staged extraction item by item. Verdict keys: `[a]pprove / [e]dit / [r]eject` (hypotheses instead get `[p]romote to fact / [k]eep / [x] kill`), aliases `[y/n]`, review flags `[enter]` accept or `[o]` overturn, `[q]` quit. Writes commit at file boundary — quitting mid-file discards that file's verdicts and leaves it pending.

Every verdict is logged to `learning/verdicts.jsonl`. Durable lessons (confirmed/rejected aliases, rejected-item boundaries, overturned near-discards) are appended to `learning/calibration.md`, which deep ingest injects into every future extraction — the system learns your keep/discard line over time.

Syndication: `pmao syndicate <vault> --initiative init-001` prints the recommended stakeholder pathway to approval and stages the proposed meetings (with cadence, e.g. "biweekly until pricing review") for the same review gate.

## LLM backend

pmao auto-detects the backend from PATH. To use a specific backend:

```bash
pmao status my-project/ --backend claude
pmao ingest my-project/ --source notes.md --backend codex
```

Or set it permanently in the vault's `project-config.yaml` (the `--backend` flag wins when both are set; leave `llm_backend` null to auto-detect from PATH):

```yaml
llm_backend: claude
llm_timeout_seconds: 120
```

## Examples

See `examples/` for:
- `example-project-config.yaml` — a filled-out config
- `example-source-notes.md` — meeting notes ready to ingest
- `example-output-summary.md` — representative `pmao summarize` output
