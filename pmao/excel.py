from pathlib import Path
from typing import List, Optional

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import FormulaRule
from openpyxl.utils import get_column_letter

from pmao.models import Initiative

_MAX_CELL_LEN = 32767
_TRUNCATION_MARKER = " … [truncated]"

_HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_GREEN  = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
_YELLOW = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
_GRAY   = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
_THIN   = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

DASHBOARD_COLS    = ["id", "name", "status", "priority", "owner", "last_touched", "current_state"]
INITIATIVE_COLS   = ["id", "name", "status", "priority", "owner", "current_state",
                     "next_steps", "last_touched", "last_touch_comment", "notes"]
ACT_DEC_COLS      = ["type", "initiative", "description", "owner",
                     "due_or_rationale", "status", "created", "source"]
MEETING_COLS      = ["initiative", "purpose", "attendees", "status", "created", "source"]
HYPOTHESIS_COLS   = ["level", "initiative", "hypothesis", "owner",
                     "validation_path", "status", "created", "source"]
FACT_COLS         = ["initiative", "claim", "stated_by", "created", "source"]


def _write_header_row(ws, cols: list) -> None:
    for ci, col_name in enumerate(cols, start=1):
        cell = ws.cell(row=1, column=ci, value=col_name)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = _BORDER
    ws.row_dimensions[1].height = 30


