"""What happens when a request is submitted, approved or retried."""

import logging
import os
from datetime import datetime

from flask import request as flask_request

from models import Insurer, SelfInitRequest, db
from services import solvit
from services.verify import verify

log = logging.getLogger(__name__)


def docs_url(req: SelfInitRequest) -> str:
    base = os.getenv("PUBLIC_BASE_URL") or flask_request.host_url
    return f"{base.rstrip('/')}/admin/requests/{req.id}"


def letter_reused(req: SelfInitRequest) -> bool:
    if not req.letter_sha256:
        return False
    return db.session.query(
        SelfInitRequest.query.filter(
            SelfInitRequest.letter_sha256 == req.letter_sha256,
            SelfInitRequest.id != req.id,
            SelfInitRequest.status != "draft",
        ).exists()
    ).scalar()


def send_to_solvit(req: SelfInitRequest) -> None:
    ok, response = solvit.create_job(req, docs_url(req))
    req.solvit_response = response
    if ok:
        req.status = "initiated"
        req.initiated_at = datetime.utcnow()
    else:
        req.status = "send_failed"


def submit(req: SelfInitRequest) -> None:
    """Run the letter check, then either create the job in Solvit or hold for review."""
    insurers = Insurer.query.filter_by(active=True).all()
    letter = {
        "insurer_name": req.letter_insurer_text,
        "letter_date": req.letter_date,
        "registration_number": req.letter_reg,
    }
    result = verify(req.insurer, insurers, letter, req.reg, letter_reused(req))

    req.insurer_match = result.insurer_match
    req.date_ok = result.date_ok
    req.reg_match = result.reg_match
    req.hold_reasons = "\n".join(result.reasons)
    req.submitted_at = datetime.utcnow()

    if result.passed:
        send_to_solvit(req)
    else:
        req.status = "held"
        log.info("Request %s held: %s", req.id, result.reasons)
    db.session.commit()
