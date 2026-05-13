"""
Zoho Analytics integration — two views, same workspace.

Phase 1 (AM Team):    Requests Summary view
  Filter:  Request_Status = "Initiated"
  Trigger: unreachable / not picking → immediate
           anything else             → 3 days still Initiated

Phase 2 (Solver Team): Scheduled Not Valued view
  Filter:  all rows (being in view = pending)
  Trigger: same timing logic as Phase 1
  Email:   client + CC solver
"""

import os
import logging
import datetime
import httpx

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────
ZOHO_CLIENT_ID      = os.getenv("ZOHO_CLIENT_ID", "")
ZOHO_CLIENT_SECRET  = os.getenv("ZOHO_CLIENT_SECRET", "")
ZOHO_REFRESH_TOKEN  = os.getenv("ZOHO_REFRESH_TOKEN", "")
ZOHO_WORKSPACE_ID   = os.getenv("ZOHO_WORKSPACE_ID", "")
ZOHO_VIEW_ID_AM     = os.getenv("ZOHO_VIEW_ID_AM", "")     # Requests Summary
ZOHO_VIEW_ID_SOLVER = os.getenv("ZOHO_VIEW_ID_SOLVER", "") # Scheduled Not Valued
ZOHO_DC             = os.getenv("ZOHO_DC", "com")

_zoho_token_cache: dict = {}


# ── Token ─────────────────────────────────────────────────────

async def _get_zoho_token() -> str:
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    if _zoho_token_cache.get("expires_at", 0) > now + 60:
        return _zoho_token_cache["access_token"]

    if not all([ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN]):
        raise RuntimeError(
            "Zoho credentials not set. Configure ZOHO_CLIENT_ID, "
            "ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN in env vars."
        )

    url = f"https://accounts.zoho.{ZOHO_DC}/oauth/v2/token"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, data={
            "refresh_token": ZOHO_REFRESH_TOKEN,
            "client_id":     ZOHO_CLIENT_ID,
            "client_secret": ZOHO_CLIENT_SECRET,
            "grant_type":    "refresh_token",
        })
        r.raise_for_status()
        data = r.json()

    if "access_token" not in data:
        raise RuntimeError(f"Zoho token error: {data}")

    _zoho_token_cache["access_token"] = data["access_token"]
    _zoho_token_cache["expires_at"]   = now + data.get("expires_in", 3600)
    logger.info("Zoho token refreshed")
    return _zoho_token_cache["access_token"]


# ── Shared fetch helper ───────────────────────────────────────

async def _fetch_view(view_id: str) -> tuple[list, list]:
    """Fetch raw columns + rows from a Zoho Analytics view."""
    token = await _get_zoho_token()
    url = (
        f"https://analyticsapi.zoho.{ZOHO_DC}/restapi/v2"
        f"/workspaces/{ZOHO_WORKSPACE_ID}/views/{view_id}/data"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            url,
            headers={
                "Authorization":   f"Zoho-oauthtoken {token}",
                "ZANALYTICS-ORGID": ZOHO_WORKSPACE_ID,
            },
            params={"CONFIG": '{"responseFormat":"json","columnFormat":"name"}'},
        )
        r.raise_for_status()
        payload = r.json()

    raw  = payload.get("data", {})
    cols = raw.get("columns", [])
    rows = raw.get("rows", [])
    return cols, rows


def _excel_date(val) -> str:
    """Convert Excel serial date number to ISO date string."""
    try:
        f = float(val)
        return (
            datetime.date(1899, 12, 30) + datetime.timedelta(days=int(f))
        ).isoformat()
    except Exception:
        return str(val) if val else ""


def _col_index(cols: list, name: str) -> int:
    """Return column index by name, -1 if not found."""
    for i, col in enumerate(cols):
        col_name = col.get("columnName") or col.get("name", "")
        if col_name.strip().lower() == name.strip().lower():
            return i
    return -1


def _get(row: list, idx: int, default="") -> str:
    if idx < 0 or idx >= len(row):
        return default
    val = row[idx]
    return str(val).strip() if val is not None else default


# ── Phase 1 — AM Team (Requests Summary) ─────────────────────

