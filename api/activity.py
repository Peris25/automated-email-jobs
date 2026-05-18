"""Activity log and live feed routes."""
from fastapi import APIRouter, Depends
from datetime import datetime, timedelta, timezone
from db.database import database, jobs as jobs_table, email_log as email_log_table
from api.auth import get_current_user
import sqlalchemy as sa

router = APIRouter()

@router.get("/activity")
async def get_activity(user=Depends(get_current_user)):
    rows = await database.fetch_all(
        sa.select(
            email_log_table.c.sent_at,
            jobs_table.c.client_name.label("client"),
            jobs_table.c.vehicle_reg.label("reg"),
            jobs_table.c.phase,
            email_log_table.c.template_key,
            email_log_table.c.delivery_status.label("status"),
        )
        .select_from(
            email_log_table.join(jobs_table, email_log_table.c.job_id == jobs_table.c.id)
        )
        .order_by(email_log_table.c.sent_at.desc())
        .limit(200)
    )
    result = []
    for r in rows:
        row = dict(r)
        row["type"] = "Follow-up" if row["template_key"] == "followup" else "First send"
        del row["template_key"]
        result.append(row)
    return result


@router.get("/feed/live")
async def get_live_feed(user=Depends(get_current_user)):
    """Last 30 minutes of activity for the dashboard feed."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:%S')

    rows = await database.fetch_all(
        sa.select(
            email_log_table.c.sent_at,
            email_log_table.c.template_key,
            email_log_table.c.delivery_status,
            jobs_table.c.client_name,
            jobs_table.c.vehicle_reg,
            jobs_table.c.phase,
        )
        .select_from(
            email_log_table.join(jobs_table, email_log_table.c.job_id == jobs_table.c.id)
        )
        .where(email_log_table.c.sent_at > cutoff)
        .order_by(email_log_table.c.sent_at.desc())
        .limit(30)
    )
    feed = []
    for r in rows:
        row = dict(r)
        status = row["delivery_status"]
        client = row["client_name"]
        reg    = row["vehicle_reg"]
        phase  = row["phase"]

        if status == "replied":
            feed_type = "reply"
            text = f"Reply received from {client} ({reg}) — phase {phase}"
        elif row["template_key"] == "followup":
            feed_type = "sent"
            text = f"Follow-up sent to {client} ({reg}) — phase {phase}"
        else:
            feed_type = "sent"
            text = f"Email sent to {client} ({reg}) — phase {phase} reminder"

        try:
            sent = datetime.fromisoformat(row["sent_at"])
            if sent.tzinfo is None:
                sent = sent.replace(tzinfo=timezone.utc)
            diff = int((datetime.now(timezone.utc) - sent).total_seconds() / 60)
            time_label = f"{diff} min ago" if diff < 60 else f"{diff // 60}h ago"
        except Exception:
            time_label = "recently"

        feed.append({"time": time_label, "type": feed_type, "text": text})
    return feed
