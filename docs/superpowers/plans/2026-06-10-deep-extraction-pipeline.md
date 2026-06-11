# Deep Extraction Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `pmao ingest --deep` — rich staged extraction (facts, hypotheses, decisions, questions, principal signals, meetings, typed actions) that writes to `staging/` and never touches canonical files, per the approved spec `docs/superpowers/specs/2026-06-10-deep-extraction-pipeline-design.md`.

**Architecture:** New `pmao/roster.py` (roster load/render), new `pmao/deep.py` (prompt assembly, validation, staging write, `run_ingest_deep`), new `skills/ingest-deep.md` (adapted extraction skill with five `{placeholder}` slots), extended `pmao/excel.py` (Facts / Signals / Meetings / Review Queue tabs), extended `pmao/vault.py` (staging dir, new canonical files, `refresh_workbook` helper). Quick ingest path behavior unchanged.

**Tech Stack:** Python 3.9+, pyyaml, openpyxl, pytest. Repo: `PMAO GITHUB/pmao-cli` (run all commands from this directory).

**Spec:** `../docs/superpowers/specs/2026-06-10-deep-extraction-pipeline-design.md` (relative to repo root). The source extraction prompt being adapted lives at `../../transcript-extraction-skill.md` (vault root, outside the repo) — Task 5 embeds the full adapted content, you do not need the original.

---

## File map

| File | Action | Responsibility |
|------|--------|----------------|
| `pmao/roster.py` | Create | Load + validate `roster.yaml`; render prompt text block |
| `pmao/deep.py` | Create | Deep ingest: prompt assembly, reconciliation/calibration blocks, extraction validation, staging write, `run_ingest_deep` |
| `skills/ingest-deep.md` | Create | The adapted extraction skill (five placeholders) |
| `pmao/vault.py` | Modify | `init_vault` creates `staging/` + `facts.json`/`signals.json`/`meetings.json`; `load_list`, `staging_summaries`, `refresh_workbook` helpers |
| `pmao/excel.py` | Modify | Four new tabs; `create_workbook` gains `facts`, `signals`, `meetings`, `staged` params |
| `pmao/cli.py` | Modify | `--deep` flag on ingest; `cmd_export` uses `refresh_workbook` |
| `pmao/ingest.py` | Modify | `apply_updates` ends with `refresh_workbook` (shared regen path) |
| `README.md` | Modify | Document `--deep`, roster, staging |
| `tests/test_roster.py` | Create | Roster load/render tests |
| `tests/test_deep.py` | Create | Deep ingest tests |
| `tests/test_vault.py` | Modify | Init + helper tests |
| `tests/test_excel.py` | Modify | New-tab tests |

---

### Task 1: Roster module

**Files:**
- Create: `pmao/roster.py`
- Test: `tests/test_roster.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_roster.py`:

```python
import tempfile
from pathlib import Path

import pytest

from pmao.roster import load_roster, render_roster, RosterError


ROSTER_YAML = """\
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
"""


def test_load_roster_returns_people():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text(ROSTER_YAML)
        people = load_roster(vault)
        assert len(people) == 2
        assert people[0]["name"] == "Sarah Klein"
        assert people[0]["decision_maker"] is True
        assert people[1].get("decision_maker") is None


def test_load_roster_missing_file_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        assert load_roster(Path(tmp)) is None


def test_load_roster_invalid_yaml_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text("people: [unclosed")
        with pytest.raises(RosterError):
            load_roster(vault)


def test_load_roster_missing_people_key_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text("staff:\n  - name: X\n")
        with pytest.raises(RosterError, match="people"):
            load_roster(vault)


def test_load_roster_person_without_name_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text("people:\n  - role: Analyst\n")
        with pytest.raises(RosterError, match="name"):
            load_roster(vault)


def test_render_roster_marks_decision_makers():
    people = [
        {"name": "Sarah Klein", "aliases": ["Sarah"], "role": "VP Finance",
         "domains": ["finance"], "decision_maker": True, "levers": ["budget"]},
        {"name": "Dev Patel", "domains": ["cost model"]},
    ]
    text = render_roster(people)
    assert "Sarah Klein" in text
    assert "DECISION-MAKER" in text
    assert "levers: budget" in text
    assert "owns: cost model" in text
    # Non-decision-maker line must not be marked
    dev_line = [ln for ln in text.splitlines() if "Dev Patel" in ln][0]
    assert "DECISION-MAKER" not in dev_line


def test_render_roster_none_gives_no_roster_text():
    text = render_roster(None)
    assert "No roster was provided" in text
    assert "unknown" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_roster.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pmao.roster'`

- [ ] **Step 3: Write the implementation**

Create `pmao/roster.py`:

```python
from pathlib import Path
from typing import List, Optional

import yaml


class RosterError(Exception):
    pass


def load_roster(vault_path: Path) -> Optional[List[dict]]:
    """Return the people list from roster.yaml, or None if the file is absent.

    Raises RosterError on malformed content — a half-parsed roster silently
    corrupts authority calls, so malformed is a hard error (per spec).
    """
    roster_path = vault_path / "roster.yaml"
    if not roster_path.exists():
        return None
    try:
        data = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise RosterError(f"roster.yaml is not valid YAML: {e}")
    if not isinstance(data, dict) or not isinstance(data.get("people"), list):
        raise RosterError("roster.yaml must contain a top-level 'people:' list")
    people = data["people"]
    for i, person in enumerate(people):
        if not isinstance(person, dict) or not person.get("name"):
            raise RosterError(f"roster.yaml people[{i}] is missing required 'name'")
    return people


def render_roster(people: Optional[List[dict]]) -> str:
    """Render the roster as a prompt-ready text block."""
    if not people:
        return (
            'No roster was provided. Mark authority "unknown" and lower '
            "confidence; never invent owners. There are no principals — "
            "leave principal_signals empty."
        )
    lines = []
    for p in people:
        parts = [p["name"]]
        if p.get("aliases"):
            parts.append(f"aliases: {', '.join(p['aliases'])}")
        if p.get("role"):
            parts.append(f"role: {p['role']}")
        if p.get("domains"):
            parts.append(f"owns: {', '.join(p['domains'])}")
        if p.get("decision_maker"):
            levers = f" (levers: {', '.join(p['levers'])})" if p.get("levers") else ""
            parts.append(f"DECISION-MAKER{levers}")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_roster.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add pmao/roster.py tests/test_roster.py
git commit -m "feat: add roster module — load/validate roster.yaml, render prompt block"
```

---

### Task 2: Vault extensions — staging dir, new canonical files, load_list

**Files:**
- Modify: `pmao/vault.py`
- Test: `tests/test_vault.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vault.py`:

```python
def test_init_vault_creates_deep_extraction_files():
    import tempfile
    from pathlib import Path
    from pmao.vault import init_vault
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        assert (vault / "staging").is_dir()
        assert (vault / "facts.json").read_text() == "[]"
        assert (vault / "signals.json").read_text() == "[]"
        assert (vault / "meetings.json").read_text() == "[]"


def test_load_list_missing_file_returns_empty():
    import tempfile
    from pathlib import Path
    from pmao.vault import load_list
    with tempfile.TemporaryDirectory() as tmp:
        assert load_list(Path(tmp), "facts.json") == []


def test_load_list_reads_json_array():
    import json
    import tempfile
    from pathlib import Path
    from pmao.vault import load_list
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "facts.json").write_text(json.dumps([{"id": "fact-1"}]))
        assert load_list(vault, "facts.json") == [{"id": "fact-1"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vault.py -v -k "deep_extraction or load_list"`
