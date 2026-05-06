"""
CSV / Excel upload endpoint
============================
POST /api/upload/jobs  — upload a CSV or .xlsx file of pending jobs.

Expected columns (case-insensitive, order doesn't matter):
  Job ID, Vehicle Reg, Client Name, Client Email, Client Phone,
  Phase, Reason Code, Initiated Date, Scheduled Date,
  Solver Name, Solver Phone, Job Status, Reason Logged At

"Reason Code" should be one of:
  not_picking  |  unreachable  |  not_ready
  (or the display versions: "Not picking", "Unreachable", "Not ready")
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

# Maps any variant of a column name → our standard field name
COLUMN_ALIASES: dict[str, str] = {
    # id variants
    "job id": "id", "job_id": "id", "jobid": "id", "id": "id",
    # vehicle
    "vehicle reg": "vehicle_reg", "vehicle_reg": "vehicle_reg",
    "reg": "vehicle_reg", "registration": "vehicle_reg", "plate": "vehicle_reg",
    # client
    "client name": "client_name", "client_name": "client_name",
    "name": "client_name", "customer name": "client_name",
    "client email": "client_email", "client_email": "client_email",
    "email": "client_email",
    "client phone": "client_phone", "client_phone": "client_phone",
    "phone": "client_phone", "mobile": "client_phone",
    # phase
    "phase": "phase",
    # reason
    "reason code": "reason", "reason_code": "reason", "reason": "reason",
    # dates
    "initiated date": "initiated_date", "initiated_date": "initiated_date",
    "initiation date": "initiated_date", "start date": "initiated_date",
    "scheduled date": "scheduled_date", "scheduled_date": "scheduled_date",
    "appointment date": "scheduled_date",
    # solver
    "solver name": "solver_name", "solver_name": "solver_name", "inspector": "solver_name",
    "solver phone": "solver_phone", "solver_phone": "solver_phone",
    # status
    "job status": "job_status", "job_status": "job_status", "status": "job_status",
    # timing
    "reason logged at": "reason_logged_at", "reason_logged_at": "reason_logged_at",
    "reason date": "reason_logged_at",
}

REASON_ALIASES: dict[str, str] = {
    "not picking": "not_picking",
    "not_picking": "not_picking",
    "unreachable": "unreachable",
    "not ready": "not_ready",
    "not_ready": "not_ready",
}


def _normalise_reason(val: str) -> str:
    if not val:
        return ""
    return REASON_ALIASES.get(str(val).lower().strip(), str(val).lower().strip().replace(" ", "_"))


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename dataframe columns to our standard DB field names."""
    rename_map = {}
    for col in df.columns:
        normalised = COLUMN_ALIASES.get(col.lower().strip())
        if normalised:
            rename_map[col] = normalised
    return df.rename(columns=rename_map)


def _read_file(content: bytes, filename: str) -> pd.DataFrame:
    if filename.endswith(".csv"):
        return pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    elif filename.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False)
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload a .csv or .xlsx file."
        )


@router.post("/jobs")
async def upload_jobs(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """
    Upload a CSV or Excel file of pending jobs.
    Upserts rows into the jobs table (insert or update by job ID).
    Returns a summary of what was imported.
    """
    content = await file.read()
    try:
        df = _read_file(content, file.filename or "upload.csv")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    df = _normalise_columns(df)

    required = {"client_name", "client_email", "vehicle_reg"}
    missing  = required - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required columns: {', '.join(missing)}. "
                   f"Found columns: {', '.join(df.columns.tolist())}"
        )

    now_iso     = datetime.now(timezone.utc).isoformat()
    inserted    = 0
    updated     = 0
    skipped     = 0
    errors      = []

    for i, row in df.iterrows():
        try:
            row_dict = row.to_dict()

            # Auto-generate ID if missing
            job_id = str(row_dict.get("id", "")).strip() or f"CSV-{uuid.uuid4().hex[:8].upper()}"

            # Normalise reason code
            reason = _normalise_reason(str(row_dict.get("reason", "")))

            record = {
                "id":               job_id,
                "vehicle_reg":      str(row_dict.get("vehicle_reg", "")).strip(),
                "client_name":      str(row_dict.get("client_name", "")).strip(),
                "client_email":     str(row_dict.get("client_email", "")).strip().lower(),
                "client_phone":     str(row_dict.get("client_phone", "")).strip() or None,
                "phase":            int(row_dict.get("phase", 1)) if row_dict.get("phase") else 1,
                "reason":           reason or None,
                "initiated_date":   str(row_dict.get("initiated_date", "")).strip() or now_iso[:10],
                "scheduled_date":   str(row_dict.get("scheduled_date", "")).strip() or None,
                "solver_name":      str(row_dict.get("solver_name", "")).strip() or None,
                "solver_phone":     str(row_dict.get("solver_phone", "")).strip() or None,
                "job_status":       str(row_dict.get("job_status", "pending")).strip().lower() or "pending",
                "reason_logged_at": str(row_dict.get("reason_logged_at", "")).strip() or now_iso,
                "source":           "csv",
                "emails_sent":      0,
                "status":           "awaiting_reply",
                "flagged_manual":   False,
                "created_at":       now_iso,
                "updated_at":       now_iso,
            }

            # Skip completely empty rows
            if not record["client_email"] and not record["vehicle_reg"]:
                skipped += 1
                continue

            # Check if job already exists
            existing = await database.fetch_one(
                jobs_table.select().where(jobs_table.c.id == job_id)
            )

            if existing:
                # Update metadata but preserve email tracking state
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
                        job_status     = record["job_status"],
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

    logger.info(f"CSV upload: {inserted} inserted, {updated} updated, {skipped} skipped")

    return {
        "ok":       True,
        "inserted": inserted,
        "updated":  updated,
        "skipped":  skipped,
        "errors":   errors[:10],   # cap error list for readability
        "total_rows": len(df),
    }


@router.get("/template")
async def download_template():
    """Return the expected CSV column headers as a downloadable template."""
    from fastapi.responses import StreamingResponse
    headers = [
        "Job ID", "Vehicle Reg", "Client Name", "Client Email", "Client Phone",
        "Phase", "Reason Code", "Initiated Date", "Scheduled Date",
        "Solver Name", "Solver Phone", "Job Status", "Reason Logged At"
    ]
    sample = [
        "J-0001", "KDA 421X", "James Mwangi", "james@example.com", "+254712345678",
        "1", "not_picking", "2026-05-01", "", "", "", "pending", "2026-05-01 09:00"
    ]
    csv_content = ",".join(headers) + "\n" + ",".join(sample) + "\n"
    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobs_template.csv"},
    )
