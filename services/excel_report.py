"""
Excel report builder — solver pending jobs (v1.5)
==================================================
Builds a styled Excel workbook for a solver's pending jobs and
returns the raw bytes so the caller can attach it to an email.

Uses openpyxl (already in requirements.txt).

Public API:
    build_solver_excel(solver_name, jobs, phase) -> bytes
"""

import io
from datetime import datetime, timezone

import openpyxl
from openpyxl.styles import (
    PatternFill, Font, Alignment, Border, Side, GradientFill
)
from openpyxl.utils import get_column_letter

# ── Colour palette ────────────────────────────────────────────
SOLVIT_BLUE   = "1A4B8C"        # header background
SOLVIT_ORANGE = "E8751A"        # accent / highlight
WHITE         = "FFFFFF"
LIGHT_GREY    = "F5F5F5"        # alternate row
DARK_GREY     = "333333"        # header text

# Reason badge colours (fill, font)
REASON_COLOURS = {
    "not_picking": ("FAEEDA", "663007"),
    "unreachable": ("FCEBEB", "791F1F"),
    "not_ready":   ("E6F1FB", "0C447C"),
    "call_back":   ("E8E6E0", "4A463E"),
    "no_logbook":  ("EFE6FB", "4A1F7C"),
    "no_sticker":  ("F5EAF5", "5C1F4A"),
    "no_letter":   ("F0E6F0", "441C44"),
}

REASON_LABELS = {
    "not_picking": "Not picking",
    "unreachable": "Unreachable",
    "not_ready":   "Not ready",
    "call_back":   "Call back",
    "no_logbook":  "No logbook",
    "no_sticker":  "No sticker",
    "no_letter":   "No letter",
}

PHASE_LABELS = {1: "Scheduling", 2: "Inspection", 3: "Approval"}


def _thin_border():
    s = Side(style="thin", color="DDDDDD")
    return Border(left=s, right=s, top=s, bottom=s)


def _phone_display(raw: str | None) -> str:
    """Format a bare Kenyan phone to 07XX XXX XXX for readability."""
    if not raw:
        return "—"
    digits = "".join(c for c in str(raw) if c.isdigit())
    if len(digits) == 9 and not digits.startswith("0"):
        digits = "0" + digits   # 722437964 → 0722437964
    if len(digits) == 10:
        return f"{digits[:4]} {digits[4:7]} {digits[7:]}"
    return str(raw)


# Urgency colour palette for the "Pending Since" column
PENDING_COLOURS = {
    "critical": ("FCEBEB", "791F1F"),   # 5+ days — red
    "warning":  ("FAEEDA", "663007"),   # 2-4 days — amber
    "ok":       ("E1F5EE", "0F6E56"),   # under 2 days — green
    "unknown":  ("F0F0F0", "666666"),   # no date on record — grey
}


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _pending_since(raw_date: str | None, now: datetime) -> tuple[str, str, float]:
    """
    Returns (display_text, urgency_key, age_in_seconds).
    display_text shows the original date plus a human "X days ago" so the
    solver immediately sees how long the job has been sitting in their basket.
    """
    dt = _parse_dt(raw_date)
    if dt is None:
        return ("—", "unknown", 0.0)

    delta = now - dt
    age_seconds = delta.total_seconds()

    if age_seconds < 0:
        # Timestamp is in the future — treat as just logged
        return (dt.strftime("%d %b %Y"), "ok", 0.0)

    days  = delta.days
    hours = delta.seconds // 3600

    if days == 0:
        rel = "Just now" if hours < 1 else f"{hours}h ago"
    elif days == 1:
        rel = "1 day ago"
    else:
        rel = f"{days} days ago"

    if days >= 5:
        urgency = "critical"
    elif days >= 2:
        urgency = "warning"
    else:
        urgency = "ok"

    display = f"{dt.strftime('%d %b %Y')}  ({rel})"
    return (display, urgency, age_seconds)