Expected: FAIL (`staging` dir missing; `ImportError: cannot import name 'load_list'`)

- [ ] **Step 3: Implement**

In `pmao/vault.py`, extend `VAULT_FILES`:

```python
VAULT_FILES = [
    "project-config.yaml",
    "initiatives.json",
    "actions.json",
    "questions.json",
    "decisions.json",
    "hypotheses.json",
    "facts.json",
    "signals.json",
    "meetings.json",
    "workbook.xlsx",
]
```

In `init_vault`, after `(vault_path / "transcripts").mkdir(exist_ok=True)` add:

```python
    (vault_path / "staging").mkdir(exist_ok=True)
```

After the `hypotheses.json` line add:

```python
    (vault_path / "facts.json").write_text("[]")
    (vault_path / "signals.json").write_text("[]")
    (vault_path / "meetings.json").write_text("[]")
```

Add at module level (after `save_initiatives`):

```python
def load_list(vault_path: Path, filename: str) -> list:
    """Load a JSON-array vault file; empty list if absent."""
    path = vault_path / filename
    return json.loads(path.read_text()) if path.exists() else []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_vault.py -v`
Expected: all pass (existing + 3 new)

- [ ] **Step 5: Commit**

```bash
git add pmao/vault.py tests/test_vault.py
git commit -m "feat: init staging/ dir and facts/signals/meetings canonical files; add load_list"
```

---

### Task 3: Workbook — Facts, Signals, Meetings, Review Queue tabs

**Files:**
- Modify: `pmao/excel.py`
- Test: `tests/test_excel.py`

The Meetings tab combines structured `meetings.json` rows with each initiative's free-text `outstanding_meetings` field (marked by a `row_source` column), per locked decision 8. The existing "Meeting Requests" tab is legacy — leave it untouched.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_excel.py`:

```python
def test_workbook_has_deep_extraction_tabs_when_empty():
    import tempfile
    from pathlib import Path
    from openpyxl import load_workbook
    from pmao.excel import create_workbook
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "wb.xlsx"
        create_workbook(path, [])
        wb = load_workbook(path)
        for tab in ("Facts", "Signals", "Meetings", "Review Queue"):
            assert tab in wb.sheetnames, f"missing tab {tab}"
        # Header row present even when empty
        assert wb["Facts"].cell(row=1, column=2).value == "initiative"
        assert wb["Review Queue"].cell(row=1, column=1).value == "staging_file"


def test_workbook_populates_facts_signals_and_review_queue():
    import tempfile
    from datetime import date
    from pathlib import Path
    from openpyxl import load_workbook
    from pmao.excel import create_workbook
    from pmao.models import Initiative

    init = Initiative(id="init-001", name="Pricing", status="in_progress",
                      created=date(2026, 6, 1), last_touched=date(2026, 6, 10))
    facts = [{"id": "fact-0001", "initiative_id": "init-001",
              "claim": "Q2 cost-to-serve up 9%", "stated_by": "Sarah Klein",
              "authority": "owner", "confidence": "high", "inferred": False,
              "source_span": "line 12", "source": "sync.vtt", "created": "2026-06-10"}]
    signals = [{"id": "sig-0001", "initiative_id": "init-001",
                "principal": "Sarah Klein", "lever": "pricing",
                "signal": "wants floor pricing", "implication": "raise floor",
                "source": "sync.vtt", "created": "2026-06-10"}]
    staged = [{"staging_file": "2026-06-10-sync.json", "category": "action_items",
               "initiative_id": "init-001", "summary": "build the cost model"}]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "wb.xlsx"
        create_workbook(path, [init], facts=facts, signals=signals, staged=staged)
        wb = load_workbook(path)
        assert wb["Facts"].cell(row=2, column=3).value == "Q2 cost-to-serve up 9%"
        assert wb["Facts"].cell(row=2, column=2).value == "Pricing"  # id resolved to name
        assert wb["Signals"].cell(row=2, column=5).value == "wants floor pricing"
        assert wb["Review Queue"].cell(row=2, column=2).value == "action_items"
        assert wb["Review Queue"].cell(row=2, column=4).value == "build the cost model"


def test_meetings_tab_combines_structured_and_initiative_field():
    import tempfile
    from datetime import date
    from pathlib import Path
    from openpyxl import load_workbook
    from pmao.excel import create_workbook
    from pmao.models import Initiative

    init = Initiative(id="init-001", name="Pricing", status="in_progress",
                      created=date(2026, 6, 1), last_touched=date(2026, 6, 10))
    init.outstanding_meetings = "- Kickoff with data team"
    meetings = [{"id": "mtg-0001", "initiative_id": "init-001",
                 "purpose": "align on cost model", "convener": "Sarah Klein",
                 "attendees": ["Finance", "CS"], "functions": ["finance"],
                 "target_timing": "next week", "status": "open",
                 "source": "sync.vtt", "created": "2026-06-10"}]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "wb.xlsx"
        create_workbook(path, [init], meetings=meetings)
        wb = load_workbook(path)
        ws = wb["Meetings"]
        rows = [[ws.cell(row=r, column=c).value for c in range(1, 11)] for r in (2, 3)]
        purposes = {row[2] for row in rows}
        sources = {row[8] for row in rows}
        assert "align on cost model" in purposes
        assert "- Kickoff with data team" in purposes
        assert sources == {"meetings.json", "initiative-field"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_excel.py -v -k "deep_extraction_tabs or populates_facts or combines_structured"`
Expected: FAIL (`KeyError: 'Worksheet Facts does not exist.'` and `TypeError: create_workbook() got an unexpected keyword argument 'facts'`)

- [ ] **Step 3: Implement**

In `pmao/excel.py`, add column definitions after `HYPOTHESIS_COLS`:

```python
FACT_COLS = [
    "id", "initiative", "claim", "stated_by", "authority",
    "confidence", "inferred", "source_span", "source", "created",
]

SIGNAL_COLS = [
    "id", "initiative", "principal", "lever", "signal",
    "implication", "source", "created",
]

MEETING_COLS = [
    "id", "initiative", "purpose", "convener", "attendees",
    "functions", "target_timing", "status", "row_source", "created",
]

REVIEW_QUEUE_COLS = ["staging_file", "category", "initiative_id", "summary"]
```

Change the `create_workbook` signature:

```python
def create_workbook(
    path: Path,
    initiatives: List[Initiative],
    meeting_requests: Optional[list] = None,
    milestones: Optional[list] = None,
    hypotheses: Optional[list] = None,
    facts: Optional[list] = None,
    signals: Optional[list] = None,
    meetings: Optional[list] = None,
    staged: Optional[list] = None,
) -> None:
```

