"""Jobs API routes."""

from fastapi import APIRouter, HTTPException, Depends
from db.database import database, jobs as jobs_table, email_log as email_log_table
from api.auth import get_current_user

router = APIRouter()


@router.get("/jobs")
async def list_jobs(user=Depends(get_current_user)):
    rows = await database.fetch_all(
        jobs_table.select()
        .where(jobs_table.c.job_status == "pending")
        .order_by(jobs_table.c.initiated_date)
    )
    return [r for r in rows]


@router.get("/jobs/all")
async def list_all_jobs(user=Depends(get_current_user)):
    """Return all jobs regardless of status — for full history view."""
    rows = await database.fetch_all(
        jobs_table.select().order_by(jobs_table.c.created_at.desc())
    )
    return [r for r in rows]


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user=Depends(get_current_user)):
    row = await database.fetch_one(
        jobs_table.select().where(jobs_table.c.id == job_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)


@router.get("/jobs/{job_id}/emails")
async def get_job_emails(job_id: str, user=Depends(get_current_user)):
    rows = await database.fetch_all(
        email_log_table.select()
        .where(email_log_table.c.job_id == job_id)
        .order_by(email_log_table.c.sent_at.desc())
    )
    return [r for r in rows]


@router.patch("/jobs/{job_id}/resolve")
async def resolve_job(job_id: str, user=Depends(get_current_user)):
    """Manually mark a job as completed."""
    from datetime import datetime, timezone
    await database.execute(
        jobs_table.update()
        .where(jobs_table.c.id == job_id)
        .values(job_status="completed", updated_at=datetime.now(timezone.utc).isoformat())
    )
    return {"ok": True}
