"""
Zoho Analytics integration service
====================================
Syncs pending jobs from a Zoho Analytics view into the local DB.

Setup:
  1. Go to https://api-console.zoho.com → Self Client
  2. Generate grant token with scopes:
       ZohoAnalytics.data.read,ZohoAnalytics.metadata.read
  3. Exchange for refresh + access tokens (one-time — see README)
  4. Find your Workspace ID and View ID in Zoho Analytics URL:
       https://analytics.zoho.com/workspace/{WORKSPACE_ID}/view/{VIEW_ID}
  5. Set the env vars below

Column mapping:
  The ZOHO_COLUMN_MAP below maps Zoho column names → our DB field names.
  Edit it to match your actual Zoho view column headers.
"""

import os
import logging
import httpx
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────
ZOHO_CLIENT_ID     = os.getenv("ZOHO_CLIENT_ID", "")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET", "")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN", "")
ZOHO_WORKSPACE_ID  = os.getenv("ZOHO_WORKSPACE_ID", "")
ZOHO_VIEW_ID       = os.getenv("ZOHO_VIEW_ID", "")
ZOHO_DC            = os.getenv("ZOHO_DC", "com")       # com | eu | in | au

_zoho_token_cache: dict = {}

# ── Column mapping: Zoho column name → DB field ───────────────
# Edit these to match your actual Zoho view column headers exactly.
ZOHO_COLUMN_MAP = {
    "Job ID":           "id",
    "Vehicle Reg":      "vehicle_reg",
    "Client Name":      "client_name",
    "Client Email":     "client_email",
    "Client Phone":     "client_phone",
    "Phase":            "phase",
    "Reason Code":      "reason",           # expects: not_picking | unreachable | not_ready
    "Initiated Date":   "initiated_date",
    "Scheduled Date":   "scheduled_date",
    "Solver Name":      "solver_name",
    "Solver Phone":     "solver_phone",
    "Job Status":       "job_status",
    "Reason Logged At": "reason_logged_at",
}

# ── Token ─────────────────────────────────────────────────────

async def _get_zoho_token() -> str:
    now = datetime.now(timezone.utc).timestamp()
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


# ── Fetch rows ────────────────────────────────────────────────

async def fetch_zoho_jobs() -> list[dict]:
    """
    Fetch all rows from the configured Zoho Analytics view.
    Returns list of dicts mapped to our DB field names.
    """
    if not all([ZOHO_WORKSPACE_ID, ZOHO_VIEW_ID]):
        raise RuntimeError("ZOHO_WORKSPACE_ID and ZOHO_VIEW_ID must be set.")

    token = await _get_zoho_token()
    url = (
        f"https://analyticsapi.zoho.{ZOHO_DC}/restapi/v2"
        f"/workspaces/{ZOHO_WORKSPACE_ID}/views/{ZOHO_VIEW_ID}/data"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            url,
            headers={"Authorization": f"Zoho-oauthtoken {token}"},
            params={"CONFIG": '{"responseFormat":"json"}'},
        )
        r.raise_for_status()
        payload = r.json()

    raw_data    = payload.get("data", {})
    column_meta = raw_data.get("columns", [])
    rows        = raw_data.get("rows", [])

    # Build column index → db field name
    col_map = {}
    for i, col in enumerate(column_meta):
        col_name = col.get("columnName") or col.get("name", "")
        db_field = ZOHO_COLUMN_MAP.get(col_name)
        if db_field:
            col_map[i] = db_field

    jobs = []
    for row in rows:
        job: dict = {"source": "zoho"}
        for idx, field in col_map.items():
            if idx < len(row):
                job[field] = row[idx]

        # Defaults for fields the view may not expose
        job.setdefault("emails_sent", 0)
        job.setdefault("status", "awaiting_reply")
        job.setdefault("job_status", "pending")

        # Normalise reason code to lowercase underscored
        if "reason" in job and job["reason"]:
            job["reason"] = (
                job["reason"].lower()
                .replace(" ", "_")
                .replace("-", "_")
            )

        if job.get("id"):
            job["zoho_row_id"] = job["id"]
            jobs.append(job)

    logger.info(f"Zoho sync: fetched {len(jobs)} jobs")
    return jobs


# ── Health check ──────────────────────────────────────────────

async def check_zoho_connection() -> dict:
    try:
        await _get_zoho_token()
        return {"status": "connected", "workspace_id": ZOHO_WORKSPACE_ID}
    except Exception as e:
        return {"status": "error", "error": str(e)}