At the end of `create_workbook`, just before `wb.save(path)`, add the four tabs. Note `_write_data_row` coerces falsy values to `""`, so booleans/lists are pre-rendered to strings in the record dicts:

```python
    init_names = {i.id: i.name for i in initiatives}

    # ── Tab 7: Facts ──────────────────────────────────────────────────────────
    ws_f = wb.create_sheet("Facts")
    _write_header_row(ws_f, FACT_COLS)
    for row_num, f in enumerate(facts or [], start=2):
        iid = f.get("initiative_id")
        record = dict(f)
        record["initiative"] = init_names.get(iid, iid or "")
        record["inferred"] = "yes" if f.get("inferred") else "no"
        _write_data_row(ws_f, row_num, FACT_COLS, record)
    ws_f.column_dimensions["B"].width = 28
    ws_f.column_dimensions["C"].width = 60
    ws_f.column_dimensions["H"].width = 40
    ws_f.freeze_panes = "A2"

    # ── Tab 8: Signals ────────────────────────────────────────────────────────
    ws_s = wb.create_sheet("Signals")
    _write_header_row(ws_s, SIGNAL_COLS)
    for row_num, s in enumerate(signals or [], start=2):
        iid = s.get("initiative_id")
        record = dict(s)
        record["initiative"] = init_names.get(iid, iid or "")
        _write_data_row(ws_s, row_num, SIGNAL_COLS, record)
    ws_s.column_dimensions["B"].width = 28
    ws_s.column_dimensions["E"].width = 50
    ws_s.column_dimensions["F"].width = 50
    ws_s.freeze_panes = "A2"

    # ── Tab 9: Meetings (structured + initiative free-text, combined) ────────
    ws_m = wb.create_sheet("Meetings")
    _write_header_row(ws_m, MEETING_COLS)
    meeting_rows = []
    for m in meetings or []:
        iid = m.get("initiative_id")
        record = dict(m)
        record["initiative"] = init_names.get(iid, iid or "")
        record["attendees"] = ", ".join(m.get("attendees") or [])
        record["functions"] = ", ".join(m.get("functions") or [])
        record["row_source"] = "meetings.json"
        meeting_rows.append(record)
    for init in initiatives:
        if init.outstanding_meetings:
            meeting_rows.append({
                "id": "", "initiative": init.name,
                "purpose": init.outstanding_meetings,
                "convener": "", "attendees": "", "functions": "",
                "target_timing": "", "status": "open",
                "row_source": "initiative-field", "created": "",
            })
    for row_num, record in enumerate(meeting_rows, start=2):
        _write_data_row(ws_m, row_num, MEETING_COLS, record)
    ws_m.column_dimensions["B"].width = 28
    ws_m.column_dimensions["C"].width = 60
    ws_m.column_dimensions["E"].width = 30
    ws_m.freeze_panes = "A2"

    # ── Tab 10: Review Queue (pending staged items) ───────────────────────────
    ws_rq = wb.create_sheet("Review Queue")
    _write_header_row(ws_rq, REVIEW_QUEUE_COLS)
    for row_num, item in enumerate(staged or [], start=2):
        _write_data_row(ws_rq, row_num, REVIEW_QUEUE_COLS, item)
    ws_rq.column_dimensions["A"].width = 30
    ws_rq.column_dimensions["B"].width = 20
    ws_rq.column_dimensions["C"].width = 14
    ws_rq.column_dimensions["D"].width = 80
    ws_rq.freeze_panes = "A2"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_excel.py -v`
Expected: all pass (existing + 3 new)

- [ ] **Step 5: Commit**

```bash
git add pmao/excel.py tests/test_excel.py
git commit -m "feat: add Facts, Signals, Meetings (combined), Review Queue workbook tabs"
```

---

### Task 4: `staging_summaries` + `refresh_workbook` shared regen path

**Files:**
- Modify: `pmao/vault.py`
- Modify: `pmao/ingest.py` (end of `apply_updates`)
- Modify: `pmao/cli.py` (`cmd_export`)
- Test: `tests/test_vault.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vault.py`:

```python
def test_staging_summaries_flattens_pending_files():
    import json
    import tempfile
    from pathlib import Path
    from pmao.vault import init_vault, staging_summaries
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        staged = {
            "status": "pending_review",
            "ingested": "2026-06-10",
            "source": "sync.vtt",
            "prompt_version": "pmao-deep-v1.0",
            "extraction": {
                "facts": [{"initiative_id": "init-001", "claim": "cost up 9%"}],
                "action_items": [{"initiative_id": None, "description": "build model"}],
                "review_flags": ["possible board-memo commitment, owner unclear"],
            },
        }
        (vault / "staging" / "2026-06-10-sync.json").write_text(json.dumps(staged))
        # Reviewed files are excluded
        done = dict(staged, status="reviewed")
        (vault / "staging" / "2026-06-09-old.json").write_text(json.dumps(done))

        rows = staging_summaries(vault)
        assert len(rows) == 3  # fact + action + review_flag
        by_cat = {r["category"]: r for r in rows}
        assert by_cat["facts"]["summary"] == "cost up 9%"
        assert by_cat["facts"]["staging_file"] == "2026-06-10-sync.json"
        assert by_cat["action_items"]["initiative_id"] == ""
        assert by_cat["review_flag"]["summary"].startswith("possible board-memo")


def test_refresh_workbook_renders_canonical_and_staged():
    import json
    import tempfile
    from pathlib import Path
    from openpyxl import load_workbook
    from pmao.vault import init_vault, refresh_workbook
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        (vault / "facts.json").write_text(json.dumps(
            [{"id": "fact-0001", "initiative_id": "general", "claim": "a fact"}]))
        (vault / "staging" / "x.json").write_text(json.dumps({
            "status": "pending_review",
            "extraction": {"facts": [{"initiative_id": "general", "claim": "staged fact"}]},
        }))
        refresh_workbook(vault)
        wb = load_workbook(vault / "workbook.xlsx")
        assert wb["Facts"].cell(row=2, column=3).value == "a fact"
        assert wb["Review Queue"].cell(row=2, column=4).value == "staged fact"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vault.py -v -k "staging_summaries or refresh_workbook"`
Expected: FAIL with `ImportError: cannot import name 'staging_summaries'`

- [ ] **Step 3: Implement**

Add to `pmao/vault.py` (after `load_list`):

