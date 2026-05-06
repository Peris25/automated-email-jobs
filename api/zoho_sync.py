"""
Zoho sync routes — manual trigger + upsert helper used by scheduler.

POST /api/zoho/sync   → trigger a manual sync right now
GET  /api/zoho/status → connection health check
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from db.database import database, jobs as jobs_table
from api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


async def upsert_jobs_from_zoho(zoho_jobs: list[dict]) -> dict:
    """
    Shared upsert logic used by both manual trigger and scheduler.
    Inserts new jobs; updates metadata of existing ones.
    Preserves email tracking state (emails_sent, status, etc.).
    """
    now_iso  = datetime.now(timezone.utc).isoformat()
    inserted = 0
    updated  = 0

    for job in zoho_jobs:
        job_id = str(job.get("id", "")).strip()
        if not job_id:
            continue

        existing = await database.fetch_one(
            jobs_table.select().where(jobs_table.c.id == job_id)
        )

        base = {
            "vehicle_reg":      str(job.get("vehicle_reg", "")).strip(),
            "client_name":      str(job.get("client_name", "")).strip(),
            "client_email":     str(job.get("client_email", "")).strip().lower(),
            "client_phone":     job.get("client_phone"),
            "phase":            int(job.get("phase", 1)),
            "reason":           job.get("reason"),
            "initiated_date":   job.get("initiated_date"),
            "scheduled_date":   job.get("scheduled_date"),
            "solver_name":      job.get("solver_name"),
            "solver_phone":     job.get("solver_phone"),
            "job_status":       job.get("job_status", "pending"),
            "reason_logged_at": job.get("reason_logged_at") or now_iso,
            "source":           "zoho",
            "zoho_row_id":      job.get("zoho_row_id"),
            "updated_at":       now_iso,
        }

        if existing:
            # Only update if job is still pending (don't overwrite manual resolutions)
            if existing["job_status"] == "pending":
                await database.execute(
                    jobs_table.update()
                    .where(jobs_table.c.id == job_id)
                    .values(**base)
                )
                updated += 1
        else:
            await database.execute(
                jobs_table.insert().values(
                    **base,
                    id              = job_id,
                    emails_sent     = 0,
                    status          = "awaiting_reply",
                    flagged_manual  = False,
                    created_at      = now_iso,
                )
            )
            inserted += 1

    return {"inserted": inserted, "updated": updated}


@router.post("/sync")
async def manual_zoho_sync(user=Depends(get_current_user)):
    """Trigger an immediate Zoho sync."""
    from services.zoho import fetch_zoho_jobs, check_zoho_connection

    health = await check_zoho_connection()
    if health["status"] != "connected":
        raise HTTPException(
            status_code=503,
            detail=f"Zoho not connected: {health.get('error', 'unknown error')}. "
                   "Check ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN env vars."
        )

    try:
        jobs = await fetch_zoho_jobs()
        result = await upsert_jobs_from_zoho(jobs)
        logger.info(f"Manual Zoho sync: {result}")
        return {"ok": True, "fetched": len(jobs), **result}
    except Exception as e:
        logger.error(f"Manual Zoho sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def zoho_status(user=Depends(get_current_user)):
    from services.zoho import check_zoho_connection
    return await check_zoho_connection()
