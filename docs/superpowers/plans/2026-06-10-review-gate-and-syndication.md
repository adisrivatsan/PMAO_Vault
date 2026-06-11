# Review Gate + Syndication Implementation Plan (Specs 2 & 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build `pmao review` (human gate: verdicts → promotion → learning) and `pmao syndicate` (stakeholder pathway + cadence proposals staged through the gate).

**Architecture:** New `pmao/review.py` (promotion core + interactive loop, NO LLM) and `pmao/syndicate.py` + `skills/syndicate.md` (LLM pathway recommendation reusing Spec 1's staging writer). Small changes: deep-ingest flags-only staging fix, `cadence` column on Meetings tab, two CLI subcommands.

**Tech Stack:** Python 3.9 (`python3` on PATH — plain `python` does not exist), pyyaml, openpyxl, pytest. Repo: `PMAO GITHUB/pmao-cli`. Specs: `../docs/superpowers/specs/2026-06-10-review-gate-design.md` and `2026-06-10-syndication-design.md`.

---

## File map

| File | Action | Responsibility |
|------|--------|----------------|
| `pmao/review.py` | Create | ID minting, category→record mapping, `promote_extraction`, derived `outstanding_meetings`, learning writers, interactive `run_review` |
| `pmao/syndicate.py` | Create | History/signals blocks, prompt assembly, `run_syndicate` |
| `skills/syndicate.md` | Create | Syndication LLM prompt (4 placeholders) |
| `pmao/deep.py` | Modify | Flags-only staging fix |
| `pmao/excel.py` | Modify | `cadence` column in MEETING_COLS |
| `pmao/cli.py` | Modify | `review` + `syndicate` subcommands |
| `README.md` | Modify | Document both commands + learning/ + cadence |
| `tests/test_review.py` | Create | Promotion + learning + interactive-loop tests |
| `tests/test_syndicate.py` | Create | Syndication tests |
| `tests/test_deep.py` | Modify | Flags-only staging test |
| `tests/test_excel.py` | Modify | Cadence column (update combined-meetings test) |

---

### Task 1: Promotion core + learning writers (`pmao/review.py`, part 1)

**Files:** Create `pmao/review.py`; Test: create `tests/test_review.py`

- [ ] **Step 1: Write the failing tests** — create `tests/test_review.py`:

```python
import json
import tempfile
from datetime import date
from pathlib import Path

from pmao.models import Initiative
from pmao.vault import init_vault, save_initiatives, load_initiatives, load_list


def _vault(tmp, initiative_id="init-001"):
    vault = Path(tmp)
    init_vault(vault)
    save_initiatives(vault, [Initiative(
        id=initiative_id, name="Pricing", status="in_progress",
        created=date(2026, 6, 1), last_touched=date(2026, 6, 1))])
    return vault


def test_promote_each_category_mints_ids_and_maps_fields():
    from pmao.review import promote_extraction
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        today = date.today().isoformat()
        approved = [
            {"category": "facts", "verdict": "approved",
             "item": {"initiative_id": "init-001", "claim": "cost up 9%", "stated_by": "Sarah Klein",
                      "authority": "owner", "confidence": "high", "inferred": False, "source_span": "l12"}},
            {"category": "hypotheses", "verdict": "promoted",
             "item": {"initiative_id": None, "theory": "margins fine", "held_by": "PM", "source_span": "l20"}},
            {"category": "hypotheses", "verdict": "kept",
             "item": {"initiative_id": "init-001", "theory": "bundling wins", "held_by": "PM",
                      "would_confirm": "pilot data", "source_span": "l22"}},
            {"category": "decisions", "verdict": "approved",
             "item": {"initiative_id": "init-001", "decision": "go with v2", "decided_by": "Sarah Klein",
                      "context": "cheaper", "source_span": "l30"}},
            {"category": "open_questions", "verdict": "approved",
             "item": {"initiative_id": "general", "question": "who owns legal?", "source_span": "l33"}},
            {"category": "principal_signals", "verdict": "approved",
             "item": {"initiative_id": "init-001", "principal": "Sarah Klein", "lever": "pricing",
                      "signal": "wants floor", "implication": "raise floor", "source_span": "l40"}},
            {"category": "meetings_to_schedule", "verdict": "approved",
             "item": {"initiative_id": "init-001", "purpose": "align on cost model", "convener": "Sarah Klein",
                      "attendees": ["Finance"], "functions": ["finance"], "target_timing": "next week",
                      "cadence": "one-time", "source_span": "l50"}},
            {"category": "action_items", "verdict": "approved",
             "item": {"initiative_id": "init-001", "description": "build model", "owner": "Dev Patel",
                      "type": "analysis_required", "due": "unspecified", "source_span": "l60"}},
        ]
        minted = promote_extraction(vault, approved, source="sync.vtt")
        assert len(minted) == 8

        facts = load_list(vault, "facts.json")
        assert len(facts) == 2  # fact + promoted hypothesis
        assert facts[0]["id"] == f"fact-{today}-0000"
        assert facts[0]["claim"] == "cost up 9%"
        assert facts[1]["claim"] == "margins fine"
        assert facts[1]["confidence"] == "high"      # human-validated
        assert facts[1]["authority"] == "unknown"

        hyps = load_list(vault, "hypotheses.json")
        assert len(hyps) == 1 and hyps[0]["hypothesis"] == "bundling wins"
        assert hyps[0]["validation_path"] == "pilot data"

        decs = load_list(vault, "decisions.json")
        assert decs[0]["rationale"] == "cheaper" and decs[0]["owner"] == "Sarah Klein"

        qs = load_list(vault, "questions.json")
        assert qs[0]["initiative_id"] == "general"

        sigs = load_list(vault, "signals.json")
        assert sigs[0]["lever"] == "pricing"

        mtgs = load_list(vault, "meetings.json")
        assert mtgs[0]["id"].startswith("mtg-") and mtgs[0]["status"] == "open"
        assert mtgs[0]["cadence"] == "one-time"

        acts = load_list(vault, "actions.json")
        assert acts[0]["type"] == "analysis_required"
        assert acts[0]["due"] == ""                   # unspecified normalized

        # Initiative side-effects: last_touched + derived outstanding_meetings
        init = load_initiatives(vault)[0]
        assert init.last_touched == date.today()
        assert "align on cost model" in init.outstanding_meetings
        assert "(next week)" in init.outstanding_meetings


def test_promote_merge_updates_existing_action_instead_of_creating():
    from pmao.review import promote_extraction
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        (vault / "actions.json").write_text(json.dumps([
            {"id": "act-old-0000", "initiative_id": "init-001", "description": "build model",
             "owner": "Dev Patel", "due": "", "status": "open"}]))
        approved = [{"category": "action_items", "verdict": "merged", "merged_into": "act-old-0000",
                     "item": {"initiative_id": "init-001", "description": "build the cost model v2",
                              "owner": "Dev Patel", "due": "2026-06-20"}}]
        promote_extraction(vault, approved, source="sync.vtt")
        acts = load_list(vault, "actions.json")
        assert len(acts) == 1
        assert "[updated: build the cost model v2]" in acts[0]["description"]
        assert acts[0]["due"] == "2026-06-20"


def test_outstanding_meetings_only_regenerated_when_meetings_promoted():
    from pmao.review import promote_extraction
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        inits = load_initiatives(vault)
        inits[0].outstanding_meetings = "- preexisting free text"
        save_initiatives(vault, inits)
        approved = [{"category": "facts", "verdict": "approved",
                     "item": {"initiative_id": "init-001", "claim": "x", "stated_by": "", "source_span": "l1"}}]
        promote_extraction(vault, approved, source="s.vtt")
        init = load_initiatives(vault)[0]
        assert init.outstanding_meetings == "- preexisting free text"  # untouched
        assert init.last_touched == date.today()


def test_learning_writers_append_and_cap():
    from pmao.review import append_verdict, append_calibration, CALIBRATION_MAX_LINES
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        append_verdict(vault, {"verdict": "approved", "category": "facts", "summary": "x"})
        append_verdict(vault, {"verdict": "rejected", "category": "facts", "summary": "y"})
        lines = (vault / "learning" / "verdicts.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2 and json.loads(lines[1])["verdict"] == "rejected"

        for i in range(CALIBRATION_MAX_LINES + 50):
            append_calibration(vault, f"lesson {i}")
        cal_lines = (vault / "learning" / "calibration.md").read_text().strip().splitlines()
        assert len(cal_lines) == CALIBRATION_MAX_LINES
        assert f"lesson {CALIBRATION_MAX_LINES + 49}" in cal_lines[-1]   # newest kept
        assert not any("lesson 0 " in ln or ln.endswith("lesson 0") for ln in cal_lines)
```

- [ ] **Step 2:** `python3 -m pytest tests/test_review.py -v` → FAIL (no module pmao.review)

- [ ] **Step 3: Create `pmao/review.py`:**

```python
import json
from datetime import date
from pathlib import Path
from typing import List, Optional

from pmao.vault import (
    load_initiatives, save_initiatives, load_list,
    refresh_workbook, STAGED_CATEGORIES,
)

CALIBRATION_MAX_LINES = 500


class _Quit(Exception):
    """User quit mid-file — discard this file's verdicts."""


# ── Promotion core ─────────────────────────────────────────────────────────────

def _record_for(category: str, item: dict, source: str, verdict: str):
    """Map a staged item to (canonical filename, id prefix, record dict without id)."""
    today = date.today().isoformat()
    base = {"initiative_id": item.get("initiative_id"), "source": source, "created": today}
    if category == "facts":
        return "facts.json", "fact", dict(base,
            claim=item.get("claim", ""), stated_by=item.get("stated_by", ""),
            authority=item.get("authority", "unknown"), confidence=item.get("confidence", "med"),
            inferred=bool(item.get("inferred", False)), source_span=item.get("source_span", ""))
    if category == "hypotheses" and verdict == "promoted":
        return "facts.json", "fact", dict(base,
            claim=item.get("theory", ""), stated_by=item.get("held_by", ""),
            authority="unknown", confidence="high", inferred=False,
            source_span=item.get("source_span", ""))
    if category == "hypotheses":  # kept
        return "hypotheses.json", "hyp", dict(base,
            hypothesis=item.get("theory", ""), owner=item.get("held_by", ""),
            validation_path=item.get("would_confirm", ""), status="open",
            source_type="[transcript]")
    if category == "decisions":
        return "decisions.json", "dec", dict(base,
            decision=item.get("decision", ""), rationale=item.get("context", ""),
            owner=item.get("decided_by", ""), status="recorded", source_type="[transcript]")
    if category == "open_questions":
        return "questions.json", "q", dict(base,
            question=item.get("question", ""), status="open")
    if category == "principal_signals":
        return "signals.json", "sig", dict(base,
            principal=item.get("principal", ""), lever=item.get("lever", ""),
            signal=item.get("signal", ""), implication=item.get("implication", ""),
            source_span=item.get("source_span", ""))
    if category == "meetings_to_schedule":
        return "meetings.json", "mtg", dict(base,
            purpose=item.get("purpose", ""), convener=item.get("convener"),
            attendees=item.get("attendees") or [], functions=item.get("functions") or [],
            target_timing=item.get("target_timing", ""), cadence=item.get("cadence", ""),
            status="open")
    if category == "action_items":
        due = item.get("due", "")
        return "actions.json", "act", dict(base,
            description=item.get("description", ""), owner=item.get("owner") or "",
            type=item.get("type", ""), due="" if due == "unspecified" else due,
            status="open")
    raise ValueError(f"unknown category: {category}")


def _mint_id(prefix: str, records: list) -> str:
    return f"{prefix}-{date.today().isoformat()}-{len(records):04d}"


def _apply_merge(records: list, entry: dict) -> None:
    """Fold an approved action item into the existing open action it matched."""
    target = next((r for r in records if r.get("id") == entry["merged_into"]), None)
    if target is None:
        return
    new_desc = entry["item"].get("description", "")
    if new_desc:
        target["description"] = f"{target.get('description', '')} [updated: {new_desc}]"
    new_due = entry["item"].get("due", "")
    if new_due and new_due != "unspecified":
        target["due"] = new_due


def promote_extraction(vault_path: Path, approved: List[dict], source: str) -> List[str]:
    """Write all approved items for one staging file. Returns minted ids.

    approved entries: {"category", "item", "verdict", optional "merged_into"}.
    Merges are supported for action_items; other merged categories are skipped
    (the verdict log records the match).
    """
    by_file = {}
    touched, meeting_touched = set(), set()
    minted = []
    for entry in approved:
        iid = entry["item"].get("initiative_id")
        if iid and iid != "general":
            touched.add(iid)
        if entry.get("merged_into"):
            if entry["category"] == "action_items":
                records = by_file.setdefault("actions.json", load_list(vault_path, "actions.json"))
                _apply_merge(records, entry)
            continue
        fname, prefix, rec = _record_for(entry["category"], entry["item"], source, entry["verdict"])
        records = by_file.setdefault(fname, load_list(vault_path, fname))
        rec_id = _mint_id(prefix, records)
        records.append(dict({"id": rec_id}, **rec))
        minted.append(rec_id)
        if fname == "meetings.json" and iid and iid != "general":
            meeting_touched.add(iid)
    for fname, records in by_file.items():
        (vault_path / fname).write_text(json.dumps(records, indent=2))

    if touched:
        initiatives = load_initiatives(vault_path)
        meetings = load_list(vault_path, "meetings.json")
        for init in initiatives:
            if init.id in touched:
                init.last_touched = date.today()
            if init.id in meeting_touched:
                open_mtgs = [m for m in meetings
                             if m.get("initiative_id") == init.id and m.get("status") == "open"]
                init.outstanding_meetings = "\n".join(
                    f"- {m.get('purpose', '')} ({m.get('target_timing') or 'unscheduled'})"
                    for m in open_mtgs)
        save_initiatives(vault_path, initiatives)
    return minted


# ── Learning writers ───────────────────────────────────────────────────────────

def append_verdict(vault_path: Path, record: dict) -> None:
    learning = vault_path / "learning"
    learning.mkdir(exist_ok=True)
    with open(learning / "verdicts.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def append_calibration(vault_path: Path, lesson: str) -> None:
    learning = vault_path / "learning"
    learning.mkdir(exist_ok=True)
    cal = learning / "calibration.md"
    lines = cal.read_text(encoding="utf-8").splitlines() if cal.exists() else []
    lines.append(f"- {date.today().isoformat()} {lesson}")
    cal.write_text("\n".join(lines[-CALIBRATION_MAX_LINES:]) + "\n", encoding="utf-8")
```

- [ ] **Step 4:** `python3 -m pytest tests/test_review.py -v` → 4 passed; full suite green.
- [ ] **Step 5: Commit** `feat: review promotion core — category mapping, ID minting, merges, derived fields, learning writers`

---

### Task 2: Interactive review loop + CLI (`pmao/review.py`, part 2)

**Files:** Modify `pmao/review.py` (append), `pmao/cli.py`; Test: append to `tests/test_review.py`

- [ ] **Step 1: Append tests** to `tests/test_review.py`:

```python
def _staged_file(vault, extraction, name="2026-06-10-sync.json", status="pending_review"):
    payload = {"status": status, "ingested": "2026-06-10", "source": "sync.vtt",
               "prompt_version": "pmao-deep-v1.1", "extraction": extraction}
    (vault / "staging" / name).write_text(json.dumps(payload))
    return vault / "staging" / name


def _run_with_inputs(monkeypatch, answers, fn, *args):
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))
    fn(*args)


def test_run_review_approve_reject_and_hypothesis_verdicts(monkeypatch, capsys):
    from pmao.review import run_review
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        staged = _staged_file(vault, {
            "facts": [{"initiative_id": "init-001", "claim": "cost up 9%", "stated_by": "Sarah Klein",
                       "authority": "owner", "confidence": "high", "inferred": False, "source_span": "l1"}],
            "hypotheses": [{"initiative_id": "init-001", "theory": "bundling wins", "held_by": "PM",
                            "would_confirm": "pilot", "source_span": "l2"}],
            "action_items": [{"initiative_id": "init-001", "description": "junk item", "owner": "",
                              "type": "communication", "due": "", "source_span": "l3"}],
            "alias_flags": [{"variants": ["Dev"], "resolved_to": "Dev Patel", "confidence": "high",
                             "needs_review": True}],
            "review_flags": ["near-discard: vague SLA aside"],
        })
        # answers: alias confirm, fact approve, hypothesis keep, action reject, flag accept-drop
        _run_with_inputs(monkeypatch, ["y", "a", "k", "r", ""], run_review, vault)

        assert len(load_list(vault, "facts.json")) == 1
        assert len(load_list(vault, "hypotheses.json")) == 1
        assert load_list(vault, "actions.json") == []          # rejected
        assert json.loads(staged.read_text())["status"] == "reviewed"

        verdicts = [json.loads(l) for l in
                    (vault / "learning" / "verdicts.jsonl").read_text().strip().splitlines()]
        kinds = {v["verdict"] for v in verdicts}
        assert {"alias_confirmed", "approved", "kept", "rejected", "flag_acknowledged"} <= kinds

        cal = (vault / "learning" / "calibration.md").read_text()
        assert 'alias: "Dev" → "Dev Patel" (confirmed)' in cal
        assert "boundary: rejected action_items" in cal


def test_run_review_edit_changes_fields(monkeypatch):
    from pmao.review import run_review
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        _staged_file(vault, {
            "action_items": [{"initiative_id": "general", "description": "build model",
                              "owner": "", "type": "analysis_required", "due": "", "source_span": "l1"}],
        })
        # edit: initiative_id -> init-001, owner -> Dev Patel, description kept (empty input)
        _run_with_inputs(monkeypatch, ["e", "init-001", "Dev Patel", ""], run_review, vault)
        acts = load_list(vault, "actions.json")
        assert acts[0]["initiative_id"] == "init-001"
        assert acts[0]["owner"] == "Dev Patel"
        assert acts[0]["description"] == "build model"


def test_run_review_merge_into_reconciliation_candidate(monkeypatch):
    from pmao.review import run_review
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        (vault / "actions.json").write_text(json.dumps([
            {"id": "act-old-0000", "initiative_id": "init-001", "description": "build model",
             "owner": "Dev Patel", "due": "", "status": "open"}]))
        _staged_file(vault, {
            "action_items": [{"initiative_id": "init-001", "description": "build model v2",
                              "owner": "Dev Patel", "type": "analysis_required", "due": "",
                              "source_span": "l1",
                              "reconciliation_candidates": [
                                  {"existing": "act-old-0000", "match_confidence": "high"}]}],
        })
        # approve, then merge yes
        _run_with_inputs(monkeypatch, ["a", "y"], run_review, vault)
        acts = load_list(vault, "actions.json")
        assert len(acts) == 1
        assert "[updated: build model v2]" in acts[0]["description"]


def test_run_review_quit_discards_current_file(monkeypatch):
    from pmao.review import run_review
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        staged = _staged_file(vault, {
            "facts": [{"initiative_id": "init-001", "claim": "first", "source_span": "l1"},
                      {"initiative_id": "init-001", "claim": "second", "source_span": "l2"}],
        })
        _run_with_inputs(monkeypatch, ["a", "q"], run_review, vault)   # approve one, then quit
        assert load_list(vault, "facts.json") == []                    # nothing promoted
        assert json.loads(staged.read_text())["status"] == "pending_review"


def test_run_review_nothing_pending(capsys):
    from pmao.review import run_review
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        run_review(vault)
        assert "Nothing to review." in capsys.readouterr().out


def test_run_review_skips_corrupt_staging_file(monkeypatch, capsys):
    from pmao.review import run_review
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        (vault / "staging" / "bad.json").write_text("{not json")
        run_review(vault)
        out = capsys.readouterr().out
        assert "bad.json" in out and "Nothing to review." in out


def test_cli_review_dispatches():
    import sys
    from unittest.mock import patch
    from pmao.cli import main
    with patch("pmao.review.run_review") as mock_review, \
         patch.object(sys, "argv", ["pmao", "review", "v/"]):
        main()
    mock_review.assert_called_once()
```

- [ ] **Step 2:** Run → FAIL (`run_review` missing).

- [ ] **Step 3: Append to `pmao/review.py`:**

```python
# ── Interactive gate ───────────────────────────────────────────────────────────

def _ask(prompt: str, choices: str) -> str:
    """Prompt until the answer is one of `choices`. 'q' or EOF/interrupt quits."""
    while True:
        try:
            ans = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise _Quit()
        if ans == "q":
            raise _Quit()
        if ans in choices.split("/"):
            return ans


def _display_item(category: str, item: dict, idx: int, total: int) -> None:
    summary_key = STAGED_CATEGORIES[category]
    print(f"\n[{category} {idx}/{total}] initiative: {item.get('initiative_id') or '(project-level)'}")
    print(f"  {summary_key}: {item.get(summary_key, '')}")
    for k in ("owner", "owner_resolution", "stated_by", "held_by", "decided_by", "authority",
              "confidence", "type", "due", "target_timing", "cadence", "would_confirm", "source_span"):
        if item.get(k):
            print(f"  {k}: {item[k]}")
    for rc in item.get("reconciliation_candidates") or []:
        print(f"  possible match: {rc.get('existing')} ({rc.get('match_confidence')})")


def _edit_item(category: str, item: dict) -> dict:
    """Prompt for initiative_id, owner, and the summary field; empty input keeps current."""
    summary_key = STAGED_CATEGORIES[category]
    edits = {}
    for field in ("initiative_id", "owner", summary_key):
        old = item.get(field) or ""
        try:
            new = input(f"  {field} [{old}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise _Quit()
        if new and new != old:
            edits[field] = [old, new]
            item[field] = new
    return edits


def _review_file(vault_path: Path, staged_path: Path, data: dict) -> None:
    extraction = data.get("extraction", {})
    source = data.get("source", staged_path.name)
    print(f"\n=== Reviewing {staged_path.name} (source: {source}, ingested: {data.get('ingested', '?')}) ===")
    if extraction.get("discard_note"):
        print(f"discard_note: {extraction['discard_note']}")

    approved, verdicts = [], []

    for alias in extraction.get("alias_flags", []):
        variants = " / ".join(alias.get("variants", []))
        print(f"\nAlias: {variants} -> {alias.get('resolved_to')} ({alias.get('confidence')})")
        ans = _ask("  confirm alias? [y/n] ", "y/n")
        verdict = "alias_confirmed" if ans == "y" else "alias_rejected"
        verdicts.append({"category": "alias_flags", "summary": f"{variants} -> {alias.get('resolved_to')}",
                         "verdict": verdict})

    for category, summary_key in STAGED_CATEGORIES.items():
        items = extraction.get(category, [])
        for idx, item in enumerate(items, start=1):
            _display_item(category, item, idx, len(items))
            base = {"category": category, "initiative_id": item.get("initiative_id"),
                    "summary": item.get(summary_key, "")}
            if category == "hypotheses":
                ans = _ask("  [p]romote to fact / [k]eep / [x] kill / [q]uit: ", "p/k/x")
                if ans == "x":
                    verdicts.append(dict(base, verdict="killed"))
                    continue
                verdict = "promoted" if ans == "p" else "kept"
                approved.append({"category": category, "item": item, "verdict": verdict})
                verdicts.append(dict(base, verdict=verdict))
                continue
            ans = _ask("  [a]pprove / [e]dit / [r]eject / [q]uit: ", "a/e/r")
            if ans == "r":
                verdicts.append(dict(base, verdict="rejected"))
                continue
            entry = {"category": category, "item": item, "verdict": "approved"}
            if ans == "e":
                edits = _edit_item(category, item)
                entry["verdict"] = "edited"
                verdicts.append(dict(base, verdict="edited", edited=edits,
                                     summary=item.get(summary_key, "")))
            else:
                verdicts.append(dict(base, verdict="approved"))
            rcs = item.get("reconciliation_candidates") or []
            if rcs:
                ans = _ask(f"  merge into existing {rcs[0].get('existing')}? [y/n] ", "y/n")
                if ans == "y":
                    entry["merged_into"] = rcs[0].get("existing")
                    verdicts[-1]["verdict"] = "merged"
                    verdicts[-1]["merged_into"] = rcs[0].get("existing")
            approved.append(entry)

    for flag in extraction.get("review_flags", []):
        print(f"\nReview flag: {flag}")
        try:
            ans = input("  [enter] accept / [o] overturn (extract similar next time): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise _Quit()
        if ans == "q":
            raise _Quit()
        if ans == "o":
            verdicts.append({"category": "review_flags", "summary": flag, "verdict": "flag_overturned"})
        else:
            verdicts.append({"category": "review_flags", "summary": flag, "verdict": "flag_acknowledged"})

    # ── Commit at file boundary ────────────────────────────────────────────────
    promote_extraction(vault_path, approved, source=source)
    today = date.today().isoformat()
    for v in verdicts:
        append_verdict(vault_path, dict(v, ts=today, staging_file=staged_path.name))
        if v["verdict"] == "alias_confirmed":
            variants, resolved = v["summary"].split(" -> ")
            append_calibration(vault_path, f'alias: "{variants}" → "{resolved}" (confirmed)')
        elif v["verdict"] == "alias_rejected":
            variants, resolved = v["summary"].split(" -> ")
            append_calibration(vault_path, f'alias: "{variants}" → "{resolved}" (REJECTED — do not merge)')
        elif v["verdict"] == "rejected":
            append_calibration(vault_path,
                f'boundary: rejected {v["category"]}: "{v["summary"]}" — do not extract similar')
        elif v["verdict"] == "flag_overturned":
            append_calibration(vault_path,
                f'boundary: near-discard overturned: "{v["summary"]}" — extract similar next time')
    data["status"] = "reviewed"
    data["reviewed"] = today
    staged_path.write_text(json.dumps(data, indent=2))
    refresh_workbook(vault_path)
    print(f"\n{staged_path.name}: reviewed. Promoted {len(approved)} item(s).")


def run_review(vault_path: Path) -> None:
    staging_dir = vault_path / "staging"
    pending = []
    if staging_dir.exists():
        for f in sorted(staging_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
            except json.JSONDecodeError:
                print(f"Warning: skipping corrupt staging file {f.name}")
                continue
            if data.get("status") == "pending_review":
                pending.append((f, data))
    if not pending:
        print("Nothing to review.")
        return
    for f, data in pending:
        try:
            _review_file(vault_path, f, data)
        except _Quit:
            print(f"\nQuit — {f.name} left pending; its verdicts were discarded.")
            return
```

- [ ] **Step 4: Wire CLI** — in `pmao/cli.py` add:

```python
def cmd_review(args) -> None:
    from pmao.review import run_review
    run_review(vault_path=Path(args.vault))
```

and in `main()` after the summarize parser:

```python
    p_review = sub.add_parser("review", help="Review staged deep-ingest extractions and promote")
    p_review.add_argument("vault", help="Path to vault directory")
    p_review.set_defaults(func=cmd_review)
```

- [ ] **Step 5:** `python3 -m pytest tests/ -q` → all green. **Commit** `feat: pmao review — interactive gate with promotion, merges, learning writes`

---

### Task 3: Deep-ingest flags-only staging fix

**Files:** Modify `pmao/deep.py`; Test: append to `tests/test_deep.py`

- [ ] **Step 1: Append test:**

```python
def test_run_ingest_deep_stages_flags_only_extraction(capsys):
    from unittest.mock import patch
    from pmao.deep import run_ingest_deep
    with tempfile.TemporaryDirectory() as tmp:
        vault = _deep_vault(tmp)
        source = vault / "transcripts" / "sync.txt"
        source.write_text("mostly noise")
        with patch("pmao.llm.call_structured",
                   return_value={"review_flags": ["near-discard: vague aside"]}):
            run_ingest_deep(vault, source)
        staged_files = list((vault / "staging").glob("*.json"))
        assert len(staged_files) == 1          # flags alone now stage
        assert "Staged for review" in capsys.readouterr().out
```

- [ ] **Step 2:** FAIL (currently stages nothing).
- [ ] **Step 3:** In `pmao/deep.py` `run_ingest_deep`, change the guard:

```python
    if not any(counts.values()) and not extraction["review_flags"]:
        print("\nNothing extracted — nothing staged.")
        return
```

- [ ] **Step 4:** Full suite green. **Commit** `fix: deep ingest stages flags-only extractions so the gate sees near-discards`

---

### Task 4: Syndication + cadence column

**Files:** Create `skills/syndicate.md`, `pmao/syndicate.py`, `tests/test_syndicate.py`; Modify `pmao/excel.py`, `pmao/cli.py`, `tests/test_excel.py`

- [ ] **Step 1: cadence column.** In `pmao/excel.py` MEETING_COLS, insert `"cadence"` after `"target_timing"`. In the initiative-field row dict in the Meetings tab, add `"cadence": ""`. In `tests/test_excel.py`, update `test_meetings_tab_combines_structured_and_initiative_field`: range becomes `range(1, 12)`, `sources = {row[9] for row in rows}` (row_source shifted by one), and add to the structured meeting dict `"cadence": "biweekly"` plus assertion `assert "biweekly" in {row[7] for row in rows}`.

- [ ] **Step 2: Write failing syndicate tests** — create `tests/test_syndicate.py`:

```python
import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from pmao.models import Initiative
from pmao.vault import init_vault, save_initiatives, load_list

SKILL_PATH = Path(__file__).parent.parent / "skills" / "syndicate.md"
PLACEHOLDERS = ["{initiative}", "{roster}", "{history}", "{signals}"]

SYNDICATE_OUTPUT = {
    "pathway": [{"step": 1, "stakeholders": ["Sarah Klein"], "purpose": "pricing pre-read",
                 "why": "controls pricing lever", "needs": "cost model", "timing": "first"}],
    "meetings_to_schedule": [{
        "initiative_id": "init-001", "purpose": "pricing pre-read with Sarah",
        "convener": "Sarah Klein", "convener_resolution": "matched_roster",
        "attendees": ["Sarah Klein"], "requester": "syndication", "functions": ["finance"],
        "target_timing": "next week", "cadence": "biweekly until pricing review",
        "related_decision": None, "related_question": None, "committee_ownership": False,
        "reconciliation_candidates": [], "source_span": "pathway step 1"}],
    "review_flags": [],
}


def _vault(tmp):
    vault = Path(tmp)
    init_vault(vault)
    save_initiatives(vault, [Initiative(
        id="init-001", name="Pricing", status="in_progress",
        created=date(2026, 6, 1), last_touched=date(2026, 6, 1))])
    return vault


def test_skill_file_has_placeholders():
    text = SKILL_PATH.read_text(encoding="utf-8")
    for ph in PLACEHOLDERS:
        assert ph in text, f"missing {ph}"
    assert "cadence" in text


def test_run_syndicate_stages_proposals(capsys):
    from unittest.mock import patch
    from pmao.syndicate import run_syndicate
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        with patch("pmao.llm.call_structured", return_value=dict(SYNDICATE_OUTPUT)) as mock:
            run_syndicate(vault, "init-001")
        prompt = mock.call_args[0][0]
        for ph in PLACEHOLDERS:
            assert ph not in prompt
        staged_files = list((vault / "staging").glob("*.json"))
        assert len(staged_files) == 1
        assert "syndicate-init-001" in staged_files[0].name
        staged = json.loads(staged_files[0].read_text())
        mtgs = staged["extraction"]["meetings_to_schedule"]
        assert mtgs[0]["cadence"] == "biweekly until pricing review"
        assert load_list(vault, "meetings.json") == []     # canonical untouched
        out = capsys.readouterr().out
        assert "pricing pre-read" in out                   # pathway printed
        assert "pmao review" in out


def test_run_syndicate_unknown_initiative_raises():
    from pmao.syndicate import run_syndicate
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        with pytest.raises(ValueError, match="init-999"):
            run_syndicate(vault, "init-999")


def test_run_syndicate_empty_output_stages_nothing(capsys):
    from unittest.mock import patch
    from pmao.syndicate import run_syndicate
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        with patch("pmao.llm.call_structured",
                   return_value={"pathway": [], "meetings_to_schedule": [], "review_flags": []}):
            run_syndicate(vault, "init-001")
        assert list((vault / "staging").glob("*.json")) == []
        assert "no meetings proposed" in capsys.readouterr().out.lower()


def test_cli_syndicate_dispatches():
    import sys
    from unittest.mock import patch
    from pmao.cli import main
    with patch("pmao.syndicate.run_syndicate") as mock_syn, \
         patch.object(sys, "argv", ["pmao", "syndicate", "v/", "--initiative", "init-001"]):
        main()
    mock_syn.assert_called_once()
    assert mock_syn.call_args.kwargs["initiative_id"] == "init-001"
```

- [ ] **Step 3: Create `skills/syndicate.md`:**

````markdown
---
name: pmao-syndicate
description: Recommend the stakeholder syndication pathway and meeting cadence for one initiative; proposals are staged for the review gate
---

# PMAO Syndicate

You are the Syndication Planner of a project-management system. Given one initiative, the people roster, the initiative's history, and what each decision-maker has signaled they care about, recommend the **minimal stakeholder pathway to approval**: who must see this initiative before it can be approved, why, in what sequence, and on what cadence. You return strict JSON. You do NOT schedule anything — your meeting proposals are staged for a human review gate.

## The initiative

{initiative}

## Roster

{roster}

Entries marked DECISION-MAKER must sign off on levers they control — they are mandatory pathway stops if the initiative touches their lever. Sequence matters: people who must *prepare or validate* material (analysts, data owners) come before the decision-makers who consume it.

## History (decisions, open questions, existing/open meetings)

{history}

Do NOT re-propose meetings that already exist as open in the history. If a needed meeting already exists, reference it in the pathway step instead of proposing a duplicate.

## What the decision-makers have signaled

{signals}

Use signals to sequence and to set each meeting's emphasis: address a principal's stated constraint BEFORE asking for their approval.

## Cadence

For each proposed meeting choose a cadence: "one-time", or a recurrence with an end trigger — "weekly", "biweekly", "monthly", or "<frequency> until <trigger>" (e.g. "biweekly until pricing review"). Recurring cadences are for ongoing alignment with a stakeholder group; approval-step meetings are usually one-time.

## Output: strict JSON only

Return one JSON object, no prose, no fences:

{
  "pathway": [
    {"step": 1, "stakeholders": ["resolved names or roles"], "purpose": "one line", "why": "why they must see it", "needs": "what they need to see", "timing": "relative timing, e.g. 'first' or 'after step 2'"}
  ],
  "meetings_to_schedule": [
    {
      "initiative_id": "the initiative's id",
      "purpose": "one line",
      "convener": "resolved name or null",
      "convener_resolution": "matched_roster|alias_merged|unresolved",
      "attendees": ["resolved names or roles"],
      "requester": "syndication",
      "functions": ["finance", "cs"],
      "target_timing": "yyyy-mm-dd | trigger phrase | unspecified",
      "cadence": "one-time | weekly | biweekly | monthly | <freq> until <trigger>",
      "related_decision": null,
      "related_question": null,
      "committee_ownership": false,
      "reconciliation_candidates": [],
      "source_span": "pathway step N"
    }
  ],
  "review_flags": ["anything uncertain about this pathway the human reviewer should check"]
}

Rules: every meeting maps to a pathway step via source_span; resolve names against the roster (never invent people); if the roster is missing, use roles/functions and flag it; empty arrays when nothing to propose.

Return only the JSON object.
````

- [ ] **Step 4: Create `pmao/syndicate.py`:**

```python
import json
from pathlib import Path

from pmao.vault import load_initiatives, load_list, refresh_workbook
from pmao.roster import load_roster, render_roster
from pmao.deep import _write_staging


def _history_block(vault_path: Path, iid: str, outstanding_meetings: str) -> str:
    lines = []
    for d in load_list(vault_path, "decisions.json"):
        if d.get("initiative_id") == iid:
            lines.append(f"decision: {d.get('decision', '')}")
    for q in load_list(vault_path, "questions.json"):
        if q.get("initiative_id") == iid and q.get("status") == "open":
            lines.append(f"open question: {q.get('question', '')}")
    for m in load_list(vault_path, "meetings.json"):
        if m.get("initiative_id") == iid and m.get("status") in ("open", "scheduled"):
            cadence = f", cadence: {m['cadence']}" if m.get("cadence") else ""
            lines.append(f"open meeting: {m.get('purpose', '')} ({m.get('target_timing') or 'unscheduled'}{cadence})")
    if outstanding_meetings:
        lines.append(f"outstanding meetings (free text): {outstanding_meetings}")
    return "\n".join(lines) if lines else "none"


def _signals_block(vault_path: Path, iid: str) -> str:
    lines = [
        f"{s.get('principal', '?')} on {s.get('lever', '?')}: {s.get('signal', '')} (implication: {s.get('implication', '')})"
        for s in load_list(vault_path, "signals.json")
        if s.get("initiative_id") in (iid, "general")
    ]
    return "\n".join(lines) if lines else "none"


def run_syndicate(vault_path: Path, initiative_id: str, config_override: str = None) -> None:
    from pmao import llm
    from pmao.ingest import _load_skill

    initiatives = load_initiatives(vault_path)
    init = next((i for i in initiatives if i.id == initiative_id), None)
    if init is None:
        valid = ", ".join(i.id for i in initiatives) or "(none)"
        raise ValueError(f"Unknown initiative '{initiative_id}'. Valid ids: {valid}")

    people = load_roster(vault_path)
    if people is None:
        print("Warning: no roster.yaml found — recommendations will use roles instead of resolved people.")

    initiative_text = json.dumps(init.to_dict(), indent=2, default=str)
    skill = _load_skill("syndicate")
    prompt = (
        skill
        .replace("{initiative}", initiative_text)
        .replace("{roster}", render_roster(people))
        .replace("{history}", _history_block(vault_path, initiative_id, init.outstanding_meetings or ""))
        .replace("{signals}", _signals_block(vault_path, initiative_id))
    )

    print(f"Recommending syndication pathway for {init.name} (this may take ~30s)...")
    result = llm.call_structured(prompt, config_override=config_override)
    result.setdefault("pathway", [])
    result.setdefault("meetings_to_schedule", [])
    result.setdefault("review_flags", [])

    print(f"\n--- Syndication pathway: {init.name} ---")
    for step in result["pathway"]:
        who = ", ".join(step.get("stakeholders", []))
        print(f"{step.get('step', '?')}. {who} — {step.get('purpose', '')}")
        if step.get("why"):
            print(f"   why: {step['why']}")
        if step.get("needs"):
            print(f"   needs: {step['needs']}")
        if step.get("timing"):
            print(f"   timing: {step['timing']}")
    if not result["pathway"]:
        print("(no pathway steps returned)")

    if not result["meetings_to_schedule"] and not result["review_flags"]:
        print("\nNo meetings proposed — nothing staged.")
        return

    extraction = {
        "meetings_to_schedule": result["meetings_to_schedule"],
        "review_flags": result["review_flags"],
    }
    staged_path = _write_staging(vault_path, extraction, f"syndicate-{initiative_id}")
    refresh_workbook(vault_path)
    n = len(result["meetings_to_schedule"])
    print(f"\nStaged {n} proposed meeting(s): staging/{staged_path.name}. Run 'pmao review' to promote.")
```

- [ ] **Step 5: Wire CLI** — in `pmao/cli.py` add:

```python
def cmd_syndicate(args) -> None:
    from pmao.syndicate import run_syndicate
    run_syndicate(vault_path=Path(args.vault), initiative_id=args.initiative, config_override=args.backend)
```

and in `main()`:

```python
    p_syn = sub.add_parser("syndicate", help="Recommend syndication pathway + meeting cadence for an initiative")
    p_syn.add_argument("vault", help="Path to vault directory")
    p_syn.add_argument("--initiative", required=True, metavar="ID", help="Initiative id, e.g. init-001")
    p_syn.add_argument("--backend", choices=["claude", "codex"], default=None)
    p_syn.set_defaults(func=cmd_syndicate)
```

- [ ] **Step 6:** Full suite green. **Commit** `feat: pmao syndicate — stakeholder pathway + cadence proposals staged through the gate`

---

### Task 5: README + regression

- [ ] **Step 1: README.** Commands table add:
  - `| \`pmao review <vault>\` | Walk staged extractions: approve/edit/reject, promote to canonical files, learn from verdicts |`
  - `| \`pmao syndicate <vault> --initiative ID\` | Recommend stakeholder pathway + meeting cadence; proposals staged for review |`
  Vault structure: `learning/` line already present. Add a short "## Review gate" section (verdict keys: a/e/r, p/k/x for hypotheses, y/n aliases, q to quit a file; commit-at-file-boundary; learning files) and extend the deep-ingest section's last paragraph: `pmao review` is no longer "upcoming". Skill files table: add `skills/syndicate.md` row.
- [ ] **Step 2:** `python3 -m pytest tests/ -q` — all green (expect ~85+).
- [ ] **Step 3: Commit** `docs: document review gate and syndication in README`

---

## Self-review notes

- Spec 2 coverage: alias-first ordering (T2), per-item verdicts incl. hypothesis p/k/x (T2), edit (T2), recon merge action-only (T1+T2), commit-at-file-boundary + quit discard (T2), promotion mapping all 9 rows (T1), derived outstanding_meetings only on meeting promotion (T1), last_touched (T1), learning verdicts+calibration with cap (T1+T2), corrupt staging skip (T2), flags accept/overturn (T2), flags-only ingest fix (T3).
- Spec 3 coverage: 4 placeholders + cadence skill (T4), unknown-initiative error (T4), staging via `_write_staging` with `syndicate-<id>` source (T4), empty-output no-stage (T4), cadence end-to-end: skill → staging → promotion (T1 mapping) → meetings.json → workbook column (T4).
- Type consistency: `promote_extraction(vault_path, approved, source)` used by T2; verdict record keys match between loop and learning writers; `STAGED_CATEGORIES` reused for display/summary keys.
