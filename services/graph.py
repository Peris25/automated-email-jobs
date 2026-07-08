"""
Microsoft Graph API service
============================
Handles:
  - OAuth2 client-credentials token acquisition
  - Sending emails via cs-team@solvit.co.ke
  - Polling inbox for replies every 5 minutes
  - Matching replies to jobs via Message-ID threading

Setup steps (do once):
  1. Go to https://entra.microsoft.com → App registrations → New registration
  2. Add API permissions (Application, not Delegated):
       Mail.Send   Mail.Read   Mail.ReadBasic
  3. Click "Grant admin consent"
  4. Certificates & secrets → New client secret → copy the Value
  5. Note your Tenant ID, Client ID
  6. Set the five env vars below
"""

import os
import logging
import httpx
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────
MS_TENANT_ID     = os.getenv("MS_TENANT_ID", "")
MS_CLIENT_ID     = os.getenv("MS_CLIENT_ID", "")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET", "")
SENDER_UPN       = os.getenv("MS_SENDER_UPN", "cs-team@solvit.co.ke")
GRAPH_BASE       = "https://graph.microsoft.com/v1.0"

_token_cache: dict = {}


# ── Token ─────────────────────────────────────────────────────

async def _get_token() -> str:
    """Return a valid access token, refreshing if expired."""
    now = datetime.now(timezone.utc).timestamp()
    if _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["access_token"]

    if not all([MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET]):
        raise RuntimeError(
            "Microsoft Graph credentials not configured. "
            "Set MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET in env vars."
        )

    url = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/token"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, data={
            "client_id":     MS_CLIENT_ID,
            "client_secret": MS_CLIENT_SECRET,
            "grant_type":    "client_credentials",
            "scope":         "https://graph.microsoft.com/.default",
        })
        r.raise_for_status()
        data = r.json()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"]   = now + data.get("expires_in", 3600)
    logger.info("Graph token refreshed")
    return _token_cache["access_token"]


# ── Send email ────────────────────────────────────────────────

async def send_email(
  to_email: str,
  subject: str,
  body: str,
  reply_to_message_id: str | None = None,
  cc_emails: list[str] | None = None,
) -> dict:
    """
    Send an email from cs-team@solvit.co.ke.
    Returns dict with graph_message_id and internet_message_id.
    """
    token = await _get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    payload: dict = {
        "message": {
            "subject": subject,
            "body":    {"contentType": "HTML", "content": body},
            "from":    {"emailAddress": {"address": SENDER_UPN}},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
            "replyTo": [{"emailAddress": {"address": SENDER_UPN}}],
            **({"ccRecipients": [{"emailAddress": {"address": cc}} for cc in cc_emails]} if cc_emails else {}),
        },
        "saveToSentItems": True,
    }

    # Thread replies to this email if we have a prior message ID
    if reply_to_message_id:
        payload["message"]["conversationId"] = reply_to_message_id

    async with httpx.AsyncClient(timeout=30) as client:
        SEND_AS_UPN = os.getenv("MS_SEND_AS_UPN", SENDER_UPN)
        r = await client.post(
            f"{GRAPH_BASE}/users/{SEND_AS_UPN}/sendMail",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()

    # Fetch the sent message to get its IDs for reply tracking
    graph_id, internet_id = await _get_last_sent_ids(token)
    logger.info(f"Email sent to {to_email} | subject: {subject}")
    return {"graph_message_id": graph_id, "internet_message_id": internet_id}


async def _get_last_sent_ids(token: str) -> tuple[str, str]:
    """Retrieve the most recently sent message's IDs."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{GRAPH_BASE}/users/{SENDER_UPN}/sentItems",
                headers={"Authorization": f"Bearer {token}"},
                params={"$top": 1, "$select": "id,internetMessageId", "$orderby": "sentDateTime desc"},
            )
            r.raise_for_status()
            msgs = r.json().get("value", [])
            if msgs:
                return msgs[0].get("id", ""), msgs[0].get("internetMessageId", "")
    except Exception as e:
        logger.warning(f"Could not fetch sent message IDs: {e}")
    return "", ""


# ── Poll for replies ──────────────────────────────────────────

async def fetch_unread_replies() -> list[dict]:
    """
    Poll the SENDER_UPN mailbox inbox for unread replies.
    support@ is a regular/shared mailbox (not an M365 group), so we read it
    via /users/{upn}/mailFolders/inbox/messages.
    """
    token = await _get_token()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{GRAPH_BASE}/users/{SENDER_UPN}/mailFolders/inbox/messages",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "$filter":  "isRead eq false",
                    "$top":     50,
                    "$orderby": "receivedDateTime desc",
                    "$select":  "id,subject,from,receivedDateTime,internetMessageId,internetMessageHeaders",
                },
            )
            r.raise_for_status()
            messages = r.json().get("value", [])
    except Exception as e:
        logger.error(f"Inbox poll failed for {SENDER_UPN}: {e}")
        return []

    results = []
    for msg in messages:
        # Pull the In-Reply-To header so replies thread back to the sent email
        in_reply_to = None
        for h in (msg.get("internetMessageHeaders") or []):
            if h.get("name", "").lower() == "in-reply-to":
                in_reply_to = (h.get("value") or "").strip()
                break

        results.append({
            "graph_message_id": msg.get("id", ""),
            "in_reply_to":      in_reply_to,
            "subject":          msg.get("subject", ""),
            "from_email":       (msg.get("from", {}) or {}).get("emailAddress", {}).get("address", ""),
            "received_at":      msg.get("receivedDateTime", ""),
        })

        # Mark read so the same reply isn't reprocessed on the next poll
        if msg.get("id"):
            await _mark_read(token, msg["id"])

    return results


async def _mark_read(token: str, message_id: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.patch(
                f"{GRAPH_BASE}/users/{SENDER_UPN}/messages/{message_id}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"isRead": True},
            )
    except Exception as e:
        logger.warning(f"Could not mark message {message_id} as read: {e}")


# ── Integration health check ──────────────────────────────────

async def check_graph_connection() -> dict:
    """Returns status dict for the settings panel integration card."""
    try:
        await _get_token()
        return {"status": "connected", "sender": SENDER_UPN}
    except Exception as e:
        return {"status": "error", "error": str(e)}
