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
    return (p or "—").strip() or "—"


def _format_jobs_table(jobs: list[dict]) -> str:
    lines = []
    lines.append("Vehicle reg     Client                          Phone               Reason")
    lines.append("-" * 95)
    for j in jobs:
        reg    = (j.get("vehicle_reg") or "—")[:15].ljust(15)
        client = (j.get("client_name") or "—")[:30].ljust(30)
        phone  = _format_phone(j.get("client_phone"))[:18].ljust(18)
        if j.get("phase") == 3 and j.get("missing_documents"):
            docs = j["missing_documents"].split(",")
            reason_str = "Missing: " + ", ".join(REASON_LABELS.get(d.strip(), d.strip()) for d in docs)
        else:
            reason_str = REASON_LABELS.get(j.get("reason") or "", j.get("reason") or "—")
        lines.append(f"{reg} {client} {phone} {reason_str}")
    return "\n".join(lines)


def _build_email_body(solver_name: str, jobs: list[dict], phase: int) -> str:
    phase_label = PHASE_LABELS.get(phase, f"Phase {phase}")
    n = len(jobs)
    plural = "job" if n == 1 else "jobs"
    table = _format_jobs_table(jobs)

    return f"""Dear {solver_name},

You currently have {n} pending {plural} at the {phase_label} stage that need follow-up.
The list below shows the vehicle, client contact, and the reason recorded so you can prioritise your day:

{table}

Please call each client to follow up and update the system once the situation has changed. Reducing turnaround on these pending items directly improves our overall submission rate.

Warm regards,
Solvit AM Team"""


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
        body    = _build_email_body(solver_name, jobs_sorted, phase)
        anchor_job_id = jobs_sorted[0].get("id") or "BULK"

        # Actually send the summary via Microsoft Graph. cc_emails may be a
        # comma-separated string ("cs-team@solvit.co.ke"); send_email wants a list.
        cc_list = [c.strip() for c in (cc_emails or "").split(",") if c.strip()]
        try:
            result = await send_email(email_addr, subject, body, cc_emails=cc_list or None)
            status = "sent"
        except Exception as e:
            result = {}
            status = "failed"
            warnings.append(
                f"Failed to send summary to {solver_name} <{email_addr}>: {e}"
            )
            logger.error(
                f"Solver summary send failed: {solver_name} <{email_addr}> — {e}"
            )

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
