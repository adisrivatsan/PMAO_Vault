# Vault Folders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat JSON vault with one folder per type and one markdown (frontmatter) file per item, keeping every existing command working.

**Architecture:** A new `pmao/store.py` owns markdown+frontmatter reading and writing. `vault.py`, `roster.py` and `ingest.py` swap their JSON reads/writes for store calls but keep the same in-memory shapes (`Initiative` dataclass, lists of dicts), so `excel.py`, the lint logic and most skills are untouched. A new `pmao migrate` converts old JSON vaults.

**Tech Stack:** Python >=3.9, `pyyaml`, `openpyxl`, pytest (run with `python3 -m pytest`).

**Spec:** `docs/superpowers/specs/2026-11-03-vault-folders-design.md`

## Global Constraints

- No new dependencies; frontmatter parsed/written with `pyyaml`.
- Folders: `projects/ tasks/ people/ meetings/ decisions/ notes/ docs/ inbox/`; vault root also holds `SCHEMA.md`, `project-config.yaml`, `workbook.xlsx`.
- `type` frontmatter is required on every item. Types: `project`, `task`, `person`, `meeting`, `decision`, `note`, `hypothesis`, `fact`, `inbox`. `hypothesis`/`fact`/`note` all live in `notes/`.
- Project `status` values stay `not_started|in_progress|ready|complete`; task status `open|done`.
- Stored dict key for the owning project stays `initiative_id` (my call, overrides the spec's `project` field name: it leaves `excel.py`, lint, and the skills untouched). The spec is updated in Task 6.
- Only `*.md` files in a type folder are items; anything else (`.bak`, `.DS_Store`) is ignored.
- Ingest keeps its confirm-then-apply flow; LLM extraction JSON schema is unchanged.

## Review Focus

- Text with `:`, quotes, `#`, or a line of `---` in a name/description round-trips unchanged (Task 1).
- Two items with the same title never overwrite each other (Task 1).
- A `.md` file with missing/malformed frontmatter is skipped with a warning, not a crash (Task 1).
- Multi-line `next_steps` or text containing `## ` survives a project save/load (Task 2).
- `pmao migrate` run twice does not duplicate items, and tolerates missing JSON files (Task 5).

## File Structure

- Create `pmao/store.py`: frontmatter parse/render, slugs, `read_items`, `write_item`.
- Create `pmao/templates/SCHEMA.md`: seed schema copied into new vaults.
- Create `pmao/migrate.py`: `migrate_vault`.
- Modify `pmao/vault.py`, `pmao/roster.py`, `pmao/ingest.py`, `pmao/cli.py`, `pmao/skills/ingest.md`, `README.md`, spec, and tests.

---

### Task 1: Markdown item store

**Files:**
- Create: `pmao/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Produces:
  - `FOLDERS: tuple` of the 8 folder names; `BODY_FIELD: dict` mapping type to its body field (`task`->`description`, `meeting`->`purpose`, `decision`->`decision`, `hypothesis`->`hypothesis`, `fact`->`claim`, `note`->`text`, `inbox`->`context`, `person`->none, `project`->none).
  - `parse_frontmatter(text: str) -> tuple[dict, str]` (raises `ValueError` if no valid frontmatter)
  - `render_frontmatter(meta: dict, body: str = "") -> str`
  - `slugify(text: str, max_len: int = 60) -> str`
  - `read_items(vault: Path, folder: str) -> list[dict]`: frontmatter keys, plus the body under its `BODY_FIELD` name, plus `_file` (filename stem, for rewrites)
  - `write_item(vault: Path, folder: str, item: dict, title: str) -> Path`: reuses `item["_file"]` if present, else slugs `title` with `-2`, `-3` on collision; atomic (tmp+replace); copies the previous file to `<name>.md.bak` when overwriting.

- [ ] **Step 1: Write failing tests** in `tests/test_store.py`:
  - `test_round_trip_special_characters`: item `{"type":"task","description":"Fix: the \"bug\" # 1\n---\nsecond line","owner":"A: B"}` written then read back equals the input (plus `_file`).
  - `test_same_title_does_not_overwrite`: two `write_item` calls with title "Pricing" (no `_file`) produce `pricing.md` and `pricing-2.md`, and `read_items` returns 2.
  - `test_rewrite_with_file_key_overwrites_and_backs_up`: read an item, change a field, `write_item` again; one `.md` file, one `.md.bak`.
  - `test_malformed_file_skipped_with_warning`: a `.md` with no frontmatter and one with invalid YAML are skipped, a warning is printed (capsys), valid items still returned.
  - `test_non_md_files_ignored`: `.DS_Store` and `x.md.bak` in the folder are not returned.
  - `test_missing_folder_returns_empty`.
  - `test_item_without_type_is_skipped_with_warning`.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_store.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement `pmao/store.py`** per the interfaces. Use `yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)` and split on the first two `---` lines only (so `---` inside the body is safe).
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `git add pmao/store.py tests/test_store.py && git commit -m "feat: markdown item store"`

### Task 2: Vault layout and projects as markdown

**Files:**
- Modify: `pmao/vault.py` (replace `VAULT_FILES`, `_cleanup_dead_files`, `init_vault`, `load_initiatives`, `save_initiatives`, `load_list`, `refresh_workbook`)
- Create: `pmao/templates/SCHEMA.md`
- Modify: `tests/test_vault.py`, `tests/test_packaging.py` (add `SCHEMA.md` to templates list)

**Interfaces:**
- Consumes: `store.read_items`, `store.write_item`, `store.FOLDERS`.
- Produces:
  - `VAULT_DIRS = store.FOLDERS`
  - `init_vault(vault_path, project_name, owner)`: creates all folders, `project-config.yaml`, `SCHEMA.md` (copied from the template), blank `workbook.xlsx`; still refuses if `project-config.yaml` or a `projects/` folder with any `.md` already exists.
  - `load_initiatives(vault_path) -> List[Initiative]` reads `projects/`; `save_initiatives(vault_path, initiatives)` writes one file per initiative (filename slug of `name`, reusing the existing file for the same `id`), removes no files.
  - `load_items(vault_path, folder, type=None) -> list[dict]` (replaces `load_list`; filters by `type` when given); `save_items(vault_path, folder, items: list[dict], title_key: str)` writes each item via `write_item`.
  - Project file layout: frontmatter `type, id, name, status, priority, owner, last_touched`; body sections `## Current state`, `## Next steps`, `## Last touch`, `## Notes` (omit empty ones).

