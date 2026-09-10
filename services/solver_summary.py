"""
Solver summary service (v1.3)
==============================
Builds a consolidated "your pending jobs" email per solver and writes
to email_log for dispatch by the existing email dispatcher.
"""

import logging
from datetime import datetime, timezone
from collections import defaultdict
from typing import Iterable

import sqlalchemy as sa

from db.database import database, solvers as solvers_table, email_log, phase_settings
from services.graph import send_email

logger = logging.getLogger(__name__)

REASON_LABELS = {
    "not_picking":  "Not picking",
    "unreachable":  "Unreachable",
    "not_ready":    "Not ready",
    "call_back":    "Call back",
    "no_logbook":   "No logbook",
    "no_sticker":   "No sticker",
    "no_letter":    "No letter",
}

PHASE_LABELS = {1: "Scheduling", 2: "Inspection", 3: "Approval"}


async def is_solver_summary_enabled(phase: int) -> bool:
    row = await database.fetch_one(
        phase_settings.select().where(phase_settings.c.phase == phase)
    )
    if not row:
        return False
    return bool(row["solver_summary_enabled"])


async def _resolve_solver_email(solver_name: str, fallback_email: str | None) -> str | None:
    if fallback_email and "@" in fallback_email:
        return fallback_email.strip().lower()
    if not solver_name:
        return None
    row = await database.fetch_one(
        solvers_table.select().where(
            (sa.func.lower(solvers_table.c.name) == solver_name.strip().lower()) &
            (solvers_table.c.active == True)
        )
    )
    return row["email"] if row else None


def _format_phone(p: str | None) -> str:
    """Format a bare Kenyan phone number for readability: 07XX XXX XXX"""
    if not p:
        return "—"
    digits = "".join(c for c in str(p) if c.isdigit())
    if len(digits) == 9 and not digits.startswith("0"):
        digits = "0" + digits   # 722437964 → 0722437964
    if len(digits) == 10:
        return f"{digits[:4]} {digits[4:7]} {digits[7:]}"
    return str(p)


