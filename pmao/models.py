from dataclasses import dataclass
from datetime import date
from typing import Optional, Literal


@dataclass
class Initiative:
    id: str
    name: str
    status: Literal["not_started", "in_progress", "ready", "complete"]
    created: date
    last_touched: date
    coordination_owner: Optional[str] = None
    responsible_owner: Optional[str] = None
    priority: Optional[Literal["high", "medium", "low"]] = None
    current_state: Optional[str] = None
    coordination_next_steps: Optional[str] = None
    outstanding_questions: Optional[str] = None
    outstanding_meetings: Optional[str] = None
    last_touch_comment: Optional[str] = None
    last_touch_timestamp: Optional[date] = None
    syndication_notes: Optional[str] = None
    materials_link: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "created": self.created.isoformat(),
            "last_touched": self.last_touched.isoformat(),
            "coordination_owner": self.coordination_owner,
            "responsible_owner": self.responsible_owner,
            "priority": self.priority,
            "current_state": self.current_state,
            "coordination_next_steps": self.coordination_next_steps,
            "outstanding_questions": self.outstanding_questions,
            "outstanding_meetings": self.outstanding_meetings,
            "last_touch_comment": self.last_touch_comment,
            "last_touch_timestamp": self.last_touch_timestamp.isoformat() if self.last_touch_timestamp else None,
            "syndication_notes": self.syndication_notes,
            "materials_link": self.materials_link,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Initiative":
        return cls(
            id=d["id"],
            name=d["name"],
            status=d["status"],
            created=date.fromisoformat(d["created"]),
            last_touched=date.fromisoformat(d["last_touched"]),
            coordination_owner=d.get("coordination_owner"),
            responsible_owner=d.get("responsible_owner"),
            priority=d.get("priority"),
            current_state=d.get("current_state"),
            coordination_next_steps=d.get("coordination_next_steps"),
            outstanding_questions=d.get("outstanding_questions"),
            outstanding_meetings=d.get("outstanding_meetings"),
            last_touch_comment=d.get("last_touch_comment"),
            last_touch_timestamp=date.fromisoformat(d["last_touch_timestamp"]) if d.get("last_touch_timestamp") else None,
            syndication_notes=d.get("syndication_notes"),
            materials_link=d.get("materials_link"),
            notes=d.get("notes"),
        )
