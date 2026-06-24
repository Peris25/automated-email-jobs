"""
CSV / Excel upload endpoint (v1.4)
====================================
Auto-detects which phase the export belongs to:
  - Phase 1 (Scheduling)  — Request Status = Initiated/Pending
  - Phase 2 (Inspection)  — has latest_pending_reason / solver_contact columns
  - Phase 3 (Approval)    — has pending_documents / missing_documents columns

v1.4: Accepts solver-summary-only files (no client_email column).
      Adds call_back as a solver-only reason (no client email sent).
"""

import io
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
import pandas as pd
import sqlalchemy as sa

from db.database import (
    database, jobs as jobs_table, uploads as uploads_table,
    job_snapshots as snapshots_table,
)
from api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

COLUMN_ALIASES: dict[str, str] = {
    "request_id": "id", "master_request_id": "id", "initiate_id": "id", "id": "id", "job_id": "id",
    "vehicle_reg": "vehicle_reg", "vehicle reg": "vehicle_reg", "reg": "vehicle_reg",
    "client_name": "client_name", "name": "client_name",
    "customer_email": "client_email", "client_email": "client_email", "email": "client_email",
    "client_cell_no": "client_phone", "client_phone": "client_phone",
    "phone": "client_phone", "mobile": "client_phone", "client_no": "client_phone",
    "phase": "phase",
    "reason": "reason", "reason_code": "reason",
    "latest_pending_reason": "reason", "pending_reason": "reason",
    "pending_documents": "missing_documents",
    "missing_documents": "missing_documents",
    "documents_pending":  "missing_documents",
    "pending_docs":       "missing_documents",
    "logbook_received":   "_logbook_received",
    "logbook":            "_logbook_received",
    "sticker_received":   "_sticker_received",
    "insurance_sticker":  "_sticker_received",
    "letter_received":    "_letter_received",
    "valuation_letter":   "_letter_received",
    "initiated_date": "initiated_date", "initiation date": "initiated_date",
    "requested_date": "initiated_date",
    "schedule_date": "scheduled_date", "scheduled_date": "scheduled_date",
    "appointment date": "scheduled_date",
    "allocated_to": "solver_name", "solver_name": "solver_name",
    "scheduler": "solver_name", "solver": "solver_name",
    "solver_contact": "solver_phone", "solver_phone": "solver_phone",
    "solver_email": "solver_email",
    "request status": "pipeline_status", "request_status": "pipeline_status",
    "job_status": "pipeline_status", "status": "pipeline_status",
    "pipeline_status": "pipeline_status",
    "reason_logged_at": "reason_logged_at", "created_at": "reason_logged_at",
}

REASON_NORMALISE: dict[str, str] = {
    "not picking": "not_picking", "not_picking": "not_picking",
    "unreachable": "unreachable",
    "not ready": "not_ready", "not_ready": "not_ready",
    "wrong number": "wrong_number",
    "call back": "call_back", "call_back": "call_back", "callback": "call_back",
    "no logbook": "no_logbook", "no_logbook": "no_logbook", "logbook missing": "no_logbook",
    "no sticker": "no_sticker", "no_sticker": "no_sticker", "sticker missing": "no_sticker",
    "no insurance sticker": "no_sticker", "no insurance": "no_sticker",
    "no letter": "no_letter", "no_letter": "no_letter", "letter missing": "no_letter",
    "no valuation letter": "no_letter",
}

SOLVER_ONLY_REASONS = {"call_back"}

PIPELINE_STATUS_NORMALISE: dict[str, str] = {
    "initiated":  "Initiated",
    "pending":    "Initiated",
    "active":     "Initiated",
    "scheduled":  "Scheduled",
    "inspected":  "Inspected",
    "completed":  "Inspected",
    "pending approval": "Inspected",
    "pending_approval": "Inspected",
    "approved":   "Approved",
    "valued":     "Approved",
}

PIPELINE_ORDER = ["Initiated", "Scheduled", "Inspected", "Approved"]
APPROVAL_REASON_CODES = {"no_logbook", "no_sticker", "no_letter"}


def _normalise_reason(val: str) -> str:
    if not val:
        return ""
    v = str(val).lower().strip()
    return REASON_NORMALISE.get(v, v.replace(" ", "_").replace("-", "_"))


