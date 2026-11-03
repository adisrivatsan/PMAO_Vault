# Vault schema

Every item is a markdown file with YAML frontmatter. `type` is required.

| Folder | type | Holds |
|---|---|---|
| `projects/` | project | Things being driven: id, name, status, priority, owner, last_touched |
| `tasks/` | task | One action: initiative_id, owner, due, status (open/done) |
| `people/` | person | name, aliases, role |
| `meetings/` | meeting | initiative_id, purpose, attendees, date |
| `decisions/` | decision | initiative_id, owner, rationale, date |
| `notes/` | note, hypothesis, fact | Context, beliefs to validate, sourced claims |
| `docs/` | | Source material (transcripts, exports) |
| `inbox/` | inbox | Items that could not be placed; the user resolves them |

## Rules

- Task vs project: a task is one action with one owner and a due date; a project has several steps or several people.
- Decision vs note: a decision records something agreed or resolved; anything else (context, opinion, observation) is a note.
- Hypothesis vs fact: a hypothesis is a belief to be validated; a fact is a sourced claim already true.
- When you can't tell where something belongs, do not guess: write it to `inbox/` and ask.
- This file is living: each misfiling becomes one added line here.
