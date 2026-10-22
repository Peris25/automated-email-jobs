"""Job creation in Solvit, same endpoint and auth as the private valuations tool.

Broker attribution: the job is created with the token of the account in SOLVIT_USERNAME /
SOLVIT_PASSWORD. Point those at the "Self-Initiate" broker alias on the portal and every job
this tool creates is attributed to that broker, with no change to Solvit itself.
"""

import json
import logging
import os
from datetime import datetime

import requests

log = logging.getLogger(__name__)

# Staging: https://solvit.staging9.com   Production: https://login.solvit.limited
SOLVIT_BASE_URL = os.getenv("SOLVIT_BASE_URL", "https://login.solvit.limited").rstrip("/")
SOLVIT_API_URL = os.getenv("SOLVIT_API_URL") or f"{SOLVIT_BASE_URL}/api/request/schedule-initiate-request"
TIMEOUT = 30


def normalize_phone_for_solvit(phone: str) -> str:
    return phone[3:] if phone and phone.startswith("254") else phone


def get_solvit_token() -> str:
    res = requests.post(
        os.getenv("SOLVIT_AUTH_URL"),
        json={"email": os.getenv("SOLVIT_USERNAME"), "password": os.getenv("SOLVIT_PASSWORD")},
        timeout=TIMEOUT,
    )
    res.raise_for_status()
    return res.json().get("token")


def build_payload(req, docs_url: str = "") -> dict:
    when = req.preferred_at or datetime.now()
    comment = f"Self-initiated valuation (request #{req.id}) via SMS link."
    if req.letter_reference:
        comment += f" Insurer ref: {req.letter_reference}."
    if req.location_text:
        comment += f" Location: {req.location_text}."
    if not req.preferred_at:
        comment += " No preferred time given, please schedule with client."
    if docs_url:
        comment += f" Documents: {docs_url}"

    return {
        "customerMobile": normalize_phone_for_solvit(req.phone),
        "vehicleRegNo": req.reg,
        "firstName": req.first_name,
        "lastName": req.last_name,
        "email": req.email,
        "type": "2",
        "siteType": "2",
        "insuranceCompanyRequestId": req.insurer.solvit_company_id,
        "paymentType": os.getenv("SOLVIT_PAYMENT_TYPE", "1"),
        "isSchedule": "1",
        "date": when.strftime("%Y-%m-%d"),
        "time": when.strftime("%H:%M"),
        "latitude": req.latitude if req.latitude is not None else "",
        "longitude": req.longitude if req.longitude is not None else "",
        "comment": comment,
    }


def create_job(req, docs_url: str = "") -> tuple[bool, str]:
    """Returns (success, response text). Never raises, so a Solvit outage holds the request instead."""
    payload = build_payload(req, docs_url)
    log.info("Posting to Solvit: %s", payload)
    try:
        token = get_solvit_token()
        res = requests.post(
            SOLVIT_API_URL,
            json=payload,
            headers={"Content-Type": "application/json", "Authorization": f"{token}"},
            timeout=TIMEOUT,
        )
        body = res.text
        log.info("Solvit responded %s: %s", res.status_code, body)
        return res.ok, json.dumps({"status": res.status_code, "body": body[:2000]})
    except Exception as e:
        log.exception("Solvit post failed")
        return False, json.dumps({"error": str(e)})