def _build_email_body_html(solver_name: str, jobs: list[dict], phase: int) -> str:
    """
    Clean HTML email body for the solver summary.
    The Excel attachment carries the full detail; the email body
    is a concise brief that works well on mobile.
    """
    phase_label = PHASE_LABELS.get(phase, f"Phase {phase}")
    n = len(jobs)
    plural = "job" if n == 1 else "jobs"

    # Build a compact HTML table — key info only
    rows_html = ""
    sorted_jobs = sorted(jobs, key=lambda j: (j.get("reason") or "", j.get("vehicle_reg") or ""))
    for i, j in enumerate(sorted_jobs, 1):
        bg = "#F9F9F9" if i % 2 == 0 else "#FFFFFF"
        reg   = (j.get("vehicle_reg") or "—").upper()
        phone = _format_phone(j.get("client_phone"))
        reason_code = (j.get("reason") or "").lower()

        if phase == 3 and j.get("missing_documents"):
            docs = [d.strip() for d in j["missing_documents"].split(",")]
            reason_label = "Missing: " + ", ".join(
                REASON_LABELS.get(d, d.replace("_", " ").title()) for d in docs
            )
        else:
            reason_label = REASON_LABELS.get(reason_code, reason_code.replace("_", " ").title())

        # Reason badge colours
        rc = {
            "not_picking": ("#FAEEDA", "#663007"),
            "unreachable": ("#FCEBEB", "#791F1F"),
            "not_ready":   ("#E6F1FB", "#0C447C"),
            "call_back":   ("#E8E6E0", "#4A463E"),
            "no_logbook":  ("#EFE6FB", "#4A1F7C"),
            "no_sticker":  ("#F5EAF5", "#5C1F4A"),
            "no_letter":   ("#F0E6F0", "#441C44"),
        }.get(reason_code, ("#F0F0F0", "#444444"))

        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:10px 12px;font-size:13px;color:#333;font-weight:600;border-bottom:1px solid #eee;">{reg}</td>
          <td style="padding:10px 12px;font-size:13px;color:#555;border-bottom:1px solid #eee;">{phone}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;">
            <span style="background:{rc[0]};color:{rc[1]};padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">{reason_label}</span>
          </td>
        </tr>"""

    first_name = solver_name.split()[0].title() if solver_name else "Solver"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<div style="max-width:600px;margin:28px auto;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

  <!-- Header -->
  <div style="background:#1A4B8C;padding:24px 28px;">
    <div style="font-size:11px;color:rgba(255,255,255,0.6);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Solvit Vehicle Valuations</div>
    <div style="font-size:20px;color:#ffffff;font-weight:700;">Your pending {phase_label.lower()} {plural}</div>
  </div>

  <!-- Orange accent bar -->
  <div style="background:#E8751A;height:4px;"></div>

  <!-- Body -->
  <div style="padding:28px;">
    <p style="margin:0 0 18px;font-size:15px;color:#333;">
      Hi <strong>{first_name}</strong>, you have <strong>{n} pending {plural}</strong> at the
      {phase_label} stage. Your full list is attached as an Excel file — please open it
      for the complete details and use it to track your follow-ups.
    </p>

    <!-- Quick-reference table -->
    <div style="margin:0 0 22px;">
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border-radius:6px;overflow:hidden;border:1px solid #e8e8e8;">
        <thead>
          <tr style="background:#1A4B8C;">
            <th style="padding:10px 12px;font-size:11px;color:#ffffff;text-align:left;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;">Vehicle</th>
            <th style="padding:10px 12px;font-size:11px;color:#ffffff;text-align:left;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;">Client phone</th>
            <th style="padding:10px 12px;font-size:11px;color:#ffffff;text-align:left;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;">Reason</th>
          </tr>
        </thead>
        <tbody>{rows_html}
        </tbody>
      </table>
    </div>

    <p style="margin:0 0 16px;font-size:13px;color:#555;line-height:1.6;">
      Please call each client to follow up and update the system once the situation changes.
      Clearing these pending items improves our overall submission rate and TAT.
    </p>

    <div style="background:#FFF8F0;border-left:4px solid #E8751A;padding:12px 16px;border-radius:0 6px 6px 0;margin-bottom:20px;">
      <p style="margin:0;font-size:13px;color:#663007;">
        <strong>📎 Excel attached:</strong> Open the attached file for a printable, sortable version of your pending jobs list.
      </p>
    </div>

    <p style="margin:0;font-size:13px;color:#777;">
      Warm regards,<br>
      <strong style="color:#333;">Solvit AM Team</strong><br>
      <span style="color:#999;font-size:12px;">cs-team@solvit.co.ke</span>
    </p>
  </div>

  <!-- Footer -->
  <div style="background:#f9f9f9;border-top:1px solid #eee;padding:16px 28px;font-size:11px;color:#aaa;text-align:center;">
    Solvit Ltd · Nairobi, Kenya · This is an automated message from the Solvit Communication Portal.
  </div>
</div>
</body>
</html>"""


def _build_email_subject(jobs: list[dict], phase: int) -> str:
    n = len(jobs)
    phase_label = PHASE_LABELS.get(phase, f"Phase {phase}")
    return f"Your {n} pending {phase_label.lower()} {'job' if n==1 else 'jobs'} — follow-up list"


