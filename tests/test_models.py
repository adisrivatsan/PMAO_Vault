from datetime import date
from pmao.models import Initiative

def test_initiative_round_trip():
    init = Initiative(
        id="init-001",
        name="Customer Data Platform",
        status="in_progress",
        created=date(2026, 6, 8),
        last_touched=date(2026, 6, 8),
        coordination_owner="Alex Jordan",
        priority="high",
    )
    d = init.to_dict()
    recovered = Initiative.from_dict(d)
    assert recovered.id == "init-001"
    assert recovered.coordination_owner == "Alex Jordan"
    assert recovered.responsible_owner is None

def test_initiative_optional_fields_default_none():
    init = Initiative(
        id="init-002", name="Test", status="not_started",
        created=date(2026, 6, 8), last_touched=date(2026, 6, 8)
    )
    assert init.coordination_owner is None
    assert init.priority is None
    assert init.current_state is None

def test_initiative_last_touch_timestamp_round_trip():
    init = Initiative(
        id="x", name="x", status="not_started",
        created=date(2026, 6, 8), last_touched=date(2026, 6, 8),
        last_touch_timestamp=date(2026, 6, 5),
    )
    d = init.to_dict()
    assert d["last_touch_timestamp"] == "2026-06-05"
    recovered = Initiative.from_dict(d)
    assert recovered.last_touch_timestamp == date(2026, 6, 5)

def test_initiative_null_last_touch_timestamp_round_trip():
    init = Initiative(
        id="x", name="x", status="not_started",
        created=date(2026, 6, 8), last_touched=date(2026, 6, 8),
    )
    d = init.to_dict()
    assert d["last_touch_timestamp"] is None
    recovered = Initiative.from_dict(d)
    assert recovered.last_touch_timestamp is None

def test_initiative_all_optional_fields_survive_round_trip():
    init = Initiative(
        id="init-003", name="Analytics Modernization",
        status="in_progress", priority="medium",
        created=date(2026, 6, 1), last_touched=date(2026, 6, 8),
        coordination_owner="Sam Lee",
        responsible_owner="Jordan Kim",
        current_state="Data model designed",
        coordination_next_steps="- Sam to schedule kickoff",
        outstanding_questions="Budget approval still needed",
        outstanding_meetings="Need kickoff with data team",
        last_touch_comment="[email] Sam confirmed timeline",
        last_touch_timestamp=date(2026, 6, 7),
        syndication_notes="Present to leadership Jun 18",
        materials_link="https://docs.example.com/analytics",
        notes="Depends on cloud migration completing first",
    )
    recovered = Initiative.from_dict(init.to_dict())
    assert recovered.current_state == "Data model designed"
    assert recovered.responsible_owner == "Jordan Kim"
    assert recovered.syndication_notes == "Present to leadership Jun 18"
