import json
from datetime import date
from pathlib import Path
from typing import List

from pmao.vault import (
    load_initiatives, save_initiatives, load_list,
    refresh_workbook, STAGED_CATEGORIES,
)

CALIBRATION_MAX_LINES = 500

# category -> the person field the gate's "owner" edit should write
PERSON_KEYS = {
    "facts": "stated_by",
    "hypotheses": "held_by",
    "decisions": "decided_by",
    "open_questions": "raised_by",
    "principal_signals": "principal",
    "meetings_to_schedule": "convener",
    "action_items": "owner",
}


class _Quit(Exception):
    """User quit mid-file — discard this file's verdicts."""


# ── Promotion core ─────────────────────────────────────────────────────────────

def _record_for(category: str, item: dict, source: str, verdict: str):
    """Map a staged item to (canonical filename, id prefix, record dict without id)."""
    if verdict == "killed":
        raise ValueError("killed items are never promoted")
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
            question=item.get("question", ""), raised_by=item.get("raised_by", ""),
            why_it_matters=item.get("why_it_matters", ""), status="open")
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
    today = date.today().isoformat()
    existing = {r.get("id") for r in records if isinstance(r, dict)}
    n = len(records)
    while f"{prefix}-{today}-{n:04d}" in existing:
        n += 1
    return f"{prefix}-{today}-{n:04d}"


def _apply_merge(records: list, entry: dict) -> bool:
    """Fold an approved action item into the existing open action it matched.

    Returns False if the merge target does not exist (the caller must then
    promote the item as a new record instead of dropping it).
    """
    target = next((r for r in records if r.get("id") == entry["merged_into"]), None)
    if target is None:
        return False
    new_desc = entry["item"].get("description", "")
    if new_desc:
        target["description"] = f"{target.get('description', '')} [updated: {new_desc}]"
    new_due = entry["item"].get("due", "")
    if new_due and new_due != "unspecified":
        target["due"] = new_due
    return True


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
            if entry["category"] != "action_items":
                continue
            records = by_file.setdefault("actions.json", load_list(vault_path, "actions.json"))
            if _apply_merge(records, entry):
                continue
            print(f"Warning: merge target {entry['merged_into']} not found — promoting as new item.")
            # fall through: promote as a new record instead of losing the item
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


def _ask_merge(prompt: str) -> str:
    """Merge prompt: empty input means no ([y/N]). 'q' or EOF/interrupt quits."""
    while True:
        try:
            ans = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise _Quit()
        if ans == "q":
            raise _Quit()
        if ans == "":
            return "n"
        if ans in ("y", "n"):
            return ans


def _candidates(item: dict) -> list:
    """The item's reconciliation_candidates, tolerating malformed staged shapes."""
    rcs = item.get("reconciliation_candidates")
    if not isinstance(rcs, list):
        return []
    return [rc for rc in rcs if isinstance(rc, dict)]


def _display_item(category: str, item: dict, idx: int, total: int) -> None:
    summary_key = STAGED_CATEGORIES[category]
    print(f"\n[{category} {idx}/{total}] initiative: {item.get('initiative_id') or '(project-level)'}")
    print(f"  {summary_key}: {item.get(summary_key, '')}")
    for k in ("owner", "owner_resolution", "stated_by", "held_by", "decided_by", "raised_by",
              "why_it_matters", "principal", "lever", "implication",
              "convener", "convener_resolution", "attendees", "authority",
              "confidence", "type", "due", "target_timing", "cadence", "would_confirm", "source_span"):
        if item.get(k):
            val = item[k]
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            print(f"  {k}: {val}")
    for rc in _candidates(item):
        print(f"  possible match: {rc.get('existing')} ({rc.get('match_confidence')})")


