"""
Email templates — HTML versions of all automated emails.
Edit the text here (or move to DB later for UI editing).

Variables available in every template:
  {client_name}, {vehicle_reg}, {phase},
  {scheduled_date}, {solver_name}, {solver_phone}
"""

from datetime import datetime


def _base_html(body_content: str) -> str:
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; color: #333; margin: 0; padding: 0; background: #f5f5f5; }}
    .container {{ max-width: 580px; margin: 30px auto; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .header {{ background: #1a73e8; padding: 28px 32px; }}
    .header h1 {{ color: #fff; margin: 0; font-size: 20px; font-weight: 600; }}
    .header p {{ color: rgba(255,255,255,0.85); margin: 4px 0 0; font-size: 14px; }}
    .body {{ padding: 32px; }}
    .body p {{ line-height: 1.7; margin: 0 0 16px; }}
    .highlight {{ background: #f0f7ff; border-left: 4px solid #1a73e8; padding: 14px 18px; border-radius: 0 6px 6px 0; margin: 20px 0; }}
    .highlight strong {{ display: block; font-size: 13px; color: #666; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
    .cta {{ display: inline-block; background: #1a73e8; color: #fff; text-decoration: none; padding: 12px 28px; border-radius: 6px; font-weight: 600; margin: 8px 0 20px; }}
    .footer {{ background: #f9f9f9; border-top: 1px solid #eee; padding: 20px 32px; font-size: 12px; color: #999; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Solvit Vehicle Valuations</h1>
      <p>cs-team@solvit.co.ke</p>
    </div>
    <div class="body">
      {body_content}
    </div>
    <div class="footer">
      <p>Solvit Ltd · Nairobi, Kenya · This is an automated message. Reply directly to this email to reach our team.</p>
    </div>
  </div>
</body>
</html>
"""


# ── Phase 1 templates (AM scheduling) ────────────────────────

def phase1_not_picking(job: dict) -> tuple[str, str]:
    subject = f"Your vehicle valuation — {job['vehicle_reg']}"
    body = _base_html(f"""
      <p>Dear {job['client_name']},</p>
      <p>We have been trying to reach you by phone regarding the valuation of your vehicle.</p>
      <div class="highlight">
        <strong>Vehicle</strong>
        {job['vehicle_reg']}
      </div>
      <p>We would like to schedule a convenient time for the inspection. Please reply to this email or call us so we can confirm a date and time that works for you.</p>
      <p>This valuation is an important step — we want to make sure it's completed without further delays.</p>
      <p>Warm regards,<br><strong>Solvit AM Team</strong></p>
    """)
    return subject, body


def phase1_unreachable(job: dict) -> tuple[str, str]:
    subject = f"We've been unable to reach you — {job['vehicle_reg']}"
    body = _base_html(f"""
      <p>Dear {job['client_name']},</p>
      <p>We have made several attempts to contact you regarding the scheduled valuation of your vehicle but have been unable to reach you.</p>
      <div class="highlight">
        <strong>Vehicle</strong>
        {job['vehicle_reg']}
      </div>
      <p>Please reply to this email at your earliest convenience so we can reschedule and keep your valuation on track. If the valuation is no longer required, please let us know.</p>
      <p>Warm regards,<br><strong>Solvit AM Team</strong></p>
    """)
    return subject, body


def phase1_not_ready(job: dict) -> tuple[str, str]:
    subject = f"Valuation update needed — {job['vehicle_reg']}"
    body = _base_html(f"""
      <p>Dear {job['client_name']},</p>
      <p>We understand you may not have been ready for the inspection when we last spoke. We are following up to check whether you are now available to proceed.</p>
      <div class="highlight">
        <strong>Vehicle</strong>
        {job['vehicle_reg']}
      </div>
      <p>Please reply to this email and we will arrange a new inspection time that suits you.</p>
      <p>Warm regards,<br><strong>Solvit AM Team</strong></p>
    """)
    return subject, body


# ── Phase 2 templates (Solver confirmation) ───────────────────

def phase2_not_picking(job: dict) -> tuple[str, str]:
    subject = f"Inspection confirmation needed — {job['vehicle_reg']}"
    scheduled = job.get("scheduled_date") or "TBC"
    solver = job.get("solver_name") or "our inspector"
    solver_phone = job.get("solver_phone") or ""
    body = _base_html(f"""
      <p>Dear {job['client_name']},</p>
      <p>Your vehicle inspection has been scheduled and our inspector is ready, but we have been unable to confirm the appointment with you by phone.</p>
      <div class="highlight">
        <strong>Vehicle</strong>
        {job['vehicle_reg']}
      </div>
      <div class="highlight">
        <strong>Scheduled date & time</strong>
        {scheduled}
      </div>
      <div class="highlight">
        <strong>Inspector</strong>
        {solver}{(' · ' + solver_phone) if solver_phone else ''}
      </div>
      <p>Please confirm by replying to this email so we can keep the appointment in place.</p>
      <p>Warm regards,<br><strong>Solvit AM Team</strong></p>
    """)
    return subject, body


def phase2_unreachable(job: dict) -> tuple[str, str]:
    subject = f"Inspection appointment — action required — {job['vehicle_reg']}"
    scheduled = job.get("scheduled_date") or "TBC"
    solver = job.get("solver_name") or "our inspector"
    body = _base_html(f"""
      <p>Dear {job['client_name']},</p>
      <p>We have an inspection appointment booked for your vehicle and have been trying to reach you to confirm, without success.</p>
      <div class="highlight">
        <strong>Vehicle</strong>
        {job['vehicle_reg']}
      </div>
      <div class="highlight">
        <strong>Appointment</strong>
        {scheduled} with {solver}
      </div>
      <p>If we do not hear from you, we may need to release this appointment slot. Please reply to confirm or reschedule.</p>
      <p>Warm regards,<br><strong>Solvit AM Team</strong></p>
    """)
    return subject, body


def phase2_not_ready(job: dict) -> tuple[str, str]:
    subject = f"Ready to reschedule your inspection? — {job['vehicle_reg']}"
    body = _base_html(f"""
      <p>Dear {job['client_name']},</p>
      <p>We noted that you were not ready for the inspection when we last spoke. We are checking in to see whether you are now available to confirm a new date.</p>
      <div class="highlight">
        <strong>Vehicle</strong>
        {job['vehicle_reg']}
      </div>
      <p>Simply reply to this email with a preferred date and time and we will arrange everything from our side.</p>
      <p>Warm regards,<br><strong>Solvit AM Team</strong></p>
    """)
    return subject, body


# ── Follow-up template (3-day, any phase/reason) ─────────────

def followup(job: dict) -> tuple[str, str]:
    subject = f"Following up — vehicle valuation {job['vehicle_reg']}"
    body = _base_html(f"""
      <p>Dear {job['client_name']},</p>
      <p>We sent you an email a few days ago regarding your vehicle valuation and haven't heard back yet. We want to make sure nothing has been missed.</p>
      <div class="highlight">
        <strong>Vehicle</strong>
        {job['vehicle_reg']}
      </div>
      <p>If you have any questions or need to adjust the timing, please reply to this email and we will sort it out right away. This is our final automated follow-up — after this, a member of the team will be in touch directly.</p>
      <p>Warm regards,<br><strong>Solvit AM Team</strong></p>
    """)
    return subject, body


# ── Template dispatcher ───────────────────────────────────────

TEMPLATE_MAP = {
    # (phase, reason) → function
    (1, "not_picking"):  phase1_not_picking,
    (1, "unreachable"):  phase1_unreachable,
    (1, "not_ready"):    phase1_not_ready,
    (2, "not_picking"):  phase2_not_picking,
    (2, "unreachable"):  phase2_unreachable,
    (2, "not_ready"):    phase2_not_ready,
}


async def get_template_from_db(job: dict, is_followup: bool = False) -> tuple[str, str, str]:
    """
    Fetch template from DB, render variables, return (key, subject, body).
    Falls back to hardcoded templates if DB has none.
    """
    from db.database import database, email_templates

    if is_followup:
        tmpl = await database.fetch_one(
            email_templates.select().where(email_templates.c.id == "followup")
        )
    else:
        phase  = int(job.get("phase", 1))
        reason = (job.get("reason") or "").lower()
        tmpl_id = f"phase{phase}_{reason}"
        tmpl = await database.fetch_one(
            email_templates.select().where(email_templates.c.id == tmpl_id)
        )

    if not tmpl:
        # Fall back to hardcoded
        return get_template(job, is_followup=is_followup)

    def render(text: str) -> str:
        for key, val in job.items():
            text = text.replace(f"{{{{{key}}}}}", str(val or ""))
        return text

    subject = render(tmpl["subject"])
    body    = render(tmpl["body"]).replace("\n", "<br>")
    body    = _base_html(body)
    key     = tmpl["id"]
    return key, subject, body