```python
_STAGED_CATEGORIES = {
    "facts": "claim",
    "hypotheses": "theory",
    "decisions": "decision",
    "open_questions": "question",
    "principal_signals": "signal",
    "meetings_to_schedule": "purpose",
    "action_items": "description",
}


def staging_summaries(vault_path: Path) -> list:
    """One Review Queue row per item in every pending_review staging file.

    Each review_flag also becomes its own row (category 'review_flag') so the
    workbook surfaces what the extractor wants a human to look at.
    """
    rows = []
    staging_dir = vault_path / "staging"
    if not staging_dir.exists():
        return rows
    for f in sorted(staging_dir.glob("*.json")):
        staged = json.loads(f.read_text())
        if staged.get("status") != "pending_review":
            continue
        extraction = staged.get("extraction", {})
        for category, summary_key in _STAGED_CATEGORIES.items():
            for item in extraction.get(category, []):
                rows.append({
                    "staging_file": f.name,
                    "category": category,
                    "initiative_id": item.get("initiative_id") or "",
                    "summary": item.get(summary_key, ""),
                })
        for flag in extraction.get("review_flags", []):
            rows.append({
                "staging_file": f.name,
                "category": "review_flag",
                "initiative_id": "",
                "summary": flag,
            })
    return rows


def refresh_workbook(vault_path: Path) -> None:
    """Regenerate workbook.xlsx from everything on disk (canonical + staging)."""
    from pmao.excel import create_workbook
    create_workbook(
        vault_path / "workbook.xlsx",
        load_initiatives(vault_path),
        hypotheses=load_list(vault_path, "hypotheses.json"),
        facts=load_list(vault_path, "facts.json"),
        signals=load_list(vault_path, "signals.json"),
        meetings=load_list(vault_path, "meetings.json"),
        staged=staging_summaries(vault_path),
    )
```

In `pmao/ingest.py`, replace the last two lines of `apply_updates`:

```python
    save_initiatives(vault_path, initiatives)
    create_workbook(vault_path / "workbook.xlsx", initiatives, hypotheses=all_hyp)
```

with:

```python
    save_initiatives(vault_path, initiatives)
    refresh_workbook(vault_path)
```

and change the imports at the top of `pmao/ingest.py` from:

```python
from pmao.vault import load_initiatives, save_initiatives
from pmao.excel import create_workbook
```

to:

```python
from pmao.vault import load_initiatives, save_initiatives, refresh_workbook
```

In `pmao/cli.py`, replace the body of `cmd_export`:

```python
def cmd_export(args) -> None:
    from pmao.vault import load_initiatives, refresh_workbook
    vault = Path(args.vault)
    initiatives = load_initiatives(vault)
    refresh_workbook(vault)
    print(f"Exported {len(initiatives)} initiatives to {(vault / 'workbook.xlsx').resolve()}")
```

- [ ] **Step 4: Run the full suite to verify everything passes (apply_updates regression included)**

Run: `python -m pytest tests/ -v`
Expected: all pass — `tests/test_ingest.py` exercises `apply_updates`, which now routes through `refresh_workbook`

- [ ] **Step 5: Commit**

```bash
git add pmao/vault.py pmao/ingest.py pmao/cli.py tests/test_vault.py
git commit -m "feat: staging_summaries + refresh_workbook shared regen; route apply_updates and export through it"
```

---

### Task 5: The deep-extraction skill file

**Files:**
- Create: `skills/ingest-deep.md`
- Test: `tests/test_deep.py` (skill-file tests only; more added in Task 6)

This is the approved adaptation of `transcript-extraction-skill.md` (spec §"Skill adaptation"): five `{placeholder}` slots, `initiative_id` on every item, unified roster (DECISION-MAKER attribute replaces the separate principal roster), chunking removed (`meta.chunk` fixed `"1/1"`), calibration block added, self-learning/scoreboard design notes dropped, `prompt_version` = `pmao-deep-v1.0`. The complete file content is below — create it verbatim, do not consult the original.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deep.py`:

```python
from pathlib import Path

SKILL_PATH = Path(__file__).parent.parent / "skills" / "ingest-deep.md"
PLACEHOLDERS = ["{initiatives}", "{roster}", "{reconciliation_candidates}", "{calibration}", "{source}"]


def test_skill_file_has_all_placeholders():
    text = SKILL_PATH.read_text(encoding="utf-8")
    for ph in PLACEHOLDERS:
        assert ph in text, f"missing placeholder {ph}"


def test_skill_file_has_no_legacy_roster_or_chunking():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "owner_roster" not in text
    assert "principal_roster" not in text
    assert "pre-chunked" not in text
    assert '"chunk": "1/1"' in text
    assert "pmao-deep-v1.0" in text


