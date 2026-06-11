import json
import re
from datetime import date
from pathlib import Path
from typing import List

from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from pmao.models import Initiative
from pmao.vault import load_initiatives, load_list, refresh_workbook, STAGED_CATEGORIES
from pmao.roster import load_roster, render_roster

PROMPT_VERSION = "pmao-deep-v1.1"
CALIBRATION_LINE_CAP = 200
RECON_DECISION_CAP = 20

# category -> the key that summarizes one item of that category
ITEM_CATEGORIES = STAGED_CATEGORIES


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
    actions = [a for a in load_list(vault_path, "actions.json")
               if isinstance(a, dict) and a.get("status") == "open"]
    decisions = [d for d in load_list(vault_path, "decisions.json")
                 if isinstance(d, dict)][-RECON_DECISION_CAP:]
    lines = []
    for a in actions:
        due = a.get("due") or "no due date"
        lines.append(f"{a.get('id', '?')}: {a.get('description', '?')} (owner: {a.get('owner', '?')}, due: {due})")
    for d in decisions:
        lines.append(f"{d.get('id', '?')}: {d.get('decision', '?')}")
    return "\n".join(lines) if lines else "none"


def _calibration_block(vault_path: Path) -> str:
    """Last CALIBRATION_LINE_CAP lines of learning/calibration.md (newest lessons win)."""
    cal_path = vault_path / "learning" / "calibration.md"
    if not cal_path.exists():
        return "No prior calibration."
    lines = cal_path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[-CALIBRATION_LINE_CAP:])


def _sanitize_value(value):
    """Strip openpyxl-illegal control chars from strings; recurse into dicts and
    lists so nested structures (e.g. reconciliation_candidates) are preserved verbatim."""
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub("", value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    return ILLEGAL_CHARACTERS_RE.sub("", str(value))


def _validate_extraction(extraction: dict, initiatives: List[Initiative]) -> dict:
    """Default missing keys; normalize wrong-shaped values (flagged, not crashed);
    sanitize hostile values; flag (never drop) unknown initiative ids — recall over precision."""
    if not isinstance(extraction, dict):
        raise ValueError(
            f"LLM returned JSON of type {type(extraction).__name__}, "
            f"expected an object — nothing staged."
        )
    flags = extraction.get("review_flags")
    extraction["review_flags"] = (
        [ILLEGAL_CHARACTERS_RE.sub("", str(f)) for f in flags] if isinstance(flags, list) else []
    )
    for key in ITEM_CATEGORIES:
        items = extraction.get(key)
        if not isinstance(items, list):
            if items is not None:
                extraction["review_flags"].append(
                    f"malformed {key}: expected a list, got {type(items).__name__} — dropped"
                )
            extraction[key] = []
            continue
        kept = []
        for item in items:
            if not isinstance(item, dict):
                extraction["review_flags"].append(
                    f"malformed {key} item dropped: {str(item)[:80]}"
                )
                continue
            kept.append({k: _sanitize_value(v) for k, v in item.items()})
        extraction[key] = kept
    aliases = extraction.get("alias_flags")
    if not isinstance(aliases, list):
        aliases = []
    kept_aliases = []
    for a in aliases:
        if not isinstance(a, dict):
            extraction["review_flags"].append(
                f"malformed alias_flags item dropped: {str(a)[:80]}"
            )
            continue
        kept_aliases.append({k: _sanitize_value(v) for k, v in a.items()})
    extraction["alias_flags"] = kept_aliases
    extraction["discard_note"] = _sanitize_value(extraction.get("discard_note") or "")
    if not isinstance(extraction.get("meta"), dict):
        extraction["meta"] = {}
    known = {i.id for i in initiatives}
    for category, summary_key in ITEM_CATEGORIES.items():
        for item in extraction[category]:
            iid = item.get("initiative_id")
            if iid is not None and iid != "general" and str(iid) not in known:
                extraction["review_flags"].append(
                    f"unknown initiative_id '{iid}' on {category}: "
                    f"{str(item.get(summary_key, ''))[:80]}"
                )
    return extraction


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
    extraction = llm.call_structured(prompt, config_override=config_override, vault_path=vault_path)
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
            variants_raw = a.get("variants") or []
            if not isinstance(variants_raw, list):
                variants_raw = [variants_raw]
            variants = " / ".join(str(v) for v in variants_raw)
            print(f"  {variants} -> {a.get('resolved_to', '?')} ({a.get('confidence', '?')})")
    if extraction["review_flags"]:
        print("\nReview flags:")
        for flag in extraction["review_flags"]:
            print(f"  - {flag}")

    if not any(counts.values()) and not extraction["review_flags"] and not extraction["alias_flags"]:
        print("\nNothing extracted — nothing staged.")
        return

    staged_path = _write_staging(vault_path, extraction, source_path.name)
    refresh_workbook(vault_path)
    print(f"\nStaged for review: staging/{staged_path.name}. Run 'pmao review' to promote.")


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
