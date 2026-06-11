from dataclasses import dataclass
from datetime import date
from typing import Optional, Literal


@dataclass
class Initiative:
    id: str
    name: str
    status: Literal["not_started", "in_progress", "ready", "complete"]
    last_touched: date
    owner: Optional[str] = None
    priority: Optional[Literal["high", "medium", "low"]] = None
    current_state: Optional[str] = None
    next_steps: Optional[str] = None
    last_touch_comment: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "priority": self.priority,
            "owner": self.owner,
            "current_state": self.current_state,
            "next_steps": self.next_steps,
            "last_touched": self.last_touched.isoformat(),
            "last_touch_comment": self.last_touch_comment,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Initiative":
        # Owner migration: coordination_owner preferred; responsible_owner fallback
        coord_owner = d.get("coordination_owner")
        old_responsible = d.get("responsible_owner")
        owner = coord_owner or d.get("owner") or old_responsible or None
        notes_parts = []
        if d.get("notes"):
            notes_parts.append(d["notes"])
        if coord_owner and old_responsible and old_responsible != coord_owner:
            notes_parts.append(f"Responsible: {old_responsible}")
        for old_key, label in (
            ("outstanding_questions", "Open questions"),
            ("outstanding_meetings", "Meetings"),
            ("syndication_notes", "Syndication"),
            ("materials_link", "Materials"),
        ):
            val = d.get(old_key)
            if val:
                notes_parts.append(f"{label}: {val}")
        notes = "\n".join(notes_parts) or None

        # next_steps migration
        next_steps = d.get("next_steps") or d.get("coordination_next_steps") or None

        # last_touched: prefer last_touch_timestamp (more specific) over last_touched
        last_touched_str = d.get("last_touch_timestamp") or d.get("last_touched")
        last_touched = date.fromisoformat(last_touched_str) if last_touched_str else date.today()

        return cls(
            id=d["id"],
            name=d["name"],
            status=d["status"],
            last_touched=last_touched,
            owner=owner,
            priority=d.get("priority"),
            current_state=d.get("current_state"),
            next_steps=next_steps,
            last_touch_comment=d.get("last_touch_comment"),
            notes=notes,
        )