def test_skill_file_requires_initiative_id_everywhere():
    text = SKILL_PATH.read_text(encoding="utf-8")
    # Every category block in the output schema carries initiative_id
    assert text.count('"initiative_id"') >= 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deep.py -v`
Expected: FAIL with `FileNotFoundError` (skill file does not exist)

- [ ] **Step 3: Create `skills/ingest-deep.md` with exactly this content**

````markdown
---
name: pmao-ingest-deep
description: Rich staged extraction from source material — facts, hypotheses, decisions, questions, signals, meetings, typed actions — for the weekly review gate
---

# PMAO Deep Ingest

You are the Transcript Extraction Stage of a project-management memory system.

You receive a meeting transcript plus injected context, and you return strict JSON. You are one component of a larger pipeline. You do NOT mint IDs, do NOT write files, do NOT reconcile or merge against memory, and do NOT decide what becomes canonical. The surrounding system does all of that. Your only job: read the transcript against the injected context and emit a clean, flagged, machine-parseable extraction for staging.

Operational notes:
- Run at low temperature. Two runs of the same transcript should agree.
- Stamp prompt_version "pmao-deep-v1.0" into every output so quality can be diffed across revisions.

---

## What the system injects (read these; they are your context)

### Current initiatives

{initiatives}

Map every extracted item to one of these via `initiative_id`: a listed id, `"general"` if it belongs to the project but matches no initiative, or `null` when the item is deliberately project-level (hypotheses especially). Never force-map an item that spans initiatives to a single one.

### Roster

{roster}

This is your authority source. A person's "owns:" domains drive fact-vs-hypothesis. Entries marked DECISION-MAKER are the principals — scope principal signals to them and to the levers they control. Resolve every owner, convener, and attendee against this roster. If no roster was provided, do not guess authority — mark authority "unknown" and lower confidence.

### Reconciliation candidates (currently open items)

{reconciliation_candidates}

If candidates are listed above, you may flag likely matches: attach the candidate's id in `reconciliation_candidates` with a confidence. You do NOT merge or close anything — you only attach candidate references. If the block says "none", skip reconciliation entirely.

### Lessons from prior review sessions

{calibration}

Apply these lessons: confirmed alias maps, keep/discard boundary examples, and authority corrections from past human reviews take precedence over your defaults.

---

## Staging discipline (this is a proposal, not the truth)

Everything you output is staged for a **weekly human review** before promotion to canonical memory. A human gate sits downstream. Because of that gate, bias toward **recall over precision**: when an item is plausibly real but ambiguous, extract it and flag it for review rather than dropping it silently. A flagged false positive costs a reviewer ten seconds; a silently missed commitment is lost forever. Put anything uncertain into `review_flags`.

**The gate must see what you dropped, not only what you kept.** Understanding what to discard is as important as understanding what to keep — a wrongly discarded commitment is invisible and permanent, and the keep/discard boundary is exactly where your judgment is least reliable. Do not enumerate obvious noise, but every **borderline discard** — a line you nearly kept — goes into `review_flags` as "near-discard: [line] — dropped because [reason]." Confirming that boundary at the weekly review is what calibrates the signal/noise threshold over time, so treat surfacing close-call drops as a first-class output, not an afterthought.

---

## Core rule

Every candidate item passes: "If this disappeared, would someone who missed the meeting lose something they could act on, be held to, decide from, or follow up on?" If yes, extract. If no, DISCARD. Most categories are knowledge; commitment is distinct and comes in two forms handled differently downstream — **meetings to schedule** (calendar objects: attendees, purpose, timing) and **action items** (tasks: owner, due date). DISCARD is most of the transcript.

---

## The categories

- **FACT** — definitive claim. Authority comes from the roster: if the speaker owns the domain → fact, high confidence. If they don't, or aren't in the roster → hypothesis, or fact with inferred=true and low confidence.
- **HYPOTHESIS** — working theory or hunch. Default ambiguous claims here. Flag each in review_flags for validation at the weekly gate — promote to fact, keep as hypothesis, or kill.
- **DECISION** — a choice made, including implied (clear call + assent). Mark explicit true/false.
- **OPEN QUESTION** — unresolved, NO owner. With an owner + deadline it becomes an information_gathering action referencing it.
- **PRINCIPAL SIGNAL** — a preference/priority/constraint from a DECISION-MAKER in the roster, scoped to a lever they control. Capture the implication for the lever.
- **MEETING TO SCHEDULE** — a commitment to convene people, split out of action items because it is a calendar object, not a task. Resolve the convener and attendees against the roster. If one sentence both schedules a meeting and assigns work, split it into a meeting and an action.
- **ACTION ITEM** — a commitment with a single accountable owner resolved against the roster. Six sub-types: analysis_required, communication, decision_pending, artifact_production, external_ask, information_gathering. If no single owner, committee_ownership=true and add to review_flags.
- **DISCARD** — noise. Summarize the volume in discard_note; do not enumerate the obvious. But surface every borderline drop — a line you nearly kept — to review_flags as a near-discard, with the reason you dropped it. The gate, not the extractor, decides the close calls.

---

## Owner and alias resolution

Resolve every owner and speaker name against the roster:
- Exact or clear match → set owner and owner_resolution="matched_roster".
- Name variant that maps confidently to one roster entry ("Sarah" → "Sarah Klein") → owner_resolution="alias_merged", and record it in alias_flags with needs_review=true. Auto-merge, but always leave the breadcrumb for the human gate.
- No confident match → owner=null, owner_resolution="unresolved", add to review_flags. Never invent a roster member.

Apply the same resolution to a meeting's convener and to each named attendee.

---

## Provenance and IDs

- Every item carries source_span (a short quote or line reference). No span → suspect; flag it.
- Do NOT generate IDs. The system assigns them. Reference related items by description text (e.g. related_question: "Epic module pricing"), not by ID — except reconciliation_candidates, where you echo the injected candidate's existing id.

---

## Output: strict JSON only

Return one JSON object, no prose before or after, no markdown fences. Empty arrays for empty categories. Every item in every category carries `initiative_id` (a listed id, "general", or null). Use exactly this shape:

{
  "meta": {
    "meeting_slug": "yyyy-mm-dd-short-slug",
    "date": "yyyy-mm-dd",
    "source": "filename or transcript id",
    "attendees": ["..."],
    "principals_present": ["..."],
    "topic": "one neutral line",
    "prompt_version": "pmao-deep-v1.0",
    "chunk": "1/1"
  },
  "facts": [
    {"initiative_id": "init-001", "claim": "", "stated_by": "", "authority": "owner|non_owner|unknown", "confidence": "high|med|low", "inferred": false, "source_span": ""}
  ],
  "hypotheses": [
    {"initiative_id": null, "theory": "", "held_by": "", "confidence": "high|med|low", "would_confirm": "", "source_span": ""}
  ],
  "decisions": [
    {"initiative_id": "init-001", "decision": "", "decided_by": "", "context": "", "stakeholders": [], "reversible": "yes|no|unknown", "explicit": true, "source_span": ""}
  ],
  "open_questions": [
    {"initiative_id": "init-001", "question": "", "raised_by": "", "why_it_matters": "", "source_span": ""}
  ],
  "principal_signals": [
    {"initiative_id": "init-001", "principal": "", "lever": "", "signal": "", "implication": "", "source_span": ""}
  ],
  "meetings_to_schedule": [
    {
      "initiative_id": "init-001",
      "purpose": "what the meeting is for, one line",
      "convener": "resolved name or null",
      "convener_resolution": "matched_roster|alias_merged|unresolved",
      "attendees": ["resolved names or roles"],
      "requester": "principal or self",
      "functions": ["finance", "cs"],
      "target_timing": "yyyy-mm-dd | trigger phrase (e.g. 'before pricing review') | unspecified",
      "related_decision": "text ref or null",
      "related_question": "text ref or null",
      "committee_ownership": false,
      "reconciliation_candidates": [{"existing": "id from injected candidates", "match_confidence": "high|med|low"}],
      "source_span": ""
    }
  ],
  "action_items": [
    {
      "initiative_id": "init-001",
      "type": "analysis_required|communication|decision_pending|artifact_production|external_ask|information_gathering",
      "description": "imperative, one sentence",
      "owner": "resolved name or null",
      "owner_resolution": "matched_roster|alias_merged|unresolved",
      "committee_ownership": false,
      "requester": "principal or self",
      "functions": ["finance", "cs"],
      "due": "yyyy-mm-dd|unspecified",
      "related_question": "text ref or null",
      "related_decision": "text ref or null",
      "blocks": "text ref or null",
      "reconciliation_candidates": [{"existing": "id from injected candidates", "match_confidence": "high|med|low"}],
      "source_span": ""
    }
  ],
  "alias_flags": [
    {"variants": ["Sarah", "Sarah K"], "resolved_to": "Sarah Klein", "confidence": "high|med|low", "needs_review": true}
  ],
  "discard_note": "one line, e.g. 'Discarded ~85%: standup logistics, rapport, two resolved tangents'",
  "review_flags": ["short notes on items the weekly human review should look at"]
}

Rules: single-threaded ownership; one sub-type per action; do not split one commitment or merge two; a sentence that both schedules a meeting and assigns work becomes one meeting_to_schedule plus one action_item; reconciliation_candidates only when candidates were injected, and only as a flag — never a merge.

---

## Compact examples (the calls the roster changes)

**Authority from the roster.**
Roster: Sarah Klein owns finance (DECISION-MAKER). Heard: Sarah — "Q2 cost-to-serve is up 9%." A PM — "I think margins are fine though."
Output: facts: [{initiative_id:"general", claim:"Q2 cost-to-serve up 9%", stated_by:"Sarah Klein", authority:"owner", confidence:"high", inferred:false}]; hypotheses: [{initiative_id:"general", theory:"margins are fine", held_by:"PM", confidence:"low"}].
Why: the roster makes Sarah authoritative on finance; the PM is not, so their read is a hypothesis.

**Alias merge with breadcrumb.**
Heard: "Sarah will run the analysis." Roster has one "Sarah Klein."
Output: action owner="Sarah Klein", owner_resolution="alias_merged"; alias_flags: [{variants:["Sarah"], resolved_to:"Sarah Klein", confidence:"high", needs_review:true}].
Why: auto-merge to keep the registry clean, but leave the breadcrumb for the gate.

**Recall over precision at the gate.**
Heard: a muffled exchange where someone may have committed to drafting a board memo, but the owner is unclear.
Output: extract the action, owner=null, owner_resolution="unresolved", committee_ownership=false, and add "possible board-memo commitment, owner unclear — confirm at review" to review_flags.
Why: a human prunes downstream. Surface it flagged rather than dropping it.

**Surfacing a borderline discard.**
Heard: "We should probably revisit the SLA language at some point." — vague, no owner, no date.
Output: not extracted as an action (no owner, no deadline), but add "near-discard: vague SLA-revisit aside, dropped (no owner/date) — confirm it isn't a real open item" to review_flags.
Why: the discard side gets the same treatment as the keep side. The gate, not the extractor, decides whether a vague aside is the seed of a real thread.

**Meeting and action from one sentence.**
Heard: "Let's get Finance and CS together next week on the cost model — Dev, build it first."
Output: meetings_to_schedule: [{initiative_id:resolved-or-"general", purpose:"align on cost model", attendees:["Finance","CS"], target_timing:"next week", convener:resolved-or-null}]; action_items: [{initiative_id:resolved-or-"general", type:"analysis_required", description:"build the cost model", owner:"Dev Patel", due:"before the meeting"}].
Why: a meeting is a calendar object; the model is a task. Two commitments, two homes.

---

## Source material

{source}

Return only the JSON object.
````

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_deep.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add skills/ingest-deep.md tests/test_deep.py
git commit -m "feat: add ingest-deep skill — staged rich extraction with initiative mapping, unified roster, calibration"
```

