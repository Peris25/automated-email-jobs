"""Internal pages: the review queue for held requests and the insurer list."""

import csv
import io
import os
import secrets
from functools import wraps

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session
from sqlalchemy import func

from models import STATUSES, Document, Insurer, SelfInitRequest, db
from services import workflow

admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="../templates")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(f"/admin/login?next={request.path}")
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        expected = os.getenv("ADMIN_PASSWORD", "")
        if expected and secrets.compare_digest(request.form.get("password", ""), expected):
            session["is_admin"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/admin") else "/admin/")
        flash("Wrong password." if expected else "ADMIN_PASSWORD is not set on the server.")
    return render_template("admin/login.html")


@admin_bp.get("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect("/admin/login")


@admin_bp.get("/")
@login_required
def requests_list():
    status = request.args.get("status", "held")
    counts = dict(
        db.session.query(SelfInitRequest.status, func.count()).group_by(SelfInitRequest.status).all()
    )
    query = SelfInitRequest.query
    if status in STATUSES:
        query = query.filter_by(status=status)
    rows = query.order_by(SelfInitRequest.created_at.desc()).limit(200).all()
    return render_template("admin/requests.html", rows=rows, status=status, counts=counts,
                           statuses=STATUSES)


@admin_bp.get("/requests/<int:req_id>")
@login_required
def request_detail(req_id):
    req = db.session.get(SelfInitRequest, req_id) or abort(404)
    insurers = Insurer.query.order_by(Insurer.name).all()
    return render_template("admin/request_detail.html", req=req, insurers=insurers)


@admin_bp.post("/requests/<int:req_id>/approve")
@login_required
def approve(req_id):
    """Staff checked the documents: create the job in Solvit (also used to retry a failed send)."""
    req = db.session.get(SelfInitRequest, req_id) or abort(404)
    if req.status not in ("held", "send_failed"):
        flash("Only held or failed requests can be approved.")
        return redirect(f"/admin/requests/{req.id}")

    if request.form.get("insurer_id", "").isdigit():
        insurer = db.session.get(Insurer, int(request.form["insurer_id"]))
        if insurer:
            req.insurer = insurer
    if not req.insurer:
        flash("Pick an insurer before approving.")
        return redirect(f"/admin/requests/{req.id}")
    if request.form.get("reg"):
        from services.ocr import normalize_reg
        req.reg = normalize_reg(request.form["reg"])
    req.reviewed_by_note = request.form.get("note", "").strip() or req.reviewed_by_note

    workflow.send_to_solvit(req)
    db.session.commit()
    flash("Job created in Solvit." if req.status == "initiated"
          else "Solvit did not accept the job. See the response below and retry.")
    return redirect(f"/admin/requests/{req.id}")


@admin_bp.post("/requests/<int:req_id>/reject")
@login_required
def reject(req_id):
    req = db.session.get(SelfInitRequest, req_id) or abort(404)
    if req.status not in ("held", "send_failed"):
        flash("Only held or failed requests can be rejected.")
        return redirect(f"/admin/requests/{req.id}")
    req.status = "rejected"
    req.reviewed_by_note = request.form.get("note", "").strip() or req.reviewed_by_note
    db.session.commit()
    flash("Request rejected.")
    return redirect("/admin/")


@admin_bp.get("/documents/<int:doc_id>")
@login_required
def document(doc_id):
    doc = db.session.get(Document, doc_id) or abort(404)
    return Response(
        doc.data, mimetype=doc.mime_type,
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )


@admin_bp.route("/insurers", methods=["GET", "POST"])
@login_required
def insurers():
    if request.method == "POST":
        insurer_id = request.form.get("id")
        name = request.form.get("name", "").strip()
        company_id = request.form.get("solvit_company_id", "").strip()
        if not name or not company_id:
            flash("Name and Solvit company ID are both required.")
            return redirect("/admin/insurers")
        insurer = db.session.get(Insurer, int(insurer_id)) if insurer_id else Insurer()
        clash = Insurer.query.filter(func.lower(Insurer.name) == name.lower(), Insurer.id != insurer.id).first()
        if clash:
            flash(f'An insurer called "{clash.name}" already exists.')
            return redirect("/admin/insurers")
        insurer.name = name
        insurer.solvit_company_id = company_id
        insurer.aliases = request.form.get("aliases", "").strip()
        insurer.active = request.form.get("active") == "on"
        db.session.add(insurer)
        db.session.commit()
        flash(f"Saved {insurer.name}.")
        return redirect("/admin/insurers")

    rows = Insurer.query.order_by(Insurer.active.desc(), Insurer.name).all()
    return render_template("admin/insurers.html", rows=rows)


def import_insurers_csv(text: str) -> tuple[int, int, list[str]]:
    """Upsert by name. Columns: name, solvit_company_id, aliases (optional), active (optional)."""
    added = updated = 0
    problems = []
    reader = csv.DictReader(io.StringIO(text))
    fields = {(f or "").strip().lower(): f for f in reader.fieldnames or []}
    if "name" not in fields or "solvit_company_id" not in fields:
        return 0, 0, ["The CSV needs at least the columns: name, solvit_company_id"]

    for line_no, row in enumerate(reader, start=2):
        get = lambda col: (row.get(fields.get(col, ""), "") or "").strip()  # noqa: E731
        name, company_id = get("name"), get("solvit_company_id")
        if not name or not company_id:
            problems.append(f"Line {line_no}: missing name or ID, skipped")
            continue
        insurer = Insurer.query.filter(func.lower(Insurer.name) == name.lower()).first()
        if insurer:
            updated += 1
        else:
            insurer = Insurer(name=name)
            db.session.add(insurer)
            added += 1
        insurer.solvit_company_id = company_id
        if "aliases" in fields:
            insurer.aliases = get("aliases")
        active = get("active").lower()
        insurer.active = active not in ("0", "false", "no", "n")
    db.session.commit()
    return added, updated, problems


@admin_bp.post("/insurers/import")
@login_required
def insurers_import():
    f = request.files.get("file")
    if not f:
        flash("Choose a CSV file to import.")
        return redirect("/admin/insurers")
    added, updated, problems = import_insurers_csv(f.read().decode("utf-8-sig", errors="replace"))
    flash(f"Imported insurers: {added} added, {updated} updated.")
    for p in problems:
        flash(p)
    return redirect("/admin/insurers")
