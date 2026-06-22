import json
import shutil
from pathlib import Path
from typing import List
import yaml

from pmao.models import Initiative

VAULT_FILES = [
    "project-config.yaml",
    "roster.yaml",
    "initiatives.json",
    "actions.json",
    "meetings.json",
    "decisions.json",
    "hypotheses.json",
    "facts.json",
    "workbook.xlsx",
]

_DEAD_FILES = ("signals.json", "questions.json")
_DEAD_DIRS = ("staging",)


def _cleanup_dead_files(vault_path: Path) -> None:
    for name in _DEAD_FILES:
        p = vault_path / name
        if p.exists():
            p.unlink()
    for name in _DEAD_DIRS:
        p = vault_path / name
        if p.exists():
            shutil.rmtree(p)


def init_vault(vault_path: Path, project_name: str = "My Project", owner: str = "") -> None:
    for marker in ("project-config.yaml", "initiatives.json"):
        if (vault_path / marker).exists():
            raise FileExistsError(
                f"{vault_path} already contains {marker} — refusing to overwrite "
                f"an existing vault. Delete the directory first to re-init."
            )
    vault_path.mkdir(parents=True, exist_ok=True)
    (vault_path / "transcripts").mkdir(exist_ok=True)

    config = {
        "project_name": project_name,
        "owner": owner,
        "llm_backend": None,
        "llm_timeout_seconds": 120,
    }
    (vault_path / "project-config.yaml").write_text(yaml.dump(config, default_flow_style=False))

    for fname in ("initiatives.json", "actions.json", "meetings.json",
                  "decisions.json", "hypotheses.json", "facts.json"):
        (vault_path / fname).write_text("[]")

    _ROSTER_TEMPLATE = """\
# roster.yaml — people involved in this project
# Used by ingest to canonicalize owner names from transcripts.
#
# people:
#   - name: Jane Smith
#     aliases: [Jane, J. Smith]
#     role: Program Manager
#   - name: Bob Jones
#     aliases: [Bob]
#     role: ELT

people: []
"""
    (vault_path / "roster.yaml").write_text(_ROSTER_TEMPLATE)

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
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(target)
    _cleanup_dead_files(vault_path)


def load_list(vault_path: Path, filename: str) -> list:
    path = vault_path / filename
    return json.loads(path.read_text()) if path.exists() else []


def refresh_workbook(vault_path: Path) -> None:
    from pmao.excel import create_workbook
    create_workbook(
        vault_path / "workbook.xlsx",
        load_initiatives(vault_path),
        actions=load_list(vault_path, "actions.json"),
        decisions=load_list(vault_path, "decisions.json"),
        meetings=load_list(vault_path, "meetings.json"),
        hypotheses=load_list(vault_path, "hypotheses.json"),
        facts=load_list(vault_path, "facts.json"),
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
                last_touched=date.today(),
                owner=row.get("owner") or None,
                priority=row.get("priority") or None,
            ))
    save_initiatives(vault_path, initiatives)
    return len(initiatives)