---

### Task 6: Deep module — prompt assembly, validation, staging write

**Files:**
- Create: `pmao/deep.py`
- Test: `tests/test_deep.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_deep.py`:

```python
import json
import tempfile
from datetime import date

from pmao.models import Initiative


def _make_initiative(id_="init-001", name="Pricing"):
    return Initiative(id=id_, name=name, status="in_progress",
                      created=date(2026, 6, 1), last_touched=date(2026, 6, 10))


def test_build_deep_prompt_fills_all_placeholders():
    from pmao.deep import _build_deep_prompt
    skill = SKILL_PATH.read_text(encoding="utf-8")
    prompt = _build_deep_prompt(
        skill, [_make_initiative()],
        roster_text="- Sarah Klein | owns: finance",
        recon_text="none",
        calibration_text="No prior calibration.",
        source_text="MEETING TEXT HERE",
    )
    for ph in PLACEHOLDERS:
        assert ph not in prompt, f"unfilled placeholder {ph}"
    assert "init-001: Pricing (status: in_progress)" in prompt
    assert "Sarah Klein" in prompt
    assert "MEETING TEXT HERE" in prompt


def test_reconciliation_block_filters_and_caps():
    from pathlib import Path
    from pmao.deep import _reconciliation_block, RECON_DECISION_CAP
    from pmao.vault import init_vault
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        actions = [
            {"id": "act-1", "description": "open one", "owner": "Dev Patel", "due": "", "status": "open"},
            {"id": "act-2", "description": "closed one", "owner": "Dev Patel", "due": "", "status": "done"},
        ]
        (vault / "actions.json").write_text(json.dumps(actions))
        decisions = [{"id": f"dec-{i}", "decision": f"decision {i}"} for i in range(30)]
        (vault / "decisions.json").write_text(json.dumps(decisions))

        block = _reconciliation_block(vault)
        assert "act-1: open one" in block
        assert "closed one" not in block
        assert "dec-29" in block          # newest kept
        assert "dec-0:" not in block      # oldest dropped by the cap
        assert block.count("dec-") == RECON_DECISION_CAP


def test_reconciliation_block_empty_says_none():
    from pathlib import Path
    from pmao.deep import _reconciliation_block
    from pmao.vault import init_vault
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        assert _reconciliation_block(vault) == "none"


def test_calibration_block_absent_and_capped():
    from pathlib import Path
    from pmao.deep import _calibration_block, CALIBRATION_LINE_CAP
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        assert _calibration_block(vault) == "No prior calibration."
        (vault / "learning").mkdir()
        lines = [f"lesson {i}" for i in range(300)]
        (vault / "learning" / "calibration.md").write_text("\n".join(lines))
        block = _calibration_block(vault)
        assert "lesson 299" in block      # newest kept
        assert "lesson 0\n" not in block  # oldest dropped
        assert len(block.splitlines()) == CALIBRATION_LINE_CAP


def test_validate_extraction_flags_unknown_initiative_and_keeps_item():
    from pmao.deep import _validate_extraction
    extraction = {
        "facts": [{"initiative_id": "init-999", "claim": "orphan claim"}],
        "hypotheses": [{"initiative_id": None, "theory": "project-level ok"}],
        "action_items": [{"initiative_id": "general", "description": "general ok"}],
    }
    out = _validate_extraction(extraction, [_make_initiative()])
    assert len(out["facts"]) == 1                      # kept, never dropped
    assert out["decisions"] == []                      # missing keys defaulted
    assert out["meetings_to_schedule"] == []
    flags = out["review_flags"]
    assert any("init-999" in f for f in flags)
    assert not any("general" in f for f in flags)
    assert len(flags) == 1                             # null and "general" not flagged


def test_write_staging_shape_and_collision_suffix():
    from pathlib import Path
    from pmao.deep import _write_staging, PROMPT_VERSION
    from pmao.vault import init_vault
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        extraction = {"facts": [{"initiative_id": "general", "claim": "x"}]}
        p1 = _write_staging(vault, extraction, "Pricing Sync.vtt")
        p2 = _write_staging(vault, extraction, "Pricing Sync.vtt")
        assert p1.name == f"{date.today().isoformat()}-pricing-sync.json"
        assert p2.name == f"{date.today().isoformat()}-pricing-sync-2.json"
        staged = json.loads(p1.read_text())
        assert staged["status"] == "pending_review"
        assert staged["source"] == "Pricing Sync.vtt"
        assert staged["prompt_version"] == PROMPT_VERSION
        assert staged["extraction"] == extraction       # stored verbatim
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deep.py -v`
Expected: skill-file tests pass; new tests FAIL with `ModuleNotFoundError: No module named 'pmao.deep'`

- [ ] **Step 3: Implement**

Create `pmao/deep.py`:

```python
import json
import re
from datetime import date
from pathlib import Path
from typing import List

from pmao.models import Initiative
from pmao.vault import load_initiatives, load_list, refresh_workbook
from pmao.roster import load_roster, render_roster

PROMPT_VERSION = "pmao-deep-v1.0"
CALIBRATION_LINE_CAP = 200
RECON_DECISION_CAP = 20

# category -> the key that summarizes one item of that category
ITEM_CATEGORIES = {
    "facts": "claim",
    "hypotheses": "theory",
    "decisions": "decision",
    "open_questions": "question",
    "principal_signals": "signal",
    "meetings_to_schedule": "purpose",
    "action_items": "description",
}


def _build_deep_prompt(
    skill: str,
    initiatives: List[Initiative],
    roster_text: str,
    recon_text: str,
    calibration_text: str,
    source_text: str,
) -> str:
    init_list = "\n".join(
        f"  {i.id}: {i.name} (status: {i.status})" for i in initiatives
    )
    return (
        skill
        .replace("{initiatives}", init_list)
        .replace("{roster}", roster_text)
        .replace("{reconciliation_candidates}", recon_text)
        .replace("{calibration}", calibration_text)
        .replace("{source}", source_text)
    )


def _reconciliation_block(vault_path: Path) -> str:
    """Open actions + the newest RECON_DECISION_CAP decisions, one per line with ids."""
    actions = [a for a in load_list(vault_path, "actions.json") if a.get("status") == "open"]
    decisions = load_list(vault_path, "decisions.json")[-RECON_DECISION_CAP:]
    lines = []
    for a in actions:
        due = a.get("due") or "no due date"
        lines.append(f"{a['id']}: {a['description']} (owner: {a.get('owner', '?')}, due: {due})")
    for d in decisions:
        lines.append(f"{d['id']}: {d['decision']}")
    return "\n".join(lines) if lines else "none"


def _calibration_block(vault_path: Path) -> str:
    """Last CALIBRATION_LINE_CAP lines of learning/calibration.md (newest lessons win)."""
    cal_path = vault_path / "learning" / "calibration.md"
    if not cal_path.exists():
        return "No prior calibration."
    lines = cal_path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[-CALIBRATION_LINE_CAP:])


def _validate_extraction(extraction: dict, initiatives: List[Initiative]) -> dict:
    """Default missing keys; flag (never drop) unknown initiative ids — recall over precision."""
    for key in ITEM_CATEGORIES:
        extraction.setdefault(key, [])
    extraction.setdefault("alias_flags", [])
    extraction.setdefault("review_flags", [])
    extraction.setdefault("discard_note", "")
    known = {i.id for i in initiatives}
    for category, summary_key in ITEM_CATEGORIES.items():
        for item in extraction[category]:
            iid = item.get("initiative_id")
            if iid is not None and iid != "general" and iid not in known:
                extraction["review_flags"].append(
                    f"unknown initiative_id '{iid}' on {category}: "
                    f"{str(item.get(summary_key, ''))[:80]}"
                )
    return extraction


def _slugify(name: str) -> str:
    stem = Path(name).stem.lower()
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "source"


def _write_staging(vault_path: Path, extraction: dict, source_name: str) -> Path:
    staging_dir = vault_path / "staging"
    staging_dir.mkdir(exist_ok=True)
    base = f"{date.today().isoformat()}-{_slugify(source_name)}"
    target = staging_dir / f"{base}.json"
    suffix = 2
    while target.exists():
        target = staging_dir / f"{base}-{suffix}.json"
        suffix += 1
    target.write_text(json.dumps({
        "status": "pending_review",
        "ingested": date.today().isoformat(),
        "source": source_name,
        "prompt_version": PROMPT_VERSION,
        "extraction": extraction,
    }, indent=2))
    return target
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_deep.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add pmao/deep.py tests/test_deep.py
git commit -m "feat: deep module — prompt assembly, reconciliation/calibration blocks, validation, staging write"
```

---

### Task 7: `run_ingest_deep` + CLI `--deep` flag

**Files:**
- Modify: `pmao/deep.py` (add `run_ingest_deep`)
- Modify: `pmao/cli.py` (`cmd_ingest`, ingest parser)
- Test: `tests/test_deep.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_deep.py`:

```python
EXTRACTION_FIXTURE = {
    "meta": {"meeting_slug": "2026-06-10-sync", "prompt_version": "pmao-deep-v1.0", "chunk": "1/1"},
    "facts": [{"initiative_id": "init-001", "claim": "cost up 9%", "stated_by": "Sarah Klein",
               "authority": "owner", "confidence": "high", "inferred": False, "source_span": "l12"}],
    "action_items": [{"initiative_id": "init-001", "type": "analysis_required",
                      "description": "build the cost model", "owner": "Dev Patel",
                      "owner_resolution": "alias_merged", "due": "unspecified", "source_span": "l40"}],
    "alias_flags": [{"variants": ["Dev"], "resolved_to": "Dev Patel", "confidence": "high", "needs_review": True}],
    "review_flags": ["near-discard: vague SLA aside"],
    "discard_note": "Discarded ~80%: logistics",
}


def _deep_vault(tmp):
    from pathlib import Path
    from pmao.vault import init_vault, save_initiatives
    vault = Path(tmp)
    init_vault(vault)
    save_initiatives(vault, [_make_initiative()])
    return vault


def test_run_ingest_deep_stages_without_touching_canonical(capsys):
    from unittest.mock import patch
    from openpyxl import load_workbook
    from pmao.deep import run_ingest_deep
    with tempfile.TemporaryDirectory() as tmp:
        vault = _deep_vault(tmp)
        source = vault / "transcripts" / "sync.txt"
        source.write_text("Sarah: cost up 9%. Dev, build the model.")

        with patch("pmao.llm.call_structured", return_value=dict(EXTRACTION_FIXTURE)) as mock:
            run_ingest_deep(vault, source)

        # Prompt was fully assembled (no leftover placeholders)
        prompt = mock.call_args[0][0]
        for ph in PLACEHOLDERS:
            assert ph not in prompt

        # Staged file exists with verbatim extraction
        staged_files = list((vault / "staging").glob("*.json"))
        assert len(staged_files) == 1
        staged = json.loads(staged_files[0].read_text())
        assert staged["status"] == "pending_review"
        assert staged["extraction"]["facts"][0]["claim"] == "cost up 9%"

        # Canonical files untouched
        assert json.loads((vault / "actions.json").read_text()) == []
        assert json.loads((vault / "facts.json").read_text()) == []

        # Workbook Review Queue reflects staging
        wb = load_workbook(vault / "workbook.xlsx")
        queue = [wb["Review Queue"].cell(row=r, column=4).value for r in (2, 3, 4)]
        assert "cost up 9%" in queue
        assert "build the cost model" in queue

        out = capsys.readouterr().out
        assert "staged, not applied" in out
        assert "near-discard: vague SLA aside" in out
        assert "pmao review" in out


def test_run_ingest_deep_empty_extraction_stages_nothing(capsys):
    from unittest.mock import patch
    from pmao.deep import run_ingest_deep
    with tempfile.TemporaryDirectory() as tmp:
        vault = _deep_vault(tmp)
        source = vault / "transcripts" / "sync.txt"
        source.write_text("nothing of substance")
        with patch("pmao.llm.call_structured", return_value={}):
            run_ingest_deep(vault, source)
        assert list((vault / "staging").glob("*.json")) == []
        assert "Nothing extracted" in capsys.readouterr().out


def test_run_ingest_deep_warns_when_roster_missing(capsys):
    from unittest.mock import patch
    from pmao.deep import run_ingest_deep
    with tempfile.TemporaryDirectory() as tmp:
        vault = _deep_vault(tmp)  # no roster.yaml written
        source = vault / "transcripts" / "sync.txt"
        source.write_text("text")
        with patch("pmao.llm.call_structured", return_value={}):
            run_ingest_deep(vault, source)
        assert "no roster.yaml" in capsys.readouterr().out


def test_cli_ingest_deep_flag_dispatches():
    import sys
    from unittest.mock import patch
    from pmao.cli import main
    with patch("pmao.deep.run_ingest_deep") as mock_deep, \
         patch.object(sys, "argv", ["pmao", "ingest", "v/", "--source", "s.txt", "--deep"]):
        main()
    mock_deep.assert_called_once()
    kwargs = mock_deep.call_args.kwargs
    assert str(kwargs["vault_path"]) == "v"
    assert str(kwargs["source_path"]) == "s.txt"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deep.py -v -k "run_ingest_deep or deep_flag"`
