import re
import shutil
import sys
from pathlib import Path
from typing import List, Tuple
import yaml

FOLDERS = ("projects", "tasks", "people", "meetings", "decisions", "notes", "docs", "inbox")

BODY_FIELD = {
    "task": "description",
    "meeting": "purpose",
    "decision": "decision",
    "hypothesis": "hypothesis",
    "fact": "claim",
    "note": "text",
    "inbox": "context",
    "person": None,
    "project": "body",
}


def parse_frontmatter(text: str) -> Tuple[dict, str]:
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        raise ValueError("missing frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("unterminated frontmatter")
    try:
        meta = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML: {e}")
    if not isinstance(meta, dict):
        raise ValueError("frontmatter is not a mapping")
    body = "\n".join(lines[end + 1:])
    if body.startswith("\n"):
        body = body[1:]
    if body.endswith("\n"):
        body = body[:-1]
    return meta, body


def render_frontmatter(meta: dict, body: str = "") -> str:
    head = "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True) + "---\n"
    return head + "\n" + body + "\n" if body else head


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len].strip("-")
    return slug or "item"


def read_items(vault: Path, folder: str) -> List[dict]:
    items = []
    d = vault / folder
    if not d.is_dir():
        return items
    for path in sorted(d.glob("*.md")):
        try:
            meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
            if "type" not in meta:
                raise ValueError("missing 'type'")
        except ValueError as e:
            print(f"Warning: skipping {folder}/{path.name}: {e}", file=sys.stderr)
            continue
        field = BODY_FIELD.get(meta["type"])
        if field and body:
            meta[field] = body
        meta["_file"] = path.stem
        items.append(meta)
    return items


def write_item(vault: Path, folder: str, item: dict, title: str) -> Path:
    d = vault / folder
    d.mkdir(parents=True, exist_ok=True)
    meta = dict(item)
    stem = meta.pop("_file", None)
    if not stem:
        base = slugify(title)
        stem, n = base, 2
        while (d / f"{stem}.md").exists():
            stem = f"{base}-{n}"
            n += 1
    field = BODY_FIELD.get(meta.get("type"))
    body = meta.pop(field, "") if field else ""
    target = d / f"{stem}.md"
    if target.exists():
        shutil.copy2(target, d / f"{stem}.md.bak")
    tmp = d / f"{stem}.md.tmp"
    tmp.write_text(render_frontmatter(meta, body or ""), encoding="utf-8")
    tmp.replace(target)
    return target
