from pathlib import Path
from typing import List, Optional

import yaml


def load_roster(vault_path: Path) -> Optional[List[dict]]:
    roster_path = vault_path / "roster.yaml"
    if not roster_path.exists():
        return None
    try:
        data = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"Warning: roster.yaml is not valid YAML — {e}")
        return None
    if not isinstance(data, dict) or not isinstance(data.get("people"), list):
        print("Warning: roster.yaml must contain a top-level 'people:' list — ignoring")
        return None
    for i, person in enumerate(data["people"]):
        if not isinstance(person, dict) or not isinstance(person.get("name"), str):
            print(f"Warning: roster.yaml people[{i}] missing valid 'name' string — ignoring roster")
            return None
    return data["people"]


def render_roster(people: Optional[List[dict]]) -> str:
    if not people:
        return ""
    lines = ["Known people (canonicalize owner names using these aliases):"]
    for p in people:
        parts = [p["name"]]
        if p.get("aliases"):
            parts.append(f"aliases: {', '.join(p['aliases'])}")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)
