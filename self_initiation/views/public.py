"""Client journey: SMS link -> upload documents -> confirm details -> done."""

import hashlib
import logging
import os
import re
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session
from werkzeug.utils import secure_filename

from models import Document, Insurer, SelfInitRequest, db
from services import ocr, workflow
from services.verify import best_insurer

log = logging.getLogger(__name__)
public_bp = Blueprint("public", __name__, template_folder="../templates")

MAX_FILE_BYTES = 10 * 1024 * 1024
FILE_SIGNATURES = {  # sniff the content so a renamed file can't slip through
    b"%PDF": "application/pdf",
    b"\x89PNG": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
}


def normalize_phone(raw: str) -> str | None:
    """Accept 07XX / 01XX / +2547XX / 2547XX and return 254XXXXXXXXX, or None if invalid."""
    digits = re.sub(r"\D", "", raw or "")
    if re.fullmatch(r"0[17]\d{8}", digits):
        digits = "254" + digits[1:]
    return digits if re.fullmatch(r"254[17]\d{8}", digits) else None


def read_upload(field: str) -> tuple[bytes, str, str] | None:
    """Returns (data, mime_type, filename) or None if the upload is missing or not an image/PDF."""
    f = request.files.get(field)
    if not f or not f.filename:
        return None
    data = f.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        return None
    mime = next((m for sig, m in FILE_SIGNATURES.items() if data.startswith(sig)), None)
    if not mime:
        return None
    return data, mime, secure_filename(f.filename) or field


def current_request() -> SelfInitRequest | None:
    req_id = session.get("request_id")
    return db.session.get(SelfInitRequest, req_id) if req_id else None


@public_bp.route("/self-initiate", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        if request.args.get("src"):
            session["source"] = request.args["src"][:100]
        return render_template("upload.html", form={})

    form = request.form
    errors = []
    first_name = form.get("firstName", "").strip()
    last_name = form.get("lastName", "").strip()
    email = form.get("email", "").strip()
    phone = normalize_phone(form.get("phone", ""))
    if not first_name or not last_name:
        errors.append("Please enter your first and last name.")
    if not phone:
        errors.append("Please enter a valid Kenyan mobile number, e.g. 0712 345 678.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        errors.append("Please enter a valid email address.")

    letter = read_upload("letter")
    logbook = read_upload("logbook")
    if not letter:
        errors.append("Please upload the instruction letter from your insurer as a PDF, JPG or PNG (max 10 MB).")
    if not logbook:
        errors.append("Please upload your logbook as a PDF, JPG or PNG (max 10 MB).")

    if errors:
        for e in errors:
            flash(e)
        return render_template("upload.html", form=form), 400

    req = SelfInitRequest(
        status="draft",
        source=session.get("source"),
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        letter_sha256=hashlib.sha256(letter[0]).hexdigest(),
    )
    for kind, (data, mime, filename) in (("letter", letter), ("logbook", logbook)):
        req.documents.append(Document(kind=kind, data=data, mime_type=mime, filename=filename))

    # Both reads run now so the next screen can pre-fill the plate and pre-select the insurer
    req.reg_from_logbook = ocr.read_logbook_reg(logbook[0], logbook[1])
    req.reg = req.reg_from_logbook
    letter_info = ocr.read_letter(letter[0], letter[1])
    req.letter_insurer_text = letter_info["insurer_name"]
    req.letter_date = letter_info["letter_date"]
    req.letter_reg = letter_info["registration_number"]
    req.letter_reference = letter_info["reference"]

    db.session.add(req)
    db.session.commit()
    session["request_id"] = req.id
    return redirect("/self-initiate/details")


@public_bp.route("/self-initiate/details", methods=["GET", "POST"])
def details():
    req = current_request()
    if not req:
        return redirect("/self-initiate")
    if req.status != "draft":
        return redirect("/self-initiate/done")

    insurers = Insurer.query.filter_by(active=True).order_by(Insurer.name).all()

    if request.method == "GET":
        suggested = best_insurer(insurers, req.letter_insurer_text) if req.letter_insurer_text else None
        return render_template(
            "details.html", req=req, insurers=insurers,
            selected_id=suggested.id if suggested else None,
            maps_api_key=os.getenv("GEOPLACES_API_KEY"),
        )

    form = request.form
    errors = []
    reg = ocr.normalize_reg(form.get("reg"))
    if not reg:
        errors.append("Please enter your vehicle's registration number.")

    insurer = None
    try:
        insurer = db.session.get(Insurer, int(form.get("insurer_id", "")))
    except ValueError:
        pass
    if not insurer or not insurer.active:
        errors.append("Please select your insurer.")

    preferred_at = None
    if form.get("preferred_at"):
        try:
            preferred_at = datetime.strptime(form["preferred_at"], "%Y-%m-%dT%H:%M")
            if preferred_at < datetime.now():
                errors.append("The preferred time is in the past. Pick a later time or leave it blank.")
        except ValueError:
            errors.append("Please pick a valid preferred date and time, or leave it blank.")

    if errors:
        for e in errors:
            flash(e)
        return render_template(
            "details.html", req=req, insurers=insurers,
            selected_id=insurer.id if insurer else None,
            maps_api_key=os.getenv("GEOPLACES_API_KEY"), form=form,
        ), 400

    req.reg = reg
    req.insurer = insurer
    req.preferred_at = preferred_at
    req.location_text = form.get("location", "").strip()[:300] or None
    try:
        req.latitude = float(form["latitude"]) if form.get("latitude") else None
        req.longitude = float(form["longitude"]) if form.get("longitude") else None
    except ValueError:
        req.latitude = req.longitude = None

    workflow.submit(req)
    return redirect("/self-initiate/done")


@public_bp.get("/self-initiate/done")
def done():
    req = current_request()
    if not req or req.status == "draft":
        return redirect("/self-initiate")
    return render_template("done.html", req=req)


@public_bp.get("/self-initiate/new")
def start_over():
    session.pop("request_id", None)
    return redirect("/self-initiate")
