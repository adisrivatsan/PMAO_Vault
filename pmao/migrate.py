import json
import shutil
from pathlib import Path
from typing import Dict

import yaml

from pmao.models import Initiative
from pmao.store import FOLDERS, read_items, write_item
from pmao.vault import load_initiatives, save_initiatives

# (json file, target folder, item type, title key)
_JSON_SOURCES = (
    ("actions.json", "tasks", "task", "description"),
    ("meetings.json", "meetings", "meeting", "purpose"),
    ("decisions.json", "decisions", "decision", "decision"),
    ("hypotheses.json", "notes", "hypothesis", "hypothesis"),
    ("facts.json", "notes", "fact", "claim"),
)


def _load_json(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def migrate_vault(vault_path: Path) -> Dict[str, int]:
    counts = {k: 0 for k in ("projects", "tasks", "meetings", "decisions", "notes", "people", "docs")}
    for d in FOLDERS:
        (vault_path / d).mkdir(parents=True, exist_ok=True)

    have = {i.id for i in load_initiatives(vault_path)}
    new = [i for i in (Initiative.from_dict(d) for d in _load_json(vault_path / "initiatives.json"))
           if i.id not in have]
    save_initiatives(vault_path, new)
    counts["projects"] = len(new)

    for fname, folder, type_, title_key in _JSON_SOURCES:
        seen = {i.get("id") for i in read_items(vault_path, folder)}
        for item in _load_json(vault_path / fname):
            if item.get("id") in seen:
                continue
            write_item(vault_path, folder, {"type": type_, **item}, str(item.get(title_key) or "item"))
            seen.add(item.get("id"))
            counts[folder] += 1

    roster = vault_path / "roster.yaml"
    if roster.exists():
        people = (yaml.safe_load(roster.read_text(encoding="utf-8")) or {}).get("people") or []
        seen = {p.get("name") for p in read_items(vault_path, "people")}
        for p in people:
            if p["name"] in seen:
                continue
            write_item(vault_path, "people", {"type": "person", **p}, p["name"])
            counts["people"] += 1

    transcripts = vault_path / "transcripts"
    if transcripts.is_dir():
        for f in sorted(transcripts.iterdir()):
            if f.is_file() and not (vault_path / "docs" / f.name).exists():
                shutil.move(str(f), vault_path / "docs" / f.name)
                counts["docs"] += 1

    schema = vault_path / "SCHEMA.md"
    if not schema.exists():
        shutil.copy2(Path(__file__).parent / "templates" / "SCHEMA.md", schema)
    return counts