def _normalise_pipeline_status(val: str) -> str:
    if not val:
        return "Initiated"
    v = str(val).lower().strip()
    return PIPELINE_STATUS_NORMALISE.get(v, val.strip().title())


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for col in df.columns:
        key = col.encode('utf-8').decode('utf-8-sig').lower().strip()
        mapped = COLUMN_ALIASES.get(key)
        if mapped:
            rename[col] = mapped
    return df.rename(columns=rename)


def _detect_phase(df: pd.DataFrame) -> int:
    cols_lower = [c.lower() for c in df.columns]
    cols_set = set(cols_lower)

    approval_signals = {"pending_documents", "missing_documents", "documents_pending",
                        "pending_docs", "logbook_received", "sticker_received",
                        "letter_received", "valuation_letter", "insurance_sticker"}
    if cols_set & approval_signals:
        return 3

    if "request status" in cols_lower or "request_status" in cols_lower or "status" in cols_lower:
        status_col = next((c for c in df.columns if c.lower() in ("request status", "request_status", "status")), None)
        if status_col:
            statuses = df[status_col].dropna().astype(str).str.lower().str.strip().unique()
            if any("pending approval" in s or s == "pending_approval" for s in statuses):
                return 3

    if "latest_pending_reason" in cols_set or "solver_contact" in cols_set or "pending_reason" in cols_set:
        return 2

    return 1


def _extract_missing_documents(row: dict, detected_phase: int) -> str | None:
    if detected_phase != 3:
        return None

    missing = []

    md = str(row.get("missing_documents", "")).strip()
    if md:
        parts = [p.strip() for p in md.replace(";", ",").split(",") if p.strip()]
        for p in parts:
            code = _normalise_reason(p)
            if code in APPROVAL_REASON_CODES and code not in missing:
                missing.append(code)
        if missing:
            return ",".join(missing)

    def is_missing(val):
        if val is None:
            return False
        v = str(val).strip().lower()
        return v in ("no", "false", "0", "missing", "pending", "not received", "n", "")

    received_logbook = row.get("_logbook_received")
    received_sticker = row.get("_sticker_received")
    received_letter  = row.get("_letter_received")

    if "_logbook_received" in row and is_missing(received_logbook):
        if "no_logbook" not in missing: missing.append("no_logbook")
    if "_sticker_received" in row and is_missing(received_sticker):
        if "no_sticker" not in missing: missing.append("no_sticker")
    if "_letter_received" in row and is_missing(received_letter):
        if "no_letter" not in missing: missing.append("no_letter")

    reason_field = _normalise_reason(str(row.get("reason", "")).strip())
    if reason_field in APPROVAL_REASON_CODES and reason_field not in missing:
        missing.append(reason_field)

    return ",".join(missing) if missing else None


def _read_file(content: bytes, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    elif name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False)
    else:
        raise HTTPException(status_code=400, detail="Please upload a .csv or .xlsx file.")


