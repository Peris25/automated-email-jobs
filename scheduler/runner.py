"""
Scheduler — runs background jobs on a timer.
  • Every 15 min: email dispatcher (send first emails + follow-ups)
  • Every  5 min: reply processor (poll inbox, match to jobs)
  • Every 15 min: Zoho sync (if DATA_SOURCE=zoho)

Uses APScheduler's AsyncIOScheduler so it runs in the same event loop
as FastAPI — no extra processes needed on Render.
"""

import os
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

DATA_SOURCE = os.getenv("DATA_SOURCE", "csv")   # "csv" or "zoho"

scheduler = AsyncIOScheduler()


async def _run_dispatcher():
    from services.dispatcher import run_email_dispatcher
    await run_email_dispatcher()


async def _run_reply_processor():
    from services.dispatcher import process_replies
    await process_replies()


async def _run_zoho_sync():
    from services.zoho import fetch_zoho_jobs
    from api.zoho_sync import upsert_jobs_from_zoho
    try:
        jobs = await fetch_zoho_jobs()
        await upsert_jobs_from_zoho(jobs)
        logger.info(f"Zoho auto-sync: {len(jobs)} jobs upserted")
    except Exception as e:
        logger.error(f"Zoho auto-sync failed: {e}")


def start_scheduler():
    # Email dispatcher — every 15 minutes
    scheduler.add_job(
        _run_dispatcher,
        trigger=IntervalTrigger(minutes=15),
        id="email_dispatcher",
        replace_existing=True,
        max_instances=1,
    )

    # Reply processor — every 5 minutes
    scheduler.add_job(
        _run_reply_processor,
        trigger=IntervalTrigger(minutes=5),
        id="reply_processor",
        replace_existing=True,
        max_instances=1,
    )

    # Zoho sync — every 15 minutes (only if configured)
    if DATA_SOURCE == "zoho":
        scheduler.add_job(
            _run_zoho_sync,
            trigger=IntervalTrigger(minutes=15),
            id="zoho_sync",
            replace_existing=True,
            max_instances=1,
        )
        logger.info("Zoho auto-sync scheduled every 15 minutes")

    scheduler.start()
    logger.info(
        "Scheduler started. "
        f"Dispatcher: 15min | Reply poller: 5min | "
        f"Data source: {DATA_SOURCE}"
    )
