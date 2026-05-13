"""
Email dispatcher — the core automation engine.
=================================================
Called by the scheduler every 15 minutes.

Logic:
  1. Pull all pending jobs with a reason code and emails_sent < 2
  2. For each job, check timing rules (should_send_now)
  3. If yes → pick template, send via Graph, log to email_log
  4. 3-day follow-up: jobs with emails_sent=1, no reply, still pending
  5. Flag jobs at emails_sent=2 for manual handling
"""

import logging
from datetime import datetime, timedelta, timezone

from db.database import database, jobs as jobs_table, email_log as email_log_table
from services.graph import send_email
from services.templates import get_template

logger = logging.getLogger(__name__)


# ── Timing rules ──────────────────────────────────────────────

def should_send_now(job: dict) -> bool:
  """
  Phase 1 AM timing rules (EAT = UTC+3):
    unreachable / not_picking → send immediately (next 15-min cycle)
    anything else             → send only if 3+ days since reason_logged_at
  Phase 2 Solver → same logic, reason from latest_pending_reason
  """
  reason   = (job.get("reason") or "").lower()
  now_utc  = datetime.now(timezone.utc)
  now_eat  = now_utc + timedelta(hours=3)

  # Immediate triggers
  if reason in ("unreachable", "not_picking", "not_ready"):
      if reason == "not_ready":
          # 3 days still in initiated
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
      return True  # unreachable and not_picking → immediate

  # Any other reason → 3 days rule
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
    """Return True if 3+ days have passed since first email with no reply."""
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
    """Render template, send email, write to email_log, update job."""
    job_dict = dict(job)
    try:
        template_key, subject, body = get_template(job_dict, is_followup=is_followup)
    except ValueError as e:
        logger.warning(f"Job {job_dict.get('id')}: {e} — skipping")
        return

    to_email = job_dict.get("client_email", "")
    if not to_email:
        logger.warning(f"Job {job_dict.get('id')} has no client_email — skipping")
        return

    # Phase 2: CC the solver
    cc_list = []
    if job_dict.get("phase") == 2 and job_dict.get("solver_email"):
        cc_list.append(job_dict["solver_email"])

    try:
        result = await send_email(to_email, subject, body, cc_emails=cc_list or None)
    except Exception as e:
        logger.error(f"Failed to send email for job {job_dict.get('id')}: {e}")
        return

    now_iso = datetime.now(timezone.utc).isoformat()

    # Log to email_log
    await database.execute(
        email_log_table.insert().values(
            job_id            = job_dict["id"],
            sent_at           = now_iso,
            template_key      = template_key,
            subject           = subject,
            to_email          = to_email,
            graph_message_id  = result.get("graph_message_id", ""),
            internet_message_id = result.get("internet_message_id", ""),
            delivery_status   = "sent",
        )
    )

    # Update job
    new_count = int(job_dict.get("emails_sent", 0)) + 1
    update_vals = {
        "emails_sent":        new_count,
        "last_email_sent_at": now_iso,
        "updated_at":         now_iso,
    }
    if new_count >= 2:
        update_vals["flagged_manual"] = True

    await database.execute(
        jobs_table.update()
        .where(jobs_table.c.id == job_dict["id"])
        .values(**update_vals)
    )

    flag_note = " [FLAGGED FOR MANUAL]" if new_count >= 2 else ""
    logger.info(
        f"{'Follow-up' if is_followup else 'First'} email sent: "
        f"{job_dict['id']} → {to_email} | template={template_key}{flag_note}"
    )


# ── Main dispatcher loop ──────────────────────────────────────

async def run_email_dispatcher():
    """
    Called by the scheduler every 15 minutes.
    Evaluates all pending jobs and sends emails where timing rules pass.
    """
    logger.info("Email dispatcher running...")

    try:
        # Jobs that haven't had any email yet
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
            if should_send_now(dict(job)):
                await _dispatch(dict(job), is_followup=False)
                sent_count += 1

        # Jobs awaiting follow-up (3 days, no reply)
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
            if needs_followup(dict(job)):
                await _dispatch(dict(job), is_followup=True)
                followup_count += 1

        logger.info(
            f"Dispatcher complete: {sent_count} first sends, "
            f"{followup_count} follow-ups"
        )

    except Exception as e:
        logger.error(f"Dispatcher error: {e}", exc_info=True)


# ── Reply processor ───────────────────────────────────────────

async def process_replies():
    """
    Called every 5 minutes by the scheduler.
    Polls Graph inbox and matches replies to jobs via Message-ID threading.
    """
    from services.graph import fetch_unread_replies

    logger.info("Reply processor running...")
    try:
        replies = await fetch_unread_replies()
        matched = 0

        for reply in replies:
            in_reply_to = reply.get("in_reply_to")
            if not in_reply_to:
                continue

            # Find the email log entry with matching internet_message_id
            log_row = await database.fetch_one(
                email_log_table.select().where(
                    email_log_table.c.internet_message_id == in_reply_to
                )
            )
            if not log_row:
                # Fallback: try matching by from_email + awaiting_reply status
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