@router.post("/jobs")
async def upload_jobs(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    content = await file.read()
    try:
        df_raw = _read_file(content, file.filename or "upload.csv")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    detected_phase = _detect_phase(df_raw)
    df = _normalise_columns(df_raw)

    missing = []
    if "vehicle_reg" not in df.columns:
        missing.append("vehicle_reg / Vehicle_reg")
    has_email_col = "client_email" in df.columns
    has_phone_col = "client_phone" in df.columns
    if not has_email_col and not has_phone_col:
        missing.append("client_email or client_phone (need at least one for client contact)")
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Could not find required columns: {', '.join(missing)}. "
                   f"Columns found: {', '.join(df_raw.columns.tolist())}"
        )

    is_solver_only_file = False
    if not has_email_col:
        is_solver_only_file = True
    else:
        if (df["client_email"].astype(str).str.strip() == "").all():
            is_solver_only_file = True
    if is_solver_only_file:
        logger.info("Detected solver-summary-only file (no populated client_email column)")

    now_iso = datetime.now(timezone.utc).isoformat()

    upload_id = await database.execute(
        uploads_table.insert().values(
            uploaded_at    = now_iso,
            uploaded_by    = user if isinstance(user, str) else "system",
            filename       = file.filename or "upload.csv",
            detected_phase = detected_phase,
            row_count      = len(df),
            inserted       = 0,
            updated        = 0,
            skipped        = 0,
            cleared        = 0,
            is_baseline    = False,
        )
    )

    inserted = 0
    updated  = 0
    skipped  = 0
    cleared  = 0
    errors   = []
    snapshots_to_insert = []
    seen_job_ids_this_upload: set[str] = set()

    for i, row in df.iterrows():
        try:
            r = row.to_dict()

            email = str(r.get("client_email", "")).strip().lower()
            phone = str(r.get("client_phone", "")).strip()
            reg   = str(r.get("vehicle_reg", "")).strip()
            if not reg or (not email and not phone):
                skipped += 1
                continue

            job_id     = str(r.get("id", "")).strip() or f"CSV-{uuid.uuid4().hex[:8].upper()}"
            seen_job_ids_this_upload.add(job_id)

            reason_raw  = str(r.get("reason", "")).strip()
            reason_norm = _normalise_reason(reason_raw) or None
            missing_docs = _extract_missing_documents(r, detected_phase)
            pipeline_status = _normalise_pipeline_status(str(r.get("pipeline_status", "")).strip())

            if detected_phase == 3 and pipeline_status == "Initiated" and missing_docs:
                pipeline_status = "Inspected"

            if detected_phase == 3 and missing_docs:
                first_doc = missing_docs.split(",")[0]
                reason_norm = first_doc

            snapshots_to_insert.append({
                "upload_id":   upload_id,
                "job_id":      job_id,
                "vehicle_reg": reg,
                "phase":       detected_phase,
                "status":      pipeline_status,
                "reason":      reason_norm,
                "missing_documents": missing_docs,
                "captured_at": now_iso,
            })

            solver_name_val  = str(r.get("solver_name", "")).strip() or None
            solver_phone_val = str(r.get("solver_phone", "")).strip() or None
            solver_email_val = str(r.get("solver_email", "")).strip().lower() or None

            if solver_name_val and solver_email_val:
                try:
                    from services.solver_summary import auto_register_solver_from_export
                    await auto_register_solver_from_export(solver_name_val, solver_email_val, solver_phone_val)
                except Exception as e:
                    logger.debug(f"solver auto-register skipped: {e}")

            internal_job_status = "pending" if pipeline_status != "Approved" else "completed"

            existing = await database.fetch_one(
                jobs_table.select().where(jobs_table.c.id == job_id)
            )

            if existing:
                prev_status = existing.get("current_status") or existing.get("previous_status")
                await database.execute(
                    jobs_table.update()
                    .where(jobs_table.c.id == job_id)
                    .values(
                        vehicle_reg       = reg,
                        client_name       = str(r.get("client_name", "")).strip() or existing.get("client_name") or "Client",
                        client_email      = email if email else existing.get("client_email"),
                        client_phone      = phone or existing.get("client_phone"),
                        phase             = detected_phase,
                        reason            = reason_norm,
                        missing_documents = missing_docs,
                        scheduled_date    = str(r.get("scheduled_date", "")).strip() or existing.get("scheduled_date"),
                        solver_name       = solver_name_val or existing.get("solver_name"),
                        solver_phone      = solver_phone_val or existing.get("solver_phone"),
                        solver_email      = solver_email_val or existing.get("solver_email"),
                        current_status    = pipeline_status,
                        previous_status   = prev_status,
                        job_status        = internal_job_status,
                        updated_at        = now_iso,
                    )
                )
                updated += 1
            else:
                await database.execute(
                    jobs_table.insert().values(
                        id               = job_id,
                        vehicle_reg      = reg,
                        client_name      = str(r.get("client_name", "")).strip() or "Client",
                        client_email     = email or None,
                        client_phone     = phone or None,
                        phase            = detected_phase,
                        reason           = reason_norm,
                        missing_documents= missing_docs,
                        initiated_date   = str(r.get("initiated_date", "")).strip() or now_iso[:10],
                        scheduled_date   = str(r.get("scheduled_date", "")).strip() or None,
                        solver_name      = solver_name_val,
                        solver_phone     = solver_phone_val,
                        solver_email     = solver_email_val,
                        current_status   = pipeline_status,
                        previous_status  = None,
                        job_status       = internal_job_status,
                        reason_logged_at = str(r.get("reason_logged_at", "")).strip() or now_iso,
                        source           = "csv",
                        emails_sent      = 0,
                        status           = "awaiting_reply",
                        flagged_manual   = False,
                        created_at       = now_iso,
                        updated_at       = now_iso,
                    )
                )
                inserted += 1

        except Exception as e:
            errors.append(f"Row {i + 2}: {e}")
            skipped += 1

    if snapshots_to_insert:
        for snap in snapshots_to_insert:
            await database.execute(snapshots_table.insert().values(**snap))

    if detected_phase == 3 and seen_job_ids_this_upload:
        previously_pending = await database.fetch_all(
            jobs_table.select().where(
                (jobs_table.c.phase == 3) &
                (jobs_table.c.job_status == "pending")
            )
        )
        for job in previously_pending:
            if job["id"] not in seen_job_ids_this_upload:
                await database.execute(
                    jobs_table.update()
                    .where(jobs_table.c.id == job["id"])
                    .values(
                        job_status        = "completed",
                        missing_documents = None,
                        updated_at        = now_iso,
                    )
                )
                cleared += 1

    await database.execute(
        uploads_table.update()
        .where(uploads_table.c.id == upload_id)
        .values(inserted=inserted, updated=updated, skipped=skipped, cleared=cleared)
    )

    logger.info(f"Upload {upload_id}: phase={detected_phase} | {inserted}/{updated}/{skipped} | cleared={cleared}")

    solver_summary_result = None
    try:
        from services.solver_summary import is_solver_summary_enabled, build_solver_summaries
        if await is_solver_summary_enabled(detected_phase):
            pending_for_phase = await database.fetch_all(
                jobs_table.select().where(
                    (jobs_table.c.phase == detected_phase) &
                    (jobs_table.c.job_status == "pending") &
                    (jobs_table.c.solver_name.isnot(None)) &
                    (jobs_table.c.solver_name != "")
                )
            )
            solver_summary_result = await build_solver_summaries(
                jobs_for_summary = pending_for_phase,
                upload_id        = upload_id,
                phase            = detected_phase,
            )
    except Exception as e:
        logger.error(f"Solver summary build failed for upload {upload_id}: {e}")
        solver_summary_result = {"summaries_queued": 0, "jobs_covered": 0,
                                 "warnings": [f"Internal error: {e}"]}

    return {
        "ok":              True,
        "upload_id":       upload_id,
        "detected_phase":  detected_phase,
        "phase_label":     {1: "Scheduling", 2: "Inspection", 3: "Approval"}.get(detected_phase, "Unknown"),
        "inserted":        inserted,
        "updated":         updated,
        "skipped":         skipped,
        "cleared":         cleared,
        "errors":          errors[:10],
        "total_rows":      len(df),
        "solver_summary":  solver_summary_result,
    }


