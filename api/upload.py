"""
CSV / Excel upload endpoint
============================
Accepts any CSV or Excel export from Zoho (or manual files).
Automatically detects columns by name — no rigid requirements.
Only client_email (or Customer_email) + vehicle_reg are truly required.
"""

import io
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
import pandas as pd

from db.database import database, jobs as jobs_table
from api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Column aliases ────────────────────────────────────────────
# Maps ANY variant found in real Zoho exports → our DB field name
COLUMN_ALIASES: dict[str, str] = {
    # id
    "request_id": "id", "master_request_id": "id", "initiate_id": "id", "id": "id", "job_id": "id",

    # vehicle
    "vehicle_reg": "vehicle_reg", "vehicle reg": "vehicle_reg", "reg": "vehicle_reg",

    # client
    "client_name": "client_name", "name": "client_name",
    "customer_email": "client_email", "client_email": "client_email", "email": "client_email",
    "client_cell_no": "client_phone", "client_phone": "client_phone",
    "phone": "client_phone", "mobile": "client_phone", "client_no": "client_phone",

    # phase
    "phase": "phase",

    # reason — Request Summary uses "reason", Scheduled Not Valued uses "latest_pending_reason"
    "reason": "reason", "reason_code": "reason",
    "latest_pending_reason": "reason", "pending_reason": "reason",

    # dates
    "initiated_date": "initiated_date", "initiation date": "initiated_date",
    "requested_date": "initiated_date",
    "schedule_date": "scheduled_date", "scheduled_date": "scheduled_date",
    "appointment date": "scheduled_date",

    # solver
    "allocated_to": "solver_name", "solver_name": "solver_name",
    "scheduler": "solver_name", "solver": "solver_name",
    "solver_contact": "solver_phone", "solver_phone": "solver_phone",
    "solver_email": "solver_email",

    # status — Request Summary has "Request Status"
    "request status": "job_status", "request_status": "job_status",
    "job_status": "job_status", "status": "job_status",

    # timing
    "reason_logged_at": "reason_logged_at", "created_at": "reason_logged_at",
}

REASON_NORMALISE: dict[str, str] = {
    "not picking": "not_picking",
    "not_picking": "not_picking",
    "unreachable": "unreachable",
    "not ready": "not_ready",
    "not_ready": "not_ready",
    "wrong number": "wrong_number",
    "no documents": "no_documents",
}

STATUS_PENDING = {"initiated", "pending", "active"}


def _normalise_reason(val: str) -> str:
    if not val:
        return ""
    v = str(val).lower().strip()
    return REASON_NORMALISE.get(v, v.replace(" ", "_").replace("-", "_"))


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for col in df.columns:
        key = col.encode('utf-8').decode('utf-8-sig').lower().strip()
        mapped = COLUMN_ALIASES.get(key)
        if mapped:
            rename[col] = mapped
    return df.rename(columns=rename)


def _detect_phase(df: pd.DataFrame) -> int:
    """Guess phase from columns present: solver view = phase 2."""
    cols = [c.lower() for c in df.columns]
    if "latest_pending_reason" in cols or "solver_contact" in cols or "pending_reason" in cols:
        return 2
    return 1


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

    # Detect phase before renaming columns
    detected_phase = _detect_phase(df_raw)

    df = _normalise_columns(df_raw)

    # Only truly require vehicle_reg + client_email
    missing = []
    if "vehicle_reg" not in df.columns:
        missing.append("vehicle_reg / Vehicle_reg")
    if "client_email" not in df.columns:
        missing.append("customer_email / Client_email")
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Could not find required columns: {', '.join(missing)}. "
                   f"Columns found: {', '.join(df_raw.columns.tolist())}"
        )

    now_iso  = datetime.now(timezone.utc).isoformat()
    inserted = 0
    updated  = 0
    skipped  = 0
    errors   = []

    for i, row in df.iterrows():
        try:
            r = row.to_dict()

            email = str(r.get("client_email", "")).strip().lower()
            reg   = str(r.get("vehicle_reg", "")).strip()
            if not email or not reg:
                skipped += 1
                continue

            # Filter: Phase 1 only import Initiated rows
            if detected_phase == 1 and "job_status" in r:
                status_val = str(r.get("job_status", "")).strip().lower()
                if status_val and status_val not in STATUS_PENDING:
                    skipped += 1
                    continue

            job_id = str(r.get("id", "")).strip() or f"CSV-{uuid.uuid4().hex[:8].upper()}"
            reason_raw = str(r.get("reason", "")).strip()

            record = {
                "id":               job_id,
                "vehicle_reg":      reg,
                "client_name":      str(r.get("client_name", "")).strip() or "Client",
                "client_email":     email,
                "client_phone":     str(r.get("client_phone", "")).strip() or None,
                "phase":            detected_phase,
                "reason":           _normalise_reason(reason_raw) or None,
                "initiated_date":   str(r.get("initiated_date", "")).strip() or now_iso[:10],
                "scheduled_date":   str(r.get("scheduled_date", "")).strip() or None,
                "solver_name":      str(r.get("solver_name", "")).strip() or None,
                "solver_phone":     str(r.get("solver_phone", "")).strip() or None,
                "job_status":       "pending",
                "reason_logged_at": str(r.get("reason_logged_at", "")).strip() or now_iso,
                "source":           "csv",
                "emails_sent":      0,
                "status":           "awaiting_reply",
                "flagged_manual":   False,
                "created_at":       now_iso,
                "updated_at":       now_iso,
            }

            existing = await database.fetch_one(
                jobs_table.select().where(jobs_table.c.id == job_id)
            )

            if existing:
                await database.execute(
                    jobs_table.update()
                    .where(jobs_table.c.id == job_id)
                    .values(
                        vehicle_reg    = record["vehicle_reg"],
                        client_name    = record["client_name"],
                        client_email   = record["client_email"],
                        client_phone   = record["client_phone"],
                        phase          = record["phase"],
                        reason         = record["reason"],
                        scheduled_date = record["scheduled_date"],
                        solver_name    = record["solver_name"],
                        solver_phone   = record["solver_phone"],
                        updated_at     = now_iso,
                    )
                )
                updated += 1
            else:
                await database.execute(jobs_table.insert().values(**record))
                inserted += 1

        except Exception as e:
            errors.append(f"Row {i + 2}: {e}")
            skipped += 1

    logger.info(f"Upload: phase={detected_phase} | {inserted} inserted, {updated} updated, {skipped} skipped")

    return {
        "ok":           True,
        "detected_phase": detected_phase,
        "inserted":     inserted,
        "updated":      updated,
        "skipped":      skipped,
        "errors":       errors[:10],
        "total_rows":   len(df),
    }


@router.get("/template")
async def download_template():
    from fastapi.responses import StreamingResponse
    headers = ["Request_ID", "Vehicle_reg", "Client_name", "Customer_email",
               "Client_cell_no", "Request Status", "Reason", "Initiated_Date",
               "Schedule_date", "Allocated_to", "Scheduler"]
    sample  = ["J-0001", "KDA 421X", "James Mwangi", "james@example.com",
               "+254712345678", "Initiated", "not_picking", "2026-05-01", "", "", ""]
    csv_content = ",".join(headers) + "\n" + ",".join(sample) + "\n"
    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobs_template.csv"},
    )