def build_solver_excel(solver_name: str, jobs: list[dict], phase: int) -> bytes:
    """
    Build a styled Excel workbook for one solver's pending jobs.
    Returns raw .xlsx bytes ready to attach to an email.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pending Jobs"

    phase_label = PHASE_LABELS.get(phase, f"Phase {phase}")
    generated   = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    # ── Row 1: Solvit branding banner ────────────────────────
    ws.merge_cells("A1:G1")
    banner = ws["A1"]
    banner.value = "Solvit Vehicle Valuations"
    banner.font  = Font(name="Calibri", bold=True, size=16, color=WHITE)
    banner.fill  = PatternFill("solid", fgColor=SOLVIT_BLUE)
    banner.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    # ── Row 2: Report title ───────────────────────────────────
    ws.merge_cells("A2:G2")
    title = ws["A2"]
    title.value = f"Pending {phase_label} Jobs — {solver_name}"
    title.font  = Font(name="Calibri", bold=True, size=13, color=WHITE)
    title.fill  = PatternFill("solid", fgColor=SOLVIT_ORANGE)
    title.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 26

    # ── Row 3: Meta line (date + count) ──────────────────────
    ws.merge_cells("A3:G3")
    meta = ws["A3"]
    n = len(jobs)
    meta.value = f"Generated: {generated}   |   Total pending: {n} {'job' if n == 1 else 'jobs'}"
    meta.font  = Font(name="Calibri", italic=True, size=10, color="666666")
    meta.alignment = Alignment(horizontal="center", vertical="center")
    meta.fill  = PatternFill("solid", fgColor="F0F0F0")
    ws.row_dimensions[3].height = 18

    # ── Row 4: Colour-key legend for the Pending Since column ────
    ws.merge_cells("A4:G4")
    legend = ws["A4"]
    legend.value = (
        "Pending Since colour key:   "
        "🔴 5+ days — please prioritise    "
        "🟠 2–4 days    "
        "🟢 Under 2 days"
    )
    legend.font = Font(name="Calibri", italic=True, size=9, color="777777")
    legend.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[4].height = 16

    # ── Row 5: Column headers ─────────────────────────────────
    headers = ["#", "Vehicle Reg", "Client Name", "Client Phone", "Reason", "Pending Since", "Notes"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col)
        cell.value = h
        cell.font  = Font(name="Calibri", bold=True, size=11, color=WHITE)
        cell.fill  = PatternFill("solid", fgColor=SOLVIT_BLUE)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)
        cell.border = _thin_border()
    ws.row_dimensions[5].height = 22

    # ── Data rows ─────────────────────────────────────────────
    # "now" is fixed once so every row's age is computed against the same
    # moment (the time this report was generated).
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    def _age_seconds_for_sort(j: dict) -> float:
        _, _, age = _pending_since(j.get("scheduled_date"), now)
        return age

    # Group by reason (keeps the same follow-up approach together), but
    # within each reason show the OLDEST pending jobs first — those are
    # the ones most in need of a solver's attention.
    sorted_jobs = sorted(
        jobs,
        key=lambda j: (j.get("reason") or "", -_age_seconds_for_sort(j))
    )

    for i, job in enumerate(sorted_jobs, 1):
        row  = i + 5            # data starts at row 6
        is_alt = (i % 2 == 0)
        bg   = LIGHT_GREY if is_alt else WHITE

        reason_code = (job.get("reason") or "").lower()
        reason_label = REASON_LABELS.get(reason_code, reason_code.replace("_", " ").title())

        # Missing-docs override for Approval phase
        if phase == 3 and job.get("missing_documents"):
            docs = [d.strip() for d in job["missing_documents"].split(",")]
            reason_label = "Missing: " + ", ".join(
                REASON_LABELS.get(d, d.replace("_", " ").title()) for d in docs
            )
            reason_code = docs[0] if docs else reason_code

        pending_display, urgency, _ = _pending_since(job.get("scheduled_date"), now)

        row_data = [
            i,
            (job.get("vehicle_reg") or "").upper(),
            (job.get("client_name") or "Client").strip() or "Client",
            _phone_display(job.get("client_phone")),
            reason_label,
            pending_display,
            "",           # Notes — blank for solver to fill in
        ]

        for col, val in enumerate(row_data, 1):
            cell = ws.cell(row=row, column=col)
            cell.value  = val
            cell.border = _thin_border()
            cell.alignment = Alignment(vertical="center", wrap_text=False)

            # Background — reason cell gets its own colour, others use alt-row
            if col == 5:
                rc = REASON_COLOURS.get(reason_code, ("F5F5F5", "333333"))
                cell.fill = PatternFill("solid", fgColor=rc[0])
                cell.font = Font(name="Calibri", size=10, color=rc[1], bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col == 6:
                pc = PENDING_COLOURS.get(urgency, PENDING_COLOURS["unknown"])
                cell.fill = PatternFill("solid", fgColor=pc[0])
                cell.font = Font(name="Calibri", size=10, color=pc[1], bold=(urgency == "critical"))
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col == 1:
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.font = Font(name="Calibri", size=10, color="999999")
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col == 2:
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.font = Font(name="Calibri", size=11, bold=True, color=DARK_GREY)
                cell.alignment = Alignment(horizontal="left", vertical="center")
            elif col == 3:
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.font = Font(name="Calibri", size=10, color=DARK_GREY)
                cell.alignment = Alignment(horizontal="left", vertical="center")
            elif col == 4:
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.font = Font(name="Calibri", size=10, color=DARK_GREY)
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col == 7:
                # Notes column — lighter styling, borderBottom only
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.font = Font(name="Calibri", size=10, color="BBBBBB", italic=True)
                cell.value = "—"
            else:
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.font = Font(name="Calibri", size=10, color=DARK_GREY)
                cell.alignment = Alignment(horizontal="center", vertical="center")

        ws.row_dimensions[row].height = 20

    # ── Auto-fit column widths ────────────────────────────────
    col_widths = [4, 16, 24, 18, 26, 26, 20]
    for col, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    # ── Freeze panes (keep header visible when scrolling) ─────
    ws.freeze_panes = "A6"

    # ── Totals row ────────────────────────────────────────────
    total_row = len(sorted_jobs) + 6
    ws.merge_cells(f"A{total_row}:D{total_row}")
    total_cell = ws[f"A{total_row}"]
    total_cell.value = f"Total: {len(sorted_jobs)} pending {'job' if len(sorted_jobs) == 1 else 'jobs'}"
    total_cell.font  = Font(name="Calibri", bold=True, size=10, color=WHITE)
    total_cell.fill  = PatternFill("solid", fgColor=SOLVIT_BLUE)
    total_cell.alignment = Alignment(horizontal="center", vertical="center")
    for col in range(5, 8):
        c = ws.cell(row=total_row, column=col)
        c.fill = PatternFill("solid", fgColor=SOLVIT_BLUE)
    ws.row_dimensions[total_row].height = 20

    # ── Page setup (for printing) ─────────────────────────────
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage   = True
    ws.page_setup.fitToWidth  = 1
    ws.print_title_rows       = "5:5"   # repeat header on each page

    # ── Sheet tab colour ──────────────────────────────────────
    ws.sheet_properties.tabColor = SOLVIT_ORANGE

    # ── Render to bytes ───────────────────────────────────────
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()
