from pathlib import Path

from pmao.store import read_items, write_item


def test_round_trip_special_characters(tmp_path):
    item = {"type": "task", "description": 'Fix: the "bug" # 1\n---\nsecond line', "owner": "A: B"}
    write_item(tmp_path, "tasks", dict(item), "Fix bug")
    got = read_items(tmp_path, "tasks")
    assert got == [{**item, "_file": "fix-bug"}]


def test_same_title_does_not_overwrite(tmp_path):
    write_item(tmp_path, "projects", {"type": "project", "name": "a"}, "Pricing")
    write_item(tmp_path, "projects", {"type": "project", "name": "b"}, "Pricing")
    names = sorted(p.name for p in (tmp_path / "projects").iterdir())
    assert names == ["pricing-2.md", "pricing.md"]
    assert len(read_items(tmp_path, "projects")) == 2


def test_rewrite_with_file_key_overwrites_and_backs_up(tmp_path):
    write_item(tmp_path, "tasks", {"type": "task", "description": "x", "owner": "A"}, "T")
    item = read_items(tmp_path, "tasks")[0]
    item["owner"] = "B"
    write_item(tmp_path, "tasks", item, "T")
    files = sorted(p.name for p in (tmp_path / "tasks").iterdir())
    assert files == ["t.md", "t.md.bak"]
    assert read_items(tmp_path, "tasks")[0]["owner"] == "B"


def test_malformed_file_skipped_with_warning(tmp_path, capsys):
    d = tmp_path / "tasks"
    d.mkdir()
    (d / "a.md").write_text("no frontmatter here")
    (d / "b.md").write_text("---\n: : [bad\n---\nbody")
    write_item(tmp_path, "tasks", {"type": "task", "owner": "A"}, "ok")
    items = read_items(tmp_path, "tasks")
    assert [i["_file"] for i in items] == ["ok"]
    out = capsys.readouterr()
    assert "a.md" in out.out + out.err and "b.md" in out.out + out.err


def test_non_md_files_ignored(tmp_path):
    d = tmp_path / "tasks"
    d.mkdir()
    (d / ".DS_Store").write_text("x")
    (d / "x.md.bak").write_text("---\ntype: task\n---\n")
    assert read_items(tmp_path, "tasks") == []


def test_missing_folder_returns_empty(tmp_path):
    assert read_items(tmp_path, "tasks") == []


def test_item_without_type_is_skipped_with_warning(tmp_path, capsys):
    d = tmp_path / "notes"
    d.mkdir()
    (d / "n.md").write_text("---\nname: x\n---\nbody")
    assert read_items(tmp_path, "notes") == []
    out = capsys.readouterr()
    assert "n.md" in out.out + out.err