def _write_data_row(ws, row_num: int, cols: list, record: dict) -> None:
    for ci, col_name in enumerate(cols, start=1):
        val = record.get(col_name, "") or ""
        if not isinstance(val, (str, int, float, bool)):
            val = str(val)
        if isinstance(val, str):
            val = ILLEGAL_CHARACTERS_RE.sub("", val)
            if len(val) > _MAX_CELL_LEN:
                val = val[: _MAX_CELL_LEN - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER
        cell = ws.cell(row=row_num, column=ci, value=val)
        if isinstance(val, str) and val.startswith("="):
            cell.data_type = "s"
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        cell.border = _BORDER


def _add_status_cf(ws, status_col_idx: int, max_row: int, num_cols: int) -> None:
    status_letter = get_column_letter(status_col_idx)
    data_range = f"A2:{get_column_letter(num_cols)}{max_row}"
    ws.conditional_formatting.add(data_range, FormulaRule(
        formula=[f'${status_letter}2="ready"'], fill=_GREEN,
    ))
    ws.conditional_formatting.add(data_range, FormulaRule(
        formula=[f'${status_letter}2="in_progress"'], fill=_YELLOW,
    ))
    ws.conditional_formatting.add(data_range, FormulaRule(
        formula=[f'${status_letter}2="complete"'], fill=_GRAY,
    ))


def create_workbook(
    path: Path,
    initiatives: List[Initiative],
    actions: Optional[list] = None,
    decisions: Optional[list] = None,
    meetings: Optional[list] = None,
    hypotheses: Optional[list] = None,
    facts: Optional[list] = None,
) -> None:
    wb = Workbook()
    init_names = {i.id: i.name for i in initiatives}

    # ── Tab 1: Dashboard ──────────────────────────────────────────────────────
    ws_dash = wb.active
    ws_dash.title = "Dashboard"
    _write_header_row(ws_dash, DASHBOARD_COLS)
    for row_num, init in enumerate(initiatives, start=2):
        _write_data_row(ws_dash, row_num, DASHBOARD_COLS, {
            "id": init.id, "name": init.name, "status": init.status,
            "priority": init.priority or "", "owner": init.owner or "",
            "last_touched": init.last_touched.isoformat(),
            "current_state": init.current_state or "",
        })
    status_col = DASHBOARD_COLS.index("status") + 1
    _add_status_cf(ws_dash, status_col, max(2, 1 + len(initiatives)), len(DASHBOARD_COLS))
    ws_dash.column_dimensions["B"].width = 32
    ws_dash.column_dimensions["C"].width = 14
    ws_dash.column_dimensions["G"].width = 40
    ws_dash.freeze_panes = "B2"

    # ── Tab 2: Initiatives ────────────────────────────────────────────────────
    ws_init = wb.create_sheet("Initiatives")
    _write_header_row(ws_init, INITIATIVE_COLS)
    for row_num, init in enumerate(initiatives, start=2):
        _write_data_row(ws_init, row_num, INITIATIVE_COLS, {
            "id": init.id, "name": init.name, "status": init.status,
            "priority": init.priority or "", "owner": init.owner or "",
            "current_state": init.current_state or "",
            "next_steps": init.next_steps or "",
            "last_touched": init.last_touched.isoformat(),
            "last_touch_comment": init.last_touch_comment or "",
            "notes": init.notes or "",
        })
    status_col = INITIATIVE_COLS.index("status") + 1
    _add_status_cf(ws_init, status_col, max(2, 1 + len(initiatives)), len(INITIATIVE_COLS))
    ws_init.column_dimensions["B"].width = 32
    ws_init.column_dimensions["F"].width = 40
    ws_init.column_dimensions["G"].width = 40
    ws_init.freeze_panes = "B2"

    # ── Tab 3: Actions & Decisions ────────────────────────────────────────────
    ws_ad = wb.create_sheet("Actions & Decisions")
    _write_header_row(ws_ad, ACT_DEC_COLS)
    combined = []
    for a in (actions or []):
        combined.append({
            "type": "action",
            "initiative": init_names.get(a.get("initiative_id", ""), a.get("initiative_id", "")),
            "description": a.get("description", ""),
            "owner": a.get("owner", ""),
            "due_or_rationale": a.get("due", ""),
            "status": a.get("status", ""),
            "created": a.get("created", ""),
            "source": a.get("source", ""),
        })
    for dec in (decisions or []):
        combined.append({
            "type": "decision",
            "initiative": init_names.get(dec.get("initiative_id", ""), dec.get("initiative_id", "")),
            "description": dec.get("decision", ""),
            "owner": dec.get("owner", ""),
            "due_or_rationale": dec.get("rationale", ""),
            "status": dec.get("status", ""),
            "created": dec.get("created", ""),
            "source": dec.get("source", ""),
        })
    for row_num, record in enumerate(combined, start=2):
        _write_data_row(ws_ad, row_num, ACT_DEC_COLS, record)
    ws_ad.column_dimensions["B"].width = 28
    ws_ad.column_dimensions["C"].width = 50
    ws_ad.freeze_panes = "A2"

    # ── Tab 4: Meetings ───────────────────────────────────────────────────────
    ws_m = wb.create_sheet("Meetings")
    _write_header_row(ws_m, MEETING_COLS)
    for row_num, m in enumerate(meetings or [], start=2):
        attendees = m.get("attendees") or []
        if isinstance(attendees, list):
            attendees = ", ".join(attendees)
        _write_data_row(ws_m, row_num, MEETING_COLS, {
            "initiative": init_names.get(m.get("initiative_id", ""), m.get("initiative_id", "")),
            "purpose": m.get("purpose", ""),
            "attendees": attendees,
            "status": m.get("status", ""),
            "created": m.get("created", ""),
            "source": m.get("source", ""),
        })
    ws_m.column_dimensions["B"].width = 50
    ws_m.freeze_panes = "A2"

    # ── Tab 5: Hypotheses ─────────────────────────────────────────────────────
    ws_hyp = wb.create_sheet("Hypotheses")
    _write_header_row(ws_hyp, HYPOTHESIS_COLS)
    project_rows = [h for h in (hypotheses or []) if not h.get("initiative_id")]
    initiative_rows = sorted(
        [h for h in (hypotheses or []) if h.get("initiative_id")],
        key=lambda h: init_names.get(h["initiative_id"], h["initiative_id"]),
    )
    for row_num, h in enumerate(project_rows + initiative_rows, start=2):
        iid = h.get("initiative_id")
        _write_data_row(ws_hyp, row_num, HYPOTHESIS_COLS, {
            "level": "Project" if not iid else "Initiative",
            "initiative": init_names.get(iid, "") if iid else "",
            "hypothesis": h.get("hypothesis", ""),
            "owner": h.get("owner", ""),
            "validation_path": h.get("validation_path", ""),
            "status": h.get("status", ""),
            "created": h.get("created", ""),
            "source": h.get("source", ""),
        })
    ws_hyp.column_dimensions["C"].width = 60
    ws_hyp.freeze_panes = "A2"

    # ── Tab 6: Facts ──────────────────────────────────────────────────────────
    ws_f = wb.create_sheet("Facts")
    _write_header_row(ws_f, FACT_COLS)
    for row_num, f in enumerate(facts or [], start=2):
        iid = f.get("initiative_id")
        _write_data_row(ws_f, row_num, FACT_COLS, {
            "initiative": init_names.get(iid, iid or ""),
            "claim": f.get("claim", ""),
            "stated_by": f.get("stated_by", ""),
            "created": f.get("created", ""),
            "source": f.get("source", ""),
        })
    ws_f.column_dimensions["B"].width = 60
    ws_f.freeze_panes = "A2"

    wb.save(path)
