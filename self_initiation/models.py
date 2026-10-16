from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Insurer(db.Model):
    """An insurer clients can pick, resolved to its Solvit company ID on submit."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    solvit_company_id = db.Column(db.String(64), nullable=False)
    # Comma separated alternative names seen on letterheads, e.g. "British American"
    aliases = db.Column(db.Text, default="")
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def alias_list(self):
        return [a.strip() for a in (self.aliases or "").split(",") if a.strip()]


# Request lifecycle:
#   draft      documents uploaded, client has not confirmed details yet
#   initiated  verification passed (or approved by staff) and the job was created in Solvit
#   held       verification failed, waiting for staff review
#   send_failed verification passed but the Solvit API call failed, staff can retry
#   rejected   staff rejected the request after review
STATUSES = ("draft", "initiated", "held", "send_failed", "rejected")


class SelfInitRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default="draft", nullable=False, index=True)
    source = db.Column(db.String(100))  # e.g. ?src=sms-reminder, for campaign reporting

    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    email = db.Column(db.String(200))
    phone = db.Column(db.String(20))

    reg = db.Column(db.String(20))
    reg_from_logbook = db.Column(db.String(20))

    insurer_id = db.Column(db.Integer, db.ForeignKey("insurer.id"))
    insurer = db.relationship("Insurer")

    # What was read off the instruction letter
    letter_insurer_text = db.Column(db.String(300))
    letter_date = db.Column(db.Date)
    letter_reg = db.Column(db.String(20))
    letter_reference = db.Column(db.String(200))
    letter_sha256 = db.Column(db.String(64), index=True)

    # Verification outcome
    insurer_match = db.Column(db.Boolean)
    date_ok = db.Column(db.Boolean)
    reg_match = db.Column(db.Boolean)  # informational only in v1, never blocks
    hold_reasons = db.Column(db.Text)  # newline separated

    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    location_text = db.Column(db.String(300))
    preferred_at = db.Column(db.DateTime)

    solvit_response = db.Column(db.Text)
    reviewed_by_note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    submitted_at = db.Column(db.DateTime)
    initiated_at = db.Column(db.DateTime)

    documents = db.relationship("Document", backref="request", cascade="all, delete-orphan")

    @property
    def full_name(self):
        return " ".join(p for p in (self.first_name, self.last_name) if p)

    def hold_reason_list(self):
        return [r for r in (self.hold_reasons or "").split("\n") if r]

    def document(self, kind):
        return next((d for d in self.documents if d.kind == kind), None)


class Document(db.Model):
    """Uploaded files live in the database so they survive redeploys on ephemeral disks."""
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("self_init_request.id"), nullable=False)
    kind = db.Column(db.String(20), nullable=False)  # "letter" or "logbook"
    filename = db.Column(db.String(255))
    mime_type = db.Column(db.String(100))
    data = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
