"""
Email dispatcher — the core automation engine.
"""

import logging
from datetime import datetime, timedelta, timezone

from db.database import database, jobs as jobs_table, email_log as email_log_table
from services.graph import send_email
from services.templates import get_template

logger = logging.getLogger(__name__)


# ── Timing rules ──────────────────────────────────────────────

def should_send_now(job: dict) -> bool:
    reason  = (job.get("reason") or "").lower()
    now_utc = datetime.now(timezone.utc)

    if reason in ("unreachable", "not_picking"):
        return True

    # not_ready and everything else → 3 days rule
    logged = job.get("reason_logged_at")
    if logged:
        try:
            dt = datetime.fromisoformat(str(logged))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (now_utc - dt) >= timedelta(days=3)
        except Exception:
            pass

    return False


def needs_followup(job: dict) -> bool:
    if job.get("emails_sent", 0) != 1:
        return False
    if job.get("status") != "awaiting_reply":
        return False
    if job.get("job_status") != "pending":
        return False

    last_sent = job.get("last_email_sent_at")
    if not last_sent:
        return False

    try:
        sent_dt = datetime.fromisoformat(str(last_sent))
        if sent_dt.tzinfo is None:
            sent_dt = sent_dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - sent_dt >= timedelta(days=3)
    except Exception:
        return False


# ── Sender ────────────────────────────────────────────────────

async def _dispatch(job: dict, is_followup: bool = False):
    try:
        template_key, subject, body = get_template(job, is_followup=is_followup)
    except ValueError as e:
        logger.warning(f"Job {job.get('id')}: {e} — skipping")
        return

    to_email = job.get("client_email", "")
    if not to_email:
        logger.warning(f"Job {job.get('id')} has no client_email — skipping")
        return

    cc_list = []
    if job.get("phase") == 2 and job.get("solver_email"):
        cc_list.append(job["solver_email"])

    try:
        result = await send_email(to_email, subject, body, cc_emails=cc_list or None)
    except Exception as e:
        logger.error(f"Failed to send email for job {job.get('id')}: {e}")
        return

    now_iso = datetime.now(timezone.utc).isoformat()

    await database.execute(
        email_log_table.insert().values(
            job_id              = job["id"],
            sent_at             = now_iso,
            template_key        = template_key,
            subject             = subject,
            to_email            = to_email,
            graph_message_id    = result.get("graph_message_id", ""),
            internet_message_id = result.get("internet_message_id", ""),
            delivery_status     = "sent",
        )
    )

    new_count = int(job.get("emails_sent", 0)) + 1
    update_vals = {
        "emails_sent":        new_count,
        "last_email_sent_at": now_iso,
        "updated_at":         now_iso,
    }
    if new_count >= 2:
        update_vals["flagged_manual"] = True

    await database.execute(
        jobs_table.update()
        .where(jobs_table.c.id == job["id"])
        .values(**update_vals)
    )

    flag_note = " [FLAGGED FOR MANUAL]" if new_count >= 2 else ""
    logger.info(
        f"{'Follow-up' if is_followup else 'First'} email sent: "
        f"{job['id']} → {to_email} | template={template_key}{flag_note}"
    )


# ── Main dispatcher loop ──────────────────────────────────────

async def run_email_dispatcher():
    logger.info("Email dispatcher running...")
    try:
        first_send_jobs = await database.fetch_all(
            jobs_table.select().where(
                (jobs_table.c.emails_sent == 0)
                & (jobs_table.c.job_status == "pending")
                & (jobs_table.c.reason != None)
                & (jobs_table.c.flagged_manual == False)
            )
        )

        sent_count = 0
        for job in first_send_jobs:
            if should_send_now(job):
                await _dispatch(job, is_followup=False)
                sent_count += 1

        followup_jobs = await database.fetch_all(
            jobs_table.select().where(
                (jobs_table.c.emails_sent == 1)
                & (jobs_table.c.status == "awaiting_reply")
                & (jobs_table.c.job_status == "pending")
                & (jobs_table.c.flagged_manual == False)
            )
        )

        followup_count = 0
        for job in followup_jobs:
            if needs_followup(job):
                await _dispatch(job, is_followup=True)
                followup_count += 1

        logger.info(
            f"Dispatcher complete: {sent_count} first sends, "
            f"{followup_count} follow-ups"
        )

    except Exception as e:
        logger.error(f"Dispatcher error: {e}", exc_info=True)


# ── Reply processor ───────────────────────────────────────────

async def process_replies():
    from services.graph import fetch_unread_replies

    logger.info("Reply processor running...")
    try:
        replies = await fetch_unread_replies()
        matched = 0

        for reply in replies:
            in_reply_to = reply.get("in_reply_to")
            if not in_reply_to:
                continue

            log_row = await database.fetch_one(
                email_log_table.select().where(
                    email_log_table.c.internet_message_id == in_reply_to
                )
            )
            if not log_row:
                from_email = reply.get("from_email", "")
                if from_email:
                    job_row = await database.fetch_one(
                        jobs_table.select().where(
                            (jobs_table.c.client_email == from_email)
                            & (jobs_table.c.status == "awaiting_reply")
                        )
                    )
                    if job_row:
                        await _mark_job_replied(job_row["id"], reply)
                        matched += 1
                continue

            await _mark_job_replied(log_row["job_id"], reply)
            matched += 1

        logger.info(f"Reply processor: {len(replies)} checked, {matched} matched")

    except Exception as e:
        logger.error(f"Reply processor error: {e}", exc_info=True)


async def _mark_job_replied(job_id: str, reply: dict):
    now_iso = datetime.now(timezone.utc).isoformat()

    await database.execute(
        jobs_table.update()
        .where(jobs_table.c.id == job_id)
        .values(status="replied", updated_at=now_iso)
    )

    await database.execute(
        email_log_table.update()
        .where(
            (email_log_table.c.job_id == job_id)
            & (email_log_table.c.delivery_status == "sent")
        )
        .values(delivery_status="replied", reply_at=now_iso)
    )

    logger.info(f"Job {job_id} marked as replied")
