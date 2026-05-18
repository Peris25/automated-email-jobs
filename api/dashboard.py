"""Dashboard KPIs and chart data routes."""

from fastapi import APIRouter, Depends
from datetime import datetime, timedelta, timezone, date
from db.database import database, jobs as jobs_table, email_log as email_log_table
from api.auth import get_current_user
import sqlalchemy as sa

router = APIRouter()


@router.get("/dashboard/kpis")
async def get_kpis(user=Depends(get_current_user)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
    week_start  = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    # Pending counts
    pending_all = await database.fetch_all(
    jobs_table.select().where(jobs_table.c.job_status == "pending")
    )
    pending_total   = len(pending_all)
    pending_phase_1 = sum(1 for r in pending_all if r["phase"] == 1)
    pending_phase_2 = sum(1 for r in pending_all if r["phase"] == 2)

    # Emails today
    today_emails = await database.fetch_all(
        email_log_table.select().where(email_log_table.c.sent_at >= today_start)
    )
    emails_today          = len(today_emails)
    emails_today_first    = sum(1 for e in today_emails if e["template_key"] != "followup")
    emails_today_followup = sum(1 for e in today_emails if e["template_key"] == "followup")

    # Reply rate (7 day)
    week_emails = await database.fetch_all(
        email_log_table.select().where(email_log_table.c.sent_at >= week_start)
    )
    replied = sum(1 for e in week_emails if e["delivery_status"] == "replied")
    reply_rate_7d = round((replied / len(week_emails) * 100) if week_emails else 0)

    # Resolved this week (job_status changed to completed/scheduled)
    resolved = await database.fetch_all(
        jobs_table.select().where(
            (jobs_table.c.job_status.in_(["completed", "scheduled"]))
            & (jobs_table.c.updated_at >= week_start)
        )
    )

    return {
        "pending_total":        pending_total,
        "pending_phase_1":      pending_phase_1,
        "pending_phase_2":      pending_phase_2,
        "emails_today":         emails_today,
        "emails_today_first":   emails_today_first,
        "emails_today_followup": emails_today_followup,
        "reply_rate_7d":        reply_rate_7d,
        "resolved_this_week":   len(resolved),
    }


@router.get("/charts/email-volume")
async def get_email_volume(days: int = 7, user=Depends(get_current_user)):
    labels, first_sends, followups = [], [], []

    for i in range(days - 1, -1, -1):
        day = datetime.now(timezone.utc) - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        day_end   = day.replace(hour=23, minute=59, second=59).isoformat()

        rows = await database.fetch_all(
            email_log_table.select().where(
                (email_log_table.c.sent_at >= day_start)
                & (email_log_table.c.sent_at <= day_end)
            )
        )
        labels.append(day.strftime("%b %-d"))
        first_sends.append(sum(1 for r in rows if r["template_key"] != "followup"))
        followups.append(sum(1 for r in rows if r["template_key"] == "followup"))

    return {"labels": labels, "first_send": first_sends, "followup": followups}


@router.get("/charts/reasons")
async def get_reason_breakdown(user=Depends(get_current_user)):
    rows = await database.fetch_all(
        jobs_table.select().where(jobs_table.c.job_status == "pending")
    )
    counts: dict = {}
    for r in rows:
        reason = r["reason"] or "unknown"
        counts[reason] = counts.get(reason, 0) + 1

    label_map = {
        "not_picking": "Not picking",
        "unreachable":  "Unreachable",
        "not_ready":    "Not ready",
    }
    return [
        {"reason": label_map.get(k, k), "count": v}
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    ]


@router.get("/integrations/status")
async def get_integration_status(user=Depends(get_current_user)):
    """Health check for the settings panel integration cards."""
    from services.graph import check_graph_connection
    from services.zoho import check_zoho_connection
    import os

    graph_status = await check_graph_connection()
    zoho_status  = await check_zoho_connection()

    return {
        "graph":       graph_status,
        "zoho":        zoho_status,
        "data_source": os.getenv("DATA_SOURCE", "csv"),
        "sender_upn":  os.getenv("MS_SENDER_UPN", "cs-team@solvit.co.ke"),
    }
