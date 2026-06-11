# PMAO Simplification — Design

Date: 2026-06-11
Status: Approved pending user spec review

## Objective

Refactor pmao-cli down to its essential purpose: ingest raw text (transcripts,
emails, chat exports, notes) → propose updates to a tracked set of business
initiatives → confirm → apply → view/export status. Delete everything that does
not directly serve that loop.

Deviation from the original refactor brief, per user direction during design
review: **hypotheses, facts, and decisions are kept** (files, ingest
extraction, summarize sections, workbook representation). Signals, questions,
staging, and learning are deleted as briefed.

## Commands (exactly six)

- `pmao init <vault> [--roster FILE]` — create vault; optionally seed
  initiatives from CSV (`id,name,owner,priority`; only `name` required).
- `pmao ingest <vault> --source FILE [--yes] [--backend claude|codex]` —
  single ingest path. LLM extracts proposed changes; CLI prints a field-level
  diff; applies on confirmation (`--yes` skips the prompt).
- `pmao status <vault> [--backend ...]` — sorted status dashboard (LLM-rendered
  via `skills/status.md`).
- `pmao summarize <vault> [--backend ...]` — executive summary
  (`skills/summarize.md`).
- `pmao export <vault>` — regenerate `workbook.xlsx`.
- `pmao config <vault>` — print `project-config.yaml`.

Deleted commands: `update`, `review`, `syndicate`, and the `ingest --deep`
flag. Rationale for `update`: ingest covers it — "set init-003 to complete" in
a text file is a valid ingest source, and the ingest skill explicitly supports
status changes.

## Vault layout

```
vault/
  project-config.yaml   # project_name, owner, llm_backend, llm_timeout_seconds
  initiatives.json      # source of truth
  actions.json          # open action items, linked to initiative ids
  meetings.json         # meetings to schedule, linked to initiative ids
  decisions.json        # recorded decisions (kept)
  hypotheses.json       # tracked hypotheses (kept)
  facts.json            # extracted facts (kept)
  workbook.xlsx         # derived artifact
  transcripts/          # drop folder for source files
  roster.yaml           # OPTIONAL, user-supplied: name + aliases per person
```

Deleted from new vaults and **removed from existing vaults the first time the
vault is written** (ingest apply or export — never on read-only commands):
`signals.json`, `questions.json`, `staging/`, `learning/`.

## Initiative schema (slim)

`id, name, status, priority, owner, current_state, next_steps, last_touched,
last_touch_comment, notes`

- `status`: `not_started | in_progress | ready | complete`
- `priority`: `high | medium | low | null`
- `last_touched`: ISO date

### Lazy migration (in `Initiative.from_dict`)

Old-schema records are folded in-memory on load; the slim schema is written on
the next save. Read-only commands (`status`, `summarize`, `config`) never
rewrite files.

| Old field | Disposition |
|---|---|
| `coordination_owner` | → `owner` (primary) |
| `responsible_owner` | → `owner` fallback; if both present and differ, append `Responsible: X` to `notes` |
| `coordination_next_steps` | → `next_steps` |
| `last_touch_timestamp` | → `last_touched` when present |
| `outstanding_questions` | → `notes` with `Open questions:` label |
| `outstanding_meetings` | → `notes` with `Meetings:` label |
| `syndication_notes` | → `notes` with `Syndication:` label |
| `materials_link` | → `notes` with `Materials:` label |
| `created` | dropped |

## Ingest pipeline

1. Preprocess source (`transcript.py` unchanged: VTT → `Name: text`; everything
   else passes through verbatim — no format-specific logic).
2. Load vault state + optional roster; build prompt from `skills/ingest.md`.
3. `call_structured()` (unchanged `llm.py`: backend precedence = `--backend` >
   config > PATH auto-detect; JSON retry once).
4. Print diff of proposed changes:
   - per-initiative field changes as `field: old → new`
   - new actions / completed actions (matched by action id)
   - new meetings, decisions, hypotheses, facts
   - **Unmatched references** section — initiative mentions the LLM could not
     map to a known id are flagged here, never silently created or dropped
5. Confirm (`[y/N]`, skipped by `--yes`) → apply → save → refresh workbook.

### Ingest extraction shape (returned by skills/ingest.md)