- [ ] **Step 1: Write failing tests** in `tests/test_vault.py` (replace JSON-specific ones; keep the CSV-seed, refuse-existing and cmd_init tests, adapted):
  - `test_init_vault_creates_folders_and_schema`: all `VAULT_DIRS` exist, `SCHEMA.md` and `workbook.xlsx` exist, no `*.json` at root.
  - `test_project_round_trip_multiline`: `Initiative` with `next_steps="- a\n- b"` and `notes="## not a heading\nx"` saves and loads equal.
  - `test_project_file_is_readable_markdown`: saved file starts with `---`, has `type: project` and a `## Current state` heading.
  - `test_save_initiatives_reuses_file_for_same_id`: rename an initiative, save again, still one file.
  - `test_load_items_filters_by_type`.
  - Update `test_seed_from_csv_*` to assert via `load_initiatives`.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_vault.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces above; write `pmao/templates/SCHEMA.md` with the seed rules from the spec ("Schema rules" section) plus the folder table and the line "When you can't tell where something belongs, do not guess: write it to `inbox/` and ask." `refresh_workbook` builds its lists from `load_items` (tasks, meetings, decisions, and `notes` filtered by `hypothesis`/`fact`).
- [ ] **Step 4: Run** `python3 -m pytest tests/test_vault.py tests/test_packaging.py tests/test_excel.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "feat: folder-per-type vault layout, projects as markdown"` (after `git add` of new files).

### Task 3: People from `people/`

**Files:**
- Modify: `pmao/roster.py` (`load_roster` reads `people/*.md`); `pmao/vault.py` (drop `roster.yaml` scaffold from `init_vault`)
- Test: `tests/test_roster.py`

**Interfaces:**
- Consumes: `store.read_items(vault, "people")`.
- Produces: `load_roster(vault_path) -> Optional[List[dict]]` returning `[{"name","aliases","role"}]` or `None` when no people; `render_roster` unchanged.

