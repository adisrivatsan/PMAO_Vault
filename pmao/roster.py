import sys
from pathlib import Path
from typing import List, Optional

from pmao import store


def load_roster(vault_path: Path) -> Optional[List[dict]]:
    people = []
    for item in store.read_items(vault_path, "people"):
        if not isinstance(item.get("name"), str):
            print(f"Warning: skipping people/{item['_file']}.md: missing 'name'", file=sys.stderr)
            continue
        people.append(item)
    return people or None


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
