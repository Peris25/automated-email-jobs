"""
Conversion analytics (v1.2 — now 3 phases)
==========================================
Compares two snapshots of the same jobs (taken at two different upload times)
to measure how many vehicles progressed through the pipeline between them.

Pipeline: Initiated → Scheduled → Inspected → Approved

Three phase-attributable conversions:
  - Scheduling : Initiated → (Scheduled / Inspected / Approved)
  - Inspection : Scheduled → (Inspected / Approved)
  - Approval   : Inspected → Approved  (i.e. docs received, report approved)

Attribution: only counts jobs the portal sent at least one email for between
the baseline and comparison upload.

Endpoints:
    GET /api/conversion                       — uses latest 2 uploads
    GET /api/conversion?baseline=42&latest=43 — explicit
    GET /api/conversion/uploads               — list of uploads for the picker
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
import sqlalchemy as sa

from db.database import (
    database,
    uploads as uploads_table,
    job_snapshots as snapshots_table,
    email_log as email_log_table,
)
from api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

PIPELINE_ORDER = ["Initiated", "Scheduled", "Inspected", "Approved"]
STATUS_INDEX = {s: i for i, s in enumerate(PIPELINE_ORDER)}


def _status_rank(status: str | None) -> int:
    if not status:
        return -1
    return STATUS_INDEX.get(status, -1)


def _classify_transition(baseline_status: str, latest_status: str) -> dict:
    b = _status_rank(baseline_status)
    l = _status_rank(latest_status)

    if b < 0 or l < 0 or l <= b:
        return {
            "any_forward":           False,
            "scheduling_conversion": False,
            "inspection_conversion": False,
            "approval_conversion":   False,
            "from_status":           baseline_status,
            "to_status":             latest_status,
        }

    return {
        "any_forward":           True,
        "scheduling_conversion": baseline_status == "Initiated",
        "inspection_conversion": baseline_status == "Scheduled" and l >= STATUS_INDEX["Inspected"],
        "approval_conversion":   baseline_status == "Inspected" and l >= STATUS_INDEX["Approved"],
        "from_status":           baseline_status,
        "to_status":             latest_status,
    }


async def _get_upload(upload_id: int) -> dict | None:
    return await database.fetch_one(
        uploads_table.select().where(uploads_table.c.id == upload_id)
    )


async def _latest_two_uploads() -> tuple[int | None, int | None]:
    rows = await database.fetch_all(
        uploads_table.select().order_by(sa.desc(uploads_table.c.uploaded_at)).limit(2)
    )
    if len(rows) < 2:
        return (None, rows[0]["id"] if rows else None)
    return (rows[1]["id"], rows[0]["id"])


@router.get("/conversion/uploads")
async def list_uploads_for_picker(user=Depends(get_current_user)):
    rows = await database.fetch_all(
        uploads_table.select().order_by(sa.desc(uploads_table.c.uploaded_at))
    )
    phase_label = {1: "Scheduling", 2: "Inspection", 3: "Approval"}
    return [
        {
            "id":             r["id"],
            "uploaded_at":    r["uploaded_at"],
            "filename":       r["filename"],
            "detected_phase": r["detected_phase"],
            "phase_label":    phase_label.get(r["detected_phase"], "?"),
            "row_count":      r["row_count"],
            "is_baseline":    r["is_baseline"],
            "label":          f"#{r['id']} · {r['uploaded_at'][:16]} · {phase_label.get(r['detected_phase'], '?')} · {r['row_count']} rows"
        }
        for r in rows
    ]


@router.get("/conversion")
async def get_conversion(
    baseline: int | None = None,
    latest:   int | None = None,
    user=Depends(get_current_user),
):
    if baseline is None and latest is None:
        explicit_baseline = await database.fetch_one(
            uploads_table.select().where(uploads_table.c.is_baseline == True)
        )
        if explicit_baseline:
            baseline = explicit_baseline["id"]
            recent = await database.fetch_all(
                uploads_table.select()
                .where(uploads_table.c.id != baseline)
                .order_by(sa.desc(uploads_table.c.uploaded_at))
                .limit(1)
            )
            latest = recent[0]["id"] if recent else None
        else:
            baseline, latest = await _latest_two_uploads()

    if baseline is None or latest is None:
        return {
            "available":  False,
            "message":    "Need at least 2 uploads to compute conversion. Upload another file to see comparison.",
            "baseline":   None,
            "latest":     None,
            "buckets":    None,
            "transitions": [],
        }

    if baseline == latest:
        raise HTTPException(status_code=400, detail="Baseline and latest must be different uploads.")

    baseline_meta = await _get_upload(baseline)
    latest_meta   = await _get_upload(latest)
    if not baseline_meta or not latest_meta:
        raise HTTPException(status_code=404, detail="Upload not found.")

    if baseline_meta["uploaded_at"] > latest_meta["uploaded_at"]:
        baseline, latest = latest, baseline
        baseline_meta, latest_meta = latest_meta, baseline_meta

    baseline_snaps = await database.fetch_all(
        snapshots_table.select().where(snapshots_table.c.upload_id == baseline)
    )
    latest_snaps = await database.fetch_all(
        snapshots_table.select().where(snapshots_table.c.upload_id == latest)
    )

    baseline_by_job = {s["job_id"]: s for s in baseline_snaps}
    latest_by_job   = {s["job_id"]: s for s in latest_snaps}

    base_ts   = baseline_meta["uploaded_at"]
    latest_ts = latest_meta["uploaded_at"]
    emails_in_window = await database.fetch_all(
        email_log_table.select().where(
            (email_log_table.c.sent_at >= base_ts)
            & (email_log_table.c.sent_at <= latest_ts)
        )
    )
    emailed_job_ids = {e["job_id"] for e in emails_in_window}

    buckets = {
        "attributed": {
            "total_emailed":            0,
            "any_forward":              0,
            "scheduling_conversion":    0,
            "scheduling_eligible":      0,
            "inspection_conversion":    0,
            "inspection_eligible":      0,
            "approval_conversion":      0,
            "approval_eligible":        0,
            "approval_cleared":         0,
        },
        "organic": {
            "total_not_emailed":      0,
            "any_forward":            0,
        },
    }

    transitions = []

    common_job_ids = set(baseline_by_job.keys()) & set(latest_by_job.keys())
    for job_id in common_job_ids:
        base = baseline_by_job[job_id]
        late = latest_by_job[job_id]
        classification = _classify_transition(base["status"], late["status"])
        was_emailed = job_id in emailed_job_ids

        if was_emailed:
            buckets["attributed"]["total_emailed"] += 1
            if base["status"] == "Initiated":
                buckets["attributed"]["scheduling_eligible"] += 1
            if base["status"] == "Scheduled":
                buckets["attributed"]["inspection_eligible"] += 1
            if base["status"] == "Inspected":
                buckets["attributed"]["approval_eligible"] += 1

            if classification["any_forward"]:
                buckets["attributed"]["any_forward"] += 1
                if classification["scheduling_conversion"]:
                    buckets["attributed"]["scheduling_conversion"] += 1
                if classification["inspection_conversion"]:
                    buckets["attributed"]["inspection_conversion"] += 1
                if classification["approval_conversion"]:
                    buckets["attributed"]["approval_conversion"] += 1
                transitions.append({
                    "job_id":      job_id,
                    "vehicle_reg": late["vehicle_reg"],
                    "from":        classification["from_status"],
                    "to":          classification["to_status"],
                    "phase":       late["phase"],
                    "emailed":     True,
                })
        else:
            buckets["organic"]["total_not_emailed"] += 1
            if classification["any_forward"]:
                buckets["organic"]["any_forward"] += 1
                transitions.append({
                    "job_id":      job_id,
                    "vehicle_reg": late["vehicle_reg"],
                    "from":        classification["from_status"],
                    "to":          classification["to_status"],
                    "phase":       late["phase"],
                    "emailed":     False,
                })

    if latest_meta["detected_phase"] == 3 and baseline_meta["detected_phase"] == 3:
        baseline_only = set(baseline_by_job.keys()) - set(latest_by_job.keys())
        for job_id in baseline_only:
            base = baseline_by_job[job_id]
            if base["phase"] != 3:
                continue
            was_emailed = job_id in emailed_job_ids
            if was_emailed:
                buckets["attributed"]["total_emailed"] += 1
                buckets["attributed"]["approval_eligible"] += 1
                buckets["attributed"]["any_forward"] += 1
                buckets["attributed"]["approval_conversion"] += 1
                buckets["attributed"]["approval_cleared"] += 1
                transitions.append({
                    "job_id":      job_id,
                    "vehicle_reg": base["vehicle_reg"],
                    "from":        "Inspected",
                    "to":          "Approved (cleared)",
                    "phase":       3,
                    "emailed":     True,
                })
            else:
                buckets["organic"]["total_not_emailed"] += 1
                buckets["organic"]["any_forward"] += 1
                transitions.append({
                    "job_id":      job_id,
                    "vehicle_reg": base["vehicle_reg"],
                    "from":        "Inspected",
                    "to":          "Approved (cleared)",
                    "phase":       3,
                    "emailed":     False,
                })

    a = buckets["attributed"]
    o = buckets["organic"]

    rates = {
        "attributed_overall_rate": _safe_pct(a["any_forward"], a["total_emailed"]),
        "scheduling_rate":         _safe_pct(a["scheduling_conversion"], a["scheduling_eligible"]),
        "inspection_rate":         _safe_pct(a["inspection_conversion"], a["inspection_eligible"]),
        "approval_rate":           _safe_pct(a["approval_conversion"],   a["approval_eligible"]),
        "organic_rate":            _safe_pct(o["any_forward"], o["total_not_emailed"]),
    }

    return {
        "available":   True,
        "baseline":    {
            "id":             baseline_meta["id"],
            "uploaded_at":    baseline_meta["uploaded_at"],
            "filename":       baseline_meta["filename"],
            "row_count":      baseline_meta["row_count"],
            "detected_phase": baseline_meta["detected_phase"],
        },
        "latest":      {
            "id":             latest_meta["id"],
            "uploaded_at":    latest_meta["uploaded_at"],
            "filename":       latest_meta["filename"],
            "row_count":      latest_meta["row_count"],
            "detected_phase": latest_meta["detected_phase"],
        },
        "buckets":     buckets,
        "rates":       rates,
        "transitions": sorted(transitions, key=lambda t: (not t["emailed"], t["from"]))[:300],
        "emails_in_window": len(emails_in_window),
    }


def _safe_pct(num: int, denom: int) -> float:
    if not denom:
        return 0.0
    return round(num / denom * 100, 1)