async def fetch_am_jobs() -> list[dict]:
    """
    Pull Phase 1 jobs from Requests Summary.
    Only rows where Request_Status = 'Initiated'.
    """
    if not ZOHO_VIEW_ID_AM:
        raise RuntimeError("ZOHO_VIEW_ID_AM not set")

    cols, rows = await _fetch_view(ZOHO_VIEW_ID_AM)

    # Column indices
    idx_id      = _col_index(cols, "Request_ID")
    idx_reg     = _col_index(cols, "Vehicle_reg")
    idx_name    = _col_index(cols, "Client_name")
    idx_email   = _col_index(cols, "Customer_email")
    idx_phone   = _col_index(cols, "Client_cell_no")
    idx_status  = _col_index(cols, "Request Status")
    idx_reason  = _col_index(cols, "Reason")
    idx_date    = _col_index(cols, "Initiated_Date")

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    jobs = []

    for row in rows:
        status = _get(row, idx_status)
        if status.strip().lower() != "initiated":
            continue  # only pending AM jobs

        reason_raw = _get(row, idx_reason)
        reason     = reason_raw.lower().strip().replace(" ", "_").replace("-", "_")

        job_id = _get(row, idx_id)
        if not job_id:
            continue

        email = _get(row, idx_email)
        if not email:
            logger.warning(f"AM job {job_id} has no email — skipping")
            continue

        jobs.append({
            "id":               job_id,
            "vehicle_reg":      _get(row, idx_reg),
            "client_name":      _get(row, idx_name),
            "client_email":     email.lower(),
            "client_phone":     _get(row, idx_phone),
            "phase":            1,
            "reason":           reason or None,
            "reason_display":   reason_raw,         # original text for email
            "initiated_date":   _excel_date(_get(row, idx_date)),
            "scheduled_date":   None,
            "solver_name":      None,
            "solver_phone":     None,
            "solver_email":     None,
            "job_status":       "pending",
            "reason_logged_at": now_iso,
            "source":           "zoho",
            "zoho_row_id":      job_id,
            "emails_sent":      0,
            "status":           "awaiting_reply",
            "flagged_manual":   False,
        })

    logger.info(f"Zoho AM sync: {len(jobs)} initiated jobs fetched")
    return jobs


# ── Phase 2 — Solver Team (Scheduled Not Valued) ──────────────

async def fetch_solver_jobs() -> list[dict]:
    """
    Pull Phase 2 jobs from Scheduled Not Valued.
    All rows in this view are by definition pending.
    """
    if not ZOHO_VIEW_ID_SOLVER:
        raise RuntimeError("ZOHO_VIEW_ID_SOLVER not set")

    cols, rows = await _fetch_view(ZOHO_VIEW_ID_SOLVER)

    idx_id           = _col_index(cols, "ID")
    idx_solver_name  = _col_index(cols, "solver_name")
    idx_solver_phone = _col_index(cols, "solver_contact")
    idx_solver_email = _col_index(cols, "solver_email")
    idx_reg          = _col_index(cols, "vehicle_reg")
    idx_email        = _col_index(cols, "Customer_email")
    idx_phone        = _col_index(cols, "client_no")
    idx_schedule     = _col_index(cols, "schedule_date")
    idx_reason       = _col_index(cols, "latest_pending_reason")

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    jobs = []

    for row in rows:
        job_id = _get(row, idx_id)
        if not job_id:
            continue

        email = _get(row, idx_email)
        if not email:
            logger.warning(f"Solver job {job_id} has no email — skipping")
            continue

        reason_raw = _get(row, idx_reason)
        reason     = reason_raw.lower().strip().replace(" ", "_").replace("-", "_")

        solver_phone = _get(row, idx_solver_phone)
        solver_email = _get(row, idx_solver_email)

        jobs.append({
            "id":               f"S-{job_id}",   # prefix to avoid ID clash with AM jobs
            "vehicle_reg":      _get(row, idx_reg),
            "client_name":      "",               # not in this view — filled from email
            "client_email":     email.lower(),
            "client_phone":     _get(row, idx_phone),
            "phase":            2,
            "reason":           reason or None,
            "reason_display":   reason_raw,
            "initiated_date":   None,
            "scheduled_date":   _excel_date(_get(row, idx_schedule)),
            "solver_name":      _get(row, idx_solver_name),
            "solver_phone":     solver_phone,
            "solver_email":     solver_email or None,            
            "job_status":       "pending",
            "reason_logged_at": now_iso,
            "source":           "zoho",
            "zoho_row_id":      job_id,
            "emails_sent":      0,
            "status":           "awaiting_reply",
            "flagged_manual":   False,
        })

    logger.info(f"Zoho Solver sync: {len(jobs)} jobs fetched")
    return jobs


# ── Combined fetch ────────────────────────────────────────────

async def fetch_zoho_jobs() -> list[dict]:
    """Fetch both AM and Solver jobs. Used by scheduler and manual sync."""
    am_jobs     = await fetch_am_jobs()     if ZOHO_VIEW_ID_AM     else []
    solver_jobs = await fetch_solver_jobs() if ZOHO_VIEW_ID_SOLVER else []
    return am_jobs + solver_jobs


# ── Health check ──────────────────────────────────────────────

async def check_zoho_connection() -> dict:
    try:
        await _get_zoho_token()
        return {"status": "connected", "workspace_id": ZOHO_WORKSPACE_ID}
    except Exception as e:
        return {"status": "error", "error": str(e)}
