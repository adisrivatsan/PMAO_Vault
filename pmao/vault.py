import json
import shutil
from pathlib import Path
from typing import List
import yaml

from pmao.models import Initiative

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


def init_vault(vault_path: Path, project_name: str = "My Project", owner: str = "") -> None:
    for marker in ("project-config.yaml", "initiatives.json"):
        if (vault_path / marker).exists():
            raise FileExistsError(
                f"{vault_path} already contains {marker} — refusing to overwrite "
                f"an existing vault. Delete the directory first to re-init."
            )
    vault_path.mkdir(parents=True, exist_ok=True)
    (vault_path / "transcripts").mkdir(exist_ok=True)
    (vault_path / "staging").mkdir(exist_ok=True)

    config = {
        "project_name": project_name,
        "owner": owner,
        "llm_backend": None,
        "llm_timeout_seconds": 120,
    }
    (vault_path / "project-config.yaml").write_text(yaml.dump(config, default_flow_style=False))

    (vault_path / "initiatives.json").write_text("[]")
    (vault_path / "actions.json").write_text("[]")
    (vault_path / "questions.json").write_text("[]")
    (vault_path / "decisions.json").write_text("[]")
    (vault_path / "hypotheses.json").write_text("[]")
    (vault_path / "facts.json").write_text("[]")
    (vault_path / "signals.json").write_text("[]")
    (vault_path / "meetings.json").write_text("[]")

    from pmao.excel import create_workbook
    create_workbook(vault_path / "workbook.xlsx", [])


def load_initiatives(vault_path: Path) -> List[Initiative]:
    data = json.loads((vault_path / "initiatives.json").read_text())
    return [Initiative.from_dict(d) for d in data]


def save_initiatives(vault_path: Path, initiatives: List[Initiative]) -> None:
    target = vault_path / "initiatives.json"
    if target.exists():
        shutil.copy2(target, vault_path / "initiatives.json.bak")
    data = [i.to_dict() for i in initiatives]
    target.write_text(json.dumps(data, indent=2, default=str))


def load_list(vault_path: Path, filename: str) -> list:
    """Load a JSON-array vault file; empty list if absent."""
    path = vault_path / filename
    return json.loads(path.read_text()) if path.exists() else []


STAGED_CATEGORIES = {
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
        try:
            staged = json.loads(f.read_text())
        except json.JSONDecodeError:
            print(f"Warning: skipping corrupt staging file {f.name}")
            continue
        if not isinstance(staged, dict):
            print(f"Warning: skipping corrupt staging file {f.name}")
            continue
        if staged.get("status") != "pending_review":
            continue
        extraction = staged.get("extraction", {})
        for category, summary_key in STAGED_CATEGORIES.items():
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


def seed_from_csv(vault_path: Path, csv_path: Path) -> int:
    import csv
    from datetime import date

    initiatives = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "name" not in (reader.fieldnames or []):
            raise ValueError(
                f"CSV {csv_path.name} is missing the required 'name' column "
                f"(found columns: {', '.join(reader.fieldnames or []) or 'none'})"
            )
        for i, row in enumerate(reader):
            initiatives.append(Initiative(
                id=row.get("id") or f"init-{i + 1:03d}",
                name=row["name"],
                status="not_started",
                created=date.today(),
                last_touched=date.today(),
                coordination_owner=row.get("coordination_owner") or None,
                responsible_owner=row.get("responsible_owner") or None,
                priority=row.get("priority") or None,
            ))
    save_initiatives(vault_path, initiatives)
    return len(initiatives)