Expected: FAIL with `ImportError: cannot import name 'run_ingest_deep'`

- [ ] **Step 3: Implement `run_ingest_deep`**

Append to `pmao/deep.py`:

```python
def run_ingest_deep(vault_path: Path, source_path: Path, config_override: str = None) -> None:
    from pmao.transcript import preprocess_transcript
    from pmao import llm
    from pmao.ingest import _load_skill

    print(f"Preprocessing {source_path.name}...")
    text = preprocess_transcript(source_path)

    initiatives = load_initiatives(vault_path)
    people = load_roster(vault_path)
    if people is None:
        print("Warning: no roster.yaml found — authority will be 'unknown' and principal signals will be empty.")

    skill = _load_skill("ingest-deep")
    prompt = _build_deep_prompt(
        skill,
        initiatives,
        roster_text=render_roster(people),
        recon_text=_reconciliation_block(vault_path),
        calibration_text=_calibration_block(vault_path),
        source_text=text,
    )

    print("Calling LLM for deep extraction (this may take ~60s)...")
    extraction = llm.call_structured(prompt, config_override=config_override)
    extraction = _validate_extraction(extraction, initiatives)

    counts = {cat: len(extraction[cat]) for cat in ITEM_CATEGORIES}
    print("\n--- Deep extraction results (staged, not applied) ---")
    for cat, n in counts.items():
        print(f"  {cat}: {n}")
    if extraction["discard_note"]:
        print(f"  discard_note: {extraction['discard_note']}")
    if extraction["alias_flags"]:
        print("\nAlias flags:")
        for a in extraction["alias_flags"]:
            variants = " / ".join(a.get("variants", []))
            print(f"  {variants} -> {a.get('resolved_to', '?')} ({a.get('confidence', '?')})")
    if extraction["review_flags"]:
        print("\nReview flags:")
        for flag in extraction["review_flags"]:
            print(f"  - {flag}")

    if not any(counts.values()):
        print("\nNothing extracted — nothing staged.")
        return

    staged_path = _write_staging(vault_path, extraction, source_path.name)
    refresh_workbook(vault_path)
    print(f"\nStaged for review: staging/{staged_path.name}. Run 'pmao review' to promote.")
```

Note the `from pmao import llm` + `llm.call_structured(...)` form — required so the tests' `patch("pmao.llm.call_structured")` intercepts the call.

- [ ] **Step 4: Wire the CLI**

In `pmao/cli.py`, replace `cmd_ingest`:

```python
def cmd_ingest(args) -> None:
    if args.deep:
        from pmao.deep import run_ingest_deep
        run_ingest_deep(vault_path=Path(args.vault), source_path=Path(args.source), config_override=args.backend)
    else:
        from pmao.ingest import run_ingest
        run_ingest(vault_path=Path(args.vault), source_path=Path(args.source), yes=args.yes, config_override=args.backend)
```

In `main()`, after the `--yes` argument on the ingest parser, add:

```python
    p_ingest.add_argument("--deep", action="store_true",
                          help="Rich extraction staged for review (no direct apply)")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_deep.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add pmao/deep.py pmao/cli.py tests/test_deep.py
git commit -m "feat: pmao ingest --deep — staged rich extraction end to end"
```

---

### Task 8: README, full regression, smoke test

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README.md**

In the Commands table, replace the ingest row with two rows:

```markdown
| `pmao ingest <vault> --source FILE [--yes]` | Quick extract: updates applied directly after confirmation |
| `pmao ingest <vault> --source FILE --deep` | Deep extract: facts, signals, meetings, typed actions — staged to `staging/` for review (never applies directly) |
```

In the Vault structure block, replace the `transcripts/` line and what's above it so the block ends:

```
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

Add a new section before "## LLM backend":

```markdown
## Deep ingest and the roster

`pmao ingest --deep` runs a richer extraction (facts, hypotheses, decisions, open questions, principal signals, meetings to schedule, typed action items, alias/review flags) and writes the result to `staging/` — canonical files are only changed when a human promotes items via the review gate (`pmao review`, upcoming).

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

The skill lives at `skills/ingest-deep.md`; edit it to change extraction behavior, no Python required.
```

In the Skill files table, add:

```markdown
| `skills/ingest-deep.md` | `pmao ingest --deep` — staged rich extraction |
```

- [ ] **Step 2: Full regression**

Run: `python -m pytest tests/ -v`
Expected: all tests pass, including untouched `tests/test_ingest.py`, `tests/test_llm.py`, `tests/test_transcript.py`, `tests/test_models.py`

- [ ] **Step 3: Manual smoke test (no LLM call)**

```bash
cd /tmp && rm -rf smoke-vault
printf 'Smoke\n\n' | python -c "
from pathlib import Path
from pmao.vault import init_vault
init_vault(Path('/tmp/smoke-vault'), project_name='Smoke', owner='me')
print(sorted(p.name for p in Path('/tmp/smoke-vault').iterdir()))
"
python -m pmao.cli ingest /tmp/smoke-vault --source missing.txt --deep || true
```

Expected: first command lists `staging`, `facts.json`, `signals.json`, `meetings.json` among vault contents; second prints a clean `Error: ...` for the missing source (argparse + error handling path works with `--deep`).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document deep ingest, roster.yaml, staging in README"
```

---

## Self-review checklist (run after writing, before handoff)

- **Spec coverage:** roster (T1), staging dir + canonical files (T2), four workbook tabs incl. combined Meetings (T3), Review Queue from staging + shared regen incl. quick-ingest path (T4), adapted skill with five placeholders / initiative_id / unified roster / no chunking / calibration / prompt_version (T5), reconciliation cap + calibration cap + unknown-id flagging + verbatim staging + collision suffix (T6), CLI flow with warnings, empty-extraction skip, summary output, no direct apply (T7), README + regression (T8). Promotion/gate, `learning/` writes, syndication: out of scope per spec.
- **Type consistency:** `load_list(vault_path, filename)` used identically in vault/deep; `create_workbook` kwargs (`facts`, `signals`, `meetings`, `staged`) match between excel.py, `refresh_workbook`, and tests; `_load_skill("ingest-deep")` matches the filename `skills/ingest-deep.md`; `run_ingest_deep(vault_path=, source_path=, config_override=)` matches the CLI call.
- **Spec deviation (intentional, minor):** spec's Review Queue table lists a "flags" column; the plan instead emits each review_flag as its own row (category `review_flag`) — cleaner than repeating file-level flags on every item row. Noted here so the reviewer of Spec 2 isn't surprised.