async def build_solver_summaries(
    jobs_for_summary: Iterable[dict],
    upload_id: int | None,
    phase: int,
    cc_emails: str = "cs-team@solvit.co.ke",
) -> dict:
    by_solver: dict[str, list[dict]] = defaultdict(list)
    name_canonical: dict[str, str] = {}

    for job in jobs_for_summary:
        sname = (job.get("solver_name") or "").strip()
        if not sname:
            continue
        key = sname.lower()
        if key not in name_canonical:
            name_canonical[key] = sname
        by_solver[key].append(job)

    warnings: list[str] = []
    summaries_queued = 0
    jobs_covered = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for key, jobs in by_solver.items():
        solver_name = name_canonical[key]
        explicit_email = next(
            (j.get("solver_email") for j in jobs if (j.get("solver_email") or "").strip()),
            None,
        )
        email_addr = await _resolve_solver_email(solver_name, explicit_email)

        if not email_addr:
            warnings.append(
                f"Could not send summary to {solver_name} — not found in solver directory "
                f"and no email in export ({len(jobs)} jobs skipped)."
            )
            continue

        jobs_sorted = sorted(jobs, key=lambda j: (j.get("reason") or "", j.get("vehicle_reg") or ""))
        subject = _build_email_subject(jobs_sorted, phase)
        body    = _build_email_body_html(solver_name, jobs_sorted, phase)

        # Build the Excel attachment
        attachment = None
        try:
            from services.excel_report import build_solver_excel
            from datetime import datetime as _dt
            date_str = _dt.now().strftime("%Y-%m-%d")
            safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in solver_name)
            filename  = f"Pending_{PHASE_LABELS.get(phase,'Phase')}_Jobs_{safe_name}_{date_str}.xlsx"
            xlsx_bytes = build_solver_excel(solver_name, jobs_sorted, phase)
            attachment = {
                "name":          filename,
                "content_type":  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "content_bytes": xlsx_bytes,
            }
        except Exception as e:
            logger.warning(f"Excel build failed for {solver_name}: {e} — sending without attachment")

        anchor_job_id = jobs_sorted[0].get("id") or "BULK"
        cc_list = [c.strip() for c in (cc_emails or "").split(",") if c.strip()]

        try:
            result = await send_email(
                email_addr, subject, body,
                cc_emails=[*cc_list] or None,
                attachments=[attachment] if attachment else None,
            )
            status = "sent"
        except Exception as e:
            result = {}
            status = "failed"
            warnings.append(f"Failed to send summary to {solver_name} <{email_addr}>: {e}")
            logger.error(f"Solver summary send failed: {solver_name} <{email_addr}> — {e}")

        await database.execute(
            email_log.insert().values(
                job_id              = anchor_job_id,
                sent_at             = now_iso,
                template_key        = "solver_summary",
                subject             = subject,
                to_email            = email_addr,
                cc_emails           = cc_emails,
                graph_message_id    = result.get("graph_message_id", ""),
                internet_message_id = result.get("internet_message_id", ""),
                delivery_status     = status,
            )
        )

        if status == "sent":
            summaries_queued += 1
            jobs_covered    += len(jobs_sorted)
            logger.info(
                f"Sent solver summary: {solver_name} <{email_addr}> "
                f"with {len(jobs_sorted)} jobs (upload_id={upload_id}, phase={phase})"
            )

    return {
        "summaries_queued": summaries_queued,
        "jobs_covered":     jobs_covered,
        "warnings":         warnings,
    }


async def auto_register_solver_from_export(name: str, email: str | None, phone: str | None = None):
    if not name or not email or "@" not in email:
        return
    existing = await database.fetch_one(
        solvers_table.select().where(
            sa.func.lower(solvers_table.c.name) == name.strip().lower()
        )
    )
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        if not existing["email"]:
            await database.execute(
                solvers_table.update()
                .where(solvers_table.c.id == existing["id"])
                .values(email=email.strip().lower(), updated_at=now)
            )
        return
    try:
        await database.execute(
            solvers_table.insert().values(
                name=name.strip(),
                email=email.strip().lower(),
                phone=(phone or "").strip() or None,
                active=True,
                created_at=now, updated_at=now,
            )
        )
        logger.info(f"Auto-registered solver from export: {name} <{email}>")
    except Exception as e:
        logger.debug(f"Skipped auto-register for {name}: {e}")
