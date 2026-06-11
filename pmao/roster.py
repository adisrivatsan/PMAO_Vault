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
        if not isinstance(person["name"], str):
            raise RosterError(f"roster.yaml people[{i}] 'name' must be a string")
        for field in ("aliases", "domains", "levers"):
            value = person.get(field)
            if value is None:
                continue
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise RosterError(
                    f"roster.yaml people[{i}] '{field}' must be a list of strings"
                )
    return people


def render_roster(people: Optional[List[dict]]) -> str:
    """Render the roster as a prompt-ready text block."""
    if not people:
        return (
            'No roster was provided. Mark authority "unknown" and lower '
            "confidence; never invent owners or attribute decision-making "
            "power to anyone."
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
