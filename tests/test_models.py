from datetime import date
from pmao.models import Initiative


def _make():
    return Initiative(
        id="init-001", name="Alpha Build",
        status="not_started", last_touched=date(2026, 6, 11),
    )


def test_slim_fields_round_trip():
    init = Initiative(
        id="init-001", name="Alpha Build", status="in_progress",
        last_touched=date(2026, 6, 11), owner="Alex Jordan",
        priority="high", current_state="Analysis done",
        next_steps="- Book review", last_touch_comment="[email] done",
        notes="Depends on cloud migration",
    )
    d = init.to_dict()
    assert set(d.keys()) == {
        "id", "name", "status", "priority", "owner",
        "current_state", "next_steps", "last_touched",
        "last_touch_comment", "notes",
    }
    r = Initiative.from_dict(d)
    assert r.id == "init-001"
    assert r.owner == "Alex Jordan"
    assert r.next_steps == "- Book review"
    assert r.last_touched == date(2026, 6, 11)


def test_optional_fields_default_none():
    init = _make()
    assert init.owner is None
    assert init.priority is None
    assert init.notes is None


def test_migration_coordination_owner_becomes_owner():
    d = {
        "id": "init-001", "name": "X", "status": "not_started",
        "last_touched": "2026-06-11",
        "coordination_owner": "Jane Smith",
    }
    r = Initiative.from_dict(d)
    assert r.owner == "Jane Smith"


def test_migration_responsible_owner_fallback():
    d = {
        "id": "init-001", "name": "X", "status": "not_started",
        "last_touched": "2026-06-11",
        "responsible_owner": "Sam Lee",
    }
    r = Initiative.from_dict(d)
    assert r.owner == "Sam Lee"


def test_migration_both_owners_differ_appends_notes():
    d = {
        "id": "init-001", "name": "X", "status": "not_started",
        "last_touched": "2026-06-11",
        "coordination_owner": "Jane Smith",
        "responsible_owner": "Sam Lee",
    }
    r = Initiative.from_dict(d)
    assert r.owner == "Jane Smith"
    assert "Responsible: Sam Lee" in r.notes


def test_migration_both_owners_same_no_notes():
    d = {
        "id": "init-001", "name": "X", "status": "not_started",
        "last_touched": "2026-06-11",
        "coordination_owner": "Jane Smith",
        "responsible_owner": "Jane Smith",
    }
    r = Initiative.from_dict(d)
    assert r.owner == "Jane Smith"
    assert not r.notes


def test_migration_coordination_next_steps_becomes_next_steps():
    d = {
        "id": "init-001", "name": "X", "status": "not_started",
        "last_touched": "2026-06-11",
        "coordination_next_steps": "- Book review",
    }
    r = Initiative.from_dict(d)
    assert r.next_steps == "- Book review"


def test_migration_old_fields_folded_into_notes():
    d = {
        "id": "init-001", "name": "X", "status": "not_started",
        "last_touched": "2026-06-11",
        "outstanding_questions": "Budget?",
        "outstanding_meetings": "Kickoff needed",
        "syndication_notes": "Present Jun 18",
        "materials_link": "https://docs.example.com",
    }
    r = Initiative.from_dict(d)
    assert "Open questions: Budget?" in r.notes
    assert "Meetings: Kickoff needed" in r.notes
    assert "Syndication: Present Jun 18" in r.notes
    assert "Materials: https://docs.example.com" in r.notes


def test_migration_last_touch_timestamp_preferred_over_last_touched():
    d = {
        "id": "init-001", "name": "X", "status": "not_started",
        "last_touched": "2026-06-01",
        "last_touch_timestamp": "2026-06-09",
    }
    r = Initiative.from_dict(d)
    assert r.last_touched == date(2026, 6, 9)


def test_migration_created_field_dropped():
    d = {
        "id": "init-001", "name": "X", "status": "not_started",
        "last_touched": "2026-06-11", "created": "2026-01-01",
    }
    r = Initiative.from_dict(d)
    d2 = r.to_dict()
    assert "created" not in d2


def test_to_dict_no_old_fields():
    init = _make()
    d = init.to_dict()
    for old in ("coordination_owner", "responsible_owner", "coordination_next_steps",
                "outstanding_questions", "outstanding_meetings", "syndication_notes",
                "materials_link", "last_touch_timestamp", "created"):
        assert old not in d, f"old field still in to_dict: {old}"