def _edit_item(category: str, item: dict, known_ids: set) -> dict:
    """Prompt for initiative_id, person field, and the summary field; empty input keeps current.

    initiative_id edits are validated against known initiative ids (+ 'general'),
    mirroring _validate_extraction — re-prompt on unknown ids.
    """
    summary_key = STAGED_CATEGORIES[category]
    person_key = PERSON_KEYS.get(category, "owner")
    edits = {}
    for field in ("initiative_id", person_key, summary_key):
        old = item.get(field) or ""
        while True:
            try:
                new = input(f"  {field} [{old}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                raise _Quit()
            if field == "initiative_id" and new and new != old and new not in known_ids:
                print(f"  unknown initiative_id '{new}' — known: {', '.join(sorted(known_ids))}")
                continue
            break
        if new and new != old:
            edits[field] = [old, new]
            item[field] = new
    return edits


def _review_file(vault_path: Path, staged_path: Path, data: dict) -> None:
    extraction = data.get("extraction", {})
    source = data.get("source", staged_path.name)
    known_ids = {i.id for i in load_initiatives(vault_path)} | {"general"}

    # Normalize malformed staged shapes so hostile content never crashes the gate.
    alias_flags = extraction.get("alias_flags")
    alias_flags = alias_flags if isinstance(alias_flags, list) else []
    review_flags = extraction.get("review_flags")
    review_flags = review_flags if isinstance(review_flags, list) else []
    cat_items = {}
    for category in STAGED_CATEGORIES:
        items = extraction.get(category)
        cat_items[category] = items if isinstance(items, list) else []

    print(f"\n=== Reviewing {staged_path.name} (source: {source}, ingested: {data.get('ingested', '?')}) ===")
    counts = ", ".join(f"{c}: {len(items)}" for c, items in cat_items.items() if items)
    if counts:
        print(f"counts: {counts}")
    if extraction.get("discard_note"):
        print(f"discard_note: {extraction['discard_note']}")

    approved, verdicts = [], []
    total = len(alias_flags) + sum(len(v) for v in cat_items.values()) + len(review_flags)

    try:
        for alias in alias_flags:
            if not isinstance(alias, dict):
                print(f"\nWarning: skipping malformed alias_flags entry: {alias!r}")
                verdicts.append({"category": "alias_flags", "summary": str(alias)[:80],
                                 "verdict": "skipped_malformed"})
                continue
            variants_raw = alias.get("variants")
            variants_list = ([v for v in variants_raw if isinstance(v, str)]
                             if isinstance(variants_raw, list) else [])
            variants = " / ".join(variants_list)
            resolved_to = alias.get("resolved_to")
            print(f"\nAlias: {variants} -> {resolved_to} ({alias.get('confidence')})")
            ans = _ask("  confirm alias? [y/n] ", "y/n")
            verdict = "alias_confirmed" if ans == "y" else "alias_rejected"
            verdicts.append({"category": "alias_flags", "summary": f"{variants} -> {resolved_to}",
                             "verdict": verdict, "variants": variants_list, "resolved_to": resolved_to})

        for category, summary_key in STAGED_CATEGORIES.items():
            items = cat_items[category]
            for idx, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    print(f"\nWarning: skipping malformed {category} item: {item!r}")
                    verdicts.append({"category": category, "summary": str(item)[:80],
                                     "verdict": "skipped_malformed"})
                    continue
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
                    edits = _edit_item(category, item, known_ids)
                    entry["verdict"] = "edited"
                    verdicts.append(dict(base, verdict="edited", edited=edits,
                                         initiative_id=item.get("initiative_id"),
                                         summary=item.get(summary_key, "")))
                else:
                    verdicts.append(dict(base, verdict="approved"))
                rcs = _candidates(item)
                if rcs:
                    cand = rcs[0].get("existing")
                    if category == "action_items" and not any(
                            r.get("id") == cand
                            for r in load_list(vault_path, "actions.json")
                            if isinstance(r, dict)):
                        print(f"  match {cand} not found in actions.json — will promote as new item")
                    else:
                        ans = _ask_merge(f"  merge into existing {cand}? [y/N] ")
                        if ans == "y":
                            entry["merged_into"] = cand
                            verdicts[-1]["verdict"] = "merged"
                            verdicts[-1]["merged_into"] = cand
                approved.append(entry)

        for flag in review_flags:
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
    except _Quit:
        print(f"\nskipped {max(total - len(verdicts), 0)} unreviewed item(s) in {staged_path.name}")
        raise

    # ── Commit at file boundary ────────────────────────────────────────────────
    # Order: promote → staging flip → learning writes → workbook
    # (crash between promote and staging flip would double-promote on re-run,
    # but flipping staging first then crashing on learning writes is safer)
    promote_extraction(vault_path, approved, source=source)
    today = date.today().isoformat()
    data["status"] = "reviewed"
    data["reviewed"] = today
    staged_path.write_text(json.dumps(data, indent=2))
    for v in verdicts:
        append_verdict(vault_path, dict(v, ts=today, staging_file=staged_path.name))
        if v["verdict"] == "alias_confirmed":
            variants = " / ".join(v.get("variants") or [])
            resolved = v.get("resolved_to") or ""
            append_calibration(vault_path, f'alias: "{variants}" → "{resolved}" (confirmed)')
        elif v["verdict"] == "alias_rejected":
            variants = " / ".join(v.get("variants") or [])
            resolved = v.get("resolved_to") or ""
            append_calibration(vault_path, f'alias: "{variants}" → "{resolved}" (REJECTED — do not merge)')
        elif v["verdict"] == "rejected":
            append_calibration(vault_path,
                f'boundary: rejected {v["category"]}: "{v["summary"]}" — do not extract similar')
        elif v["verdict"] == "flag_overturned":
            append_calibration(vault_path,
                f'boundary: near-discard overturned: "{v["summary"]}" — extract similar next time')
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
            if not isinstance(data, dict):
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