```json
{
  "initiative_updates": [{"initiative_id", "status", "current_state",
                          "next_steps", "last_touch_comment"}],
  "new_actions":        [{"initiative_id", "description", "owner", "due"}],
  "completed_actions":  ["act-..."],
  "meetings":           [{"initiative_id", "purpose", "attendees"}],
  "decisions":          [{"initiative_id", "decision", "rationale", "owner"}],
  "hypotheses":         [{"initiative_id|null", "hypothesis", "owner",
                          "validation_path"}],
  "facts":              [{"initiative_id", "claim", "stated_by"}],
  "unmatched_references": [{"mention", "context"}]
}
```

Empty string on an initiative_update field means "no new information — leave
untouched"; the `[clear]` sentinel clears a field (existing behavior, kept).

### Roster

`roster.yaml` is ONLY a name+aliases list used to canonicalize owner names in
the ingest prompt:

```yaml
people:
  - name: Jane Smith
    aliases: [Jane, JS]
```

Missing or malformed roster → print a warning and continue. The current
hard-error behavior, authority/decision-maker/levers fields, and
`render_roster` authority text are all deleted.

## Workbook (exactly 6 tabs)

1. **Dashboard** — name, status, priority, owner, last_touched, current_state.
   Status conditional formatting kept (green/yellow/gray).
2. **Initiatives** — all ten slim fields.
3. **Actions & Decisions** — combined tab with a `type` column
   (`action`/`decision`): type, initiative, description/decision, owner,
   due (actions) / rationale (decisions), status, created, source.
   JSON files remain separate (actions have an open/done lifecycle; decisions
   are immutable records).
4. **Meetings** — initiative, purpose, attendees, status, created, source.
5. **Hypotheses** — level (project/initiative), initiative, hypothesis, owner,
   validation_path, status, created, source.
6. **Facts** — initiative, claim, stated_by, created, source.

Deleted tabs: Full Next Steps Log, Last Touch Log, Meeting Requests,
Milestones, Signals, Review Queue. Cell hygiene helpers kept (illegal-char
strip, 32767 truncation, `=` formula-injection guard).

## Skills (exactly three)

- `ingest.md` — rewritten to the extraction shape above; format-agnostic;
  instructs the model to put unmappable initiative mentions in
  `unmatched_references`.
- `status.md` — updated to slim fields (sort by status then priority; needs-
  attention and next-steps sections; last-touched list).
- `summarize.md` — updated to slim fields + actions, meetings, decisions,
  hypotheses, facts sections.

Deleted: `ingest-deep.md`, `update.md`, `syndicate.md`.

## Deletion map

| Path | Fate |
|---|---|
| `pmao/deep.py`, `pmao/review.py`, `pmao/syndicate.py` | delete |
| `pmao/skills/ingest-deep.md`, `update.md`, `syndicate.md` | delete |
| `pmao/templates/workbook-schema.yaml` | delete |
| `tests/test_deep.py`, `test_review.py`, `test_syndicate.py` | delete |
| `pmao/cli.py` | trim to 6 commands |
| `pmao/models.py` | slim schema + lazy migration |
| `pmao/vault.py` | drop staging/signals/questions plumbing; dead-file cleanup on write; seed columns `id,name,owner,priority` |
| `pmao/ingest.py` | rewrite: diff display, new extraction shape, roster injection; drop `run_update` |
| `pmao/excel.py` | 6 tabs |
| `pmao/roster.py` | slim to name+aliases, warn-don't-error |
| `pmao/templates/initiative-template.csv` | columns → `id,name,owner,priority` |
| `pmao/llm.py`, `pmao/transcript.py`, `pyproject.toml` | keep as-is |
| `README.md` | rewrite; quick start = exactly `init` → `ingest` → `status` |
| `examples/example-project-config.yaml`, `example-source-notes.md` | update to slim schema |
| `examples/example-output-summary.md` | delete (references removed summary sections) |

## Testing

LLM calls stubbed (existing monkeypatch pattern). Keep/rewrite tests for:

- each of the six commands (CLI wiring + happy path)
- vault round-trip: init → seed → save → load equality
- migration: old-schema initiatives.json loads, folds correctly, and writes
  slim schema; dead files removed on first write
- ingest apply: diff fields, `[clear]` sentinel, completed-action matching,
  unmatched references surfaced
- excel: 6 tabs, cell hygiene
- roster: missing/malformed warns and continues

## Acceptance

A new user goes from `pip install` to an updated dashboard in exactly three
commands: `pmao init`, `pmao ingest`, `pmao status`. README quick start states
exactly that. Final report includes deletion list, LOC before/after
(before: 4,769 total Python + 552 skill lines), and judgment calls.