@router.get("/template")
async def download_template():
    from fastapi.responses import StreamingResponse
    headers = ["Request_ID", "Vehicle_reg", "Client_name", "Customer_email",
               "Client_cell_no", "Request Status", "Reason", "Pending_documents",
               "Initiated_Date", "Schedule_date", "Allocated_to", "Solver_email"]
    sample  = ["J-0001", "KDA 421X", "James Mwangi", "james@example.com",
               "+254712345678", "Pending Approval", "", "no_logbook,no_sticker",
               "2026-05-01", "", "David Kimani", "david.kimani@solvit.co.ke"]
    csv_content = ",".join(headers) + "\n" + ",".join(sample) + "\n"
    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobs_template.csv"},
    )


@router.get("/history")
async def list_uploads(user=Depends(get_current_user)):
    rows = await database.fetch_all(
        uploads_table.select().order_by(sa.desc(uploads_table.c.uploaded_at))
    )
    return rows


@router.patch("/{upload_id}/baseline")
async def set_baseline(upload_id: int, user=Depends(get_current_user)):
    await database.execute(uploads_table.update().values(is_baseline=False))
    await database.execute(
        uploads_table.update()
        .where(uploads_table.c.id == upload_id)
        .values(is_baseline=True)
    )
    return {"ok": True, "baseline_upload_id": upload_id}
