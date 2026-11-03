import shutil
from pathlib import Path
from typing import List
import yaml

from pmao.models import Initiative
from pmao.store import FOLDERS, read_items, write_item

VAULT_DIRS = FOLDERS

_SECTIONS = (
    ("current_state", "## Current state"),
    ("next_steps", "## Next steps"),
    ("last_touch_comment", "## Last touch"),
    ("notes", "## Notes"),
)
_SECTION_FIELDS = {key for key, _ in _SECTIONS}


def init_vault(vault_path: Path, project_name: str = "My Project", owner: str = "") -> None:
    existing = [p for p in [vault_path / "project-config.yaml", *sorted((vault_path / "projects").glob("*.md"))]
                if p.exists()]
    if existing:
        raise FileExistsError(
            f"{vault_path} already contains {existing[0].name} — refusing to overwrite "
            f"an existing vault. Delete the directory first to re-init."
        )
    vault_path.mkdir(parents=True, exist_ok=True)
    for d in VAULT_DIRS:
        (vault_path / d).mkdir(exist_ok=True)

    config = {
        "project_name": project_name,
        "owner": owner,
        "llm_backend": None,
        "llm_timeout_seconds": 120,
    }
    (vault_path / "project-config.yaml").write_text(yaml.dump(config, default_flow_style=False))
    shutil.copy2(Path(__file__).parent / "templates" / "SCHEMA.md", vault_path / "SCHEMA.md")

    from pmao.excel import create_workbook
    create_workbook(vault_path / "workbook.xlsx", [])


def _split_body(body: str) -> dict:
    headings = {h: key for key, h in _SECTIONS}
    out, key = {}, None
    for line in body.split("\n"):
        if line in headings and headings[line] not in out:
            key = headings[line]
            out[key] = []
        elif key:
            out[key].append(line)
    return {k: "\n".join(v).strip("\n") or None for k, v in out.items()}


def _join_body(d: dict) -> str:
    return "\n\n".join(f"{h}\n{d[key]}" for key, h in _SECTIONS if d.get(key))


def load_initiatives(vault_path: Path) -> List[Initiative]:
    return [Initiative.from_dict({**{k: v for k, v in i.items() if k not in ("type", "body", "_file")},
                                  **_split_body(i.get("body", ""))})
            for i in read_items(vault_path, "projects")]


def save_initiatives(vault_path: Path, initiatives: List[Initiative]) -> None:
    files = {i["id"]: i["_file"] for i in read_items(vault_path, "projects") if "id" in i}
    for init in initiatives:
        d = init.to_dict()
        item = {"type": "project", **{k: v for k, v in d.items() if k not in _SECTION_FIELDS},
                "body": _join_body(d)}
        if init.id in files:
            item["_file"] = files[init.id]
        write_item(vault_path, "projects", item, init.name)


def load_items(vault_path: Path, folder: str, type: str = None) -> list:
    return [i for i in read_items(vault_path, folder) if type is None or i.get("type") == type]


def save_items(vault_path: Path, folder: str, items: List[dict], title_key: str) -> None:
    for item in items:
        write_item(vault_path, folder, item, str(item.get(title_key) or "item"))


def refresh_workbook(vault_path: Path) -> None:
    from pmao.excel import create_workbook
    create_workbook(
        vault_path / "workbook.xlsx",
        load_initiatives(vault_path),
        actions=load_items(vault_path, "tasks"),
        decisions=load_items(vault_path, "decisions"),
        meetings=load_items(vault_path, "meetings"),
        hypotheses=load_items(vault_path, "notes", "hypothesis"),
        facts=load_items(vault_path, "notes", "fact"),
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