- [ ] **Step 1: Rewrite tests** in `tests/test_roster.py` to build `people/jane-smith.md` (`type: person`, `name`, `aliases: [Jane]`, `role`) and assert `load_roster` returns it, returns `None` for an empty/missing folder, and skips a person file lacking `name` with a warning. Keep the `render_roster` tests as-is.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_roster.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `load_roster` on top of `read_items`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "feat: roster from people folder"`

### Task 4: Ingest, status, lint, summarize on the new folders

**Files:**
- Modify: `pmao/ingest.py` (`apply_updates`, `run_ingest`, `run_status`, `run_summarize`, `run_lint`), `pmao/skills/ingest.md`
- Test: `tests/test_ingest.py`, `tests/test_lint.py`

**Interfaces:**
- Consumes: `vault.load_items`, `vault.save_items`, `store.write_item`, `store.FOLDERS`.
- Produces: `apply_updates(vault_path, extraction, transcript_name)` writes new tasks to `tasks/` (`type: task`), meetings to `meetings/`, decisions to `decisions/`, hypotheses and facts to `notes/` (`type: hypothesis|fact`), and each `unmatched_references` entry to `inbox/` (`type: inbox`, fields `mention`, body `context`, `source`, `created`). Completed task ids flip `status: done` in place (same file). Item `id` formats unchanged (`act-`, `mtg-`, `dec-`, `hyp-`, `fact-`); `_build_ingest_prompt` gains a `schema: str = ""` argument replacing a new `{schema}` placeholder in `ingest.md`; `run_ingest` passes the vault's `SCHEMA.md` text (empty if missing).

- [ ] **Step 1: Update tests**: existing `test_apply_updates_*` assert via `load_items` instead of JSON files (same expectations); add `test_unmatched_reference_written_to_inbox`, `test_completed_action_rewrites_same_file`, `test_build_ingest_prompt_substitutes_schema`, `test_run_status_reports_inbox_count` (capsys contains "Inbox: 1"), `test_lint_prompt_mentions_inbox` is not needed; `run_lint` just prints the inbox count after the LLM text.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_ingest.py tests/test_lint.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the changes. `run_status` filters hypotheses with `load_items(vault, "notes", type="hypothesis")`. `run_status` and `run_lint` print `Inbox: N item(s) need filing: <filenames>` when `inbox/` is non-empty. Add the `{schema}` section ("## Vault schema (filing rules)") to `ingest.md` and one line telling the LLM to put anything it cannot place in `unmatched_references`.
- [ ] **Step 4: Run** `python3 -m pytest -q`. Expected: all PASS.
- [ ] **Step 5: Commit** `git commit -am "feat: ingest/status/lint/summarize read and write the folder vault"`

### Task 5: `pmao migrate`

**Files:**
- Create: `pmao/migrate.py`
- Test: `tests/test_migrate.py`

**Interfaces:**
- Consumes: `vault.save_initiatives`, `store.write_item`, `models.Initiative.from_dict`.
- Produces: `migrate_vault(vault_path: Path) -> dict[str, int]` returning counts by folder. Reads `initiatives.json`, `actions.json`, `meetings.json`, `decisions.json`, `hypotheses.json`, `facts.json`, `roster.yaml` (any missing file is skipped); creates folders if absent; moves `transcripts/*` into `docs/`; leaves the old JSON/YAML files in place; skips any item whose `id` already exists in its target folder (so a second run adds nothing).

- [ ] **Step 1: Write failing tests**: `test_migrate_converts_all_types` (build an old-layout vault in `tmp_path` with one of each; assert counts `{"projects":1,"tasks":1,...}`, `load_initiatives` returns it, tasks keep `initiative_id`/`status`, hypotheses/facts land in `notes/` with correct `type`, roster person lands in `people/`); `test_migrate_twice_adds_nothing`; `test_migrate_tolerates_missing_files`; `test_migrate_moves_transcripts_to_docs`; `test_migrate_leaves_old_files`.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_migrate.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `migrate_vault`; also copy `SCHEMA.md` from the template if the vault has none.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `git add pmao/migrate.py tests/test_migrate.py && git commit -m "feat: migrate old JSON vaults to folder layout"`

### Task 6: CLI, README, spec update

**Files:**
- Modify: `pmao/cli.py` (`cmd_init` output text; add `migrate` subcommand `pmao migrate <vault>` printing the per-folder counts), `README.md` (Vault Layout, Roster, Commands, Quick Start), the spec (`initiative_id` note under Frontmatter), `tests/test_vault.py` (`test_cmd_init_*` text if asserted)
- Test: `tests/test_cli.py` (create)

**Interfaces:**
- Consumes: `migrate.migrate_vault`.

- [ ] **Step 1: Write failing tests** in `tests/test_cli.py`: `test_migrate_command_prints_counts` (calls `main()` with `sys.argv = ["pmao","migrate",str(vault)]`, capsys contains "projects: 1"); `test_init_then_ingest_end_to_end` with `pmao.llm.call_structured` monkeypatched to return one project update, one new action and one unmatched reference, `--yes`; assert the project file's `## Current state` changed, a `tasks/*.md` exists, an `inbox/*.md` exists.
- [ ] **Step 2: Run** `python3 -m pytest tests/test_cli.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the CLI changes and rewrite the README vault-layout, roster and command sections for the folder layout; add the `initiative_id` note to the spec.
- [ ] **Step 4: Run** `python3 -m pytest -q`. Expected: all PASS.
- [ ] **Step 5: Commit** `git commit -am "feat: pmao migrate command, docs for folder vault"`
