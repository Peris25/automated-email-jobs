"""
Rules and Templates API (v1.2)
================================
Rules are now split across 3 phases × 3 reasons = 9 rules total:
  Phase 1 Scheduling : unreachable, not_picking, not_ready
  Phase 2 Inspection : unreachable, not_picking, not_ready
  Phase 3 Approval   : no_logbook, no_sticker, no_letter

GET/PUT /api/rules           — list / update rules
GET/PUT /api/templates/{id}  — list / update email templates
POST    /api/rules/seed      — seed defaults (idempotent)
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.database import database, email_rules, email_templates
from api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

NOW = lambda: datetime.now(timezone.utc).isoformat()

DEFAULT_RULES = [
    # ── Scheduling (phase 1) ──
    {"id": "scheduling_unreachable", "phase": 1, "reason": "Unreachable",
     "reason_code": "unreachable", "timing": "immediate",
     "delay_minutes": 15, "delay_days": 0, "followup_days": 3, "enabled": True},
    {"id": "scheduling_not_picking", "phase": 1, "reason": "Not picking",
     "reason_code": "not_picking", "timing": "same_day_5pm",
     "delay_minutes": 0, "delay_days": 0, "followup_days": 3, "enabled": True},
    {"id": "scheduling_not_ready", "phase": 1, "reason": "Not ready",
     "reason_code": "not_ready", "timing": "next_day_9am",
     "delay_minutes": 0, "delay_days": 0, "followup_days": 3, "enabled": True},
    # ── Inspection (phase 2) ──
    {"id": "inspection_unreachable", "phase": 2, "reason": "Unreachable",
     "reason_code": "unreachable", "timing": "immediate",
     "delay_minutes": 30, "delay_days": 0, "followup_days": 2, "enabled": True},
    {"id": "inspection_not_picking", "phase": 2, "reason": "Not picking",
     "reason_code": "not_picking", "timing": "same_day_5pm",
     "delay_minutes": 0, "delay_days": 0, "followup_days": 2, "enabled": True},
    {"id": "inspection_not_ready", "phase": 2, "reason": "Not ready",
     "reason_code": "not_ready", "timing": "next_day_9am",
     "delay_minutes": 0, "delay_days": 0, "followup_days": 2, "enabled": True},
    # ── Approval (phase 3) — NEW ──
    {"id": "approval_no_logbook", "phase": 3, "reason": "No logbook",
     "reason_code": "no_logbook", "timing": "same_day_5pm",
     "delay_minutes": 0, "delay_days": 0, "followup_days": 4, "enabled": True},
    {"id": "approval_no_sticker", "phase": 3, "reason": "No sticker",
     "reason_code": "no_sticker", "timing": "same_day_5pm",
     "delay_minutes": 0, "delay_days": 0, "followup_days": 4, "enabled": True},
    {"id": "approval_no_letter", "phase": 3, "reason": "No letter",
     "reason_code": "no_letter", "timing": "same_day_5pm",
     "delay_minutes": 0, "delay_days": 0, "followup_days": 4, "enabled": True},
]

DEFAULT_TEMPLATES = [
    # Existing Scheduling templates (preserved from v1.1)
    {"id": "phase1_not_picking", "phase": 1, "reason": "not_picking",
     "label": "Scheduling — Not picking",
     "subject": "Your vehicle valuation — {{vehicle_reg}}",
     "body": "Dear {{client_name}},\n\nWe have been trying to reach you by phone regarding the valuation of your vehicle ({{vehicle_reg}}).\n\nPlease reply to this email or call us so we can confirm a date and time that works for you.\n\nWarm regards,\nSolvit AM Team"},
    {"id": "phase1_unreachable", "phase": 1, "reason": "unreachable",
     "label": "Scheduling — Unreachable",
     "subject": "We've been unable to reach you — {{vehicle_reg}}",
     "body": "Dear {{client_name}},\n\nWe have made several attempts to contact you regarding the valuation of your vehicle ({{vehicle_reg}}) but have been unable to reach you.\n\nPlease reply to this email at your earliest convenience.\n\nWarm regards,\nSolvit AM Team"},
    {"id": "phase1_not_ready", "phase": 1, "reason": "not_ready",
     "label": "Scheduling — Not ready",
     "subject": "Valuation update needed — {{vehicle_reg}}",
     "body": "Dear {{client_name}},\n\nWe understand you may not have been ready for the inspection. We are following up to check whether you are now available to proceed.\n\nPlease reply and we will arrange a new time.\n\nWarm regards,\nSolvit AM Team"},
    # Inspection templates (preserved from v1.1)
    {"id": "phase2_not_picking", "phase": 2, "reason": "not_picking",
     "label": "Inspection — Not picking",
     "subject": "Inspection confirmation needed — {{vehicle_reg}}",
     "body": "Dear {{client_name}},\n\nYour vehicle inspection has been scheduled for {{scheduled_date}} with {{solver_name}}, but we have been unable to confirm the appointment with you by phone.\n\nPlease confirm by replying to this email.\n\nWarm regards,\nSolvit AM Team"},
    {"id": "phase2_unreachable", "phase": 2, "reason": "unreachable",
     "label": "Inspection — Unreachable",
     "subject": "Inspection appointment — action required — {{vehicle_reg}}",
     "body": "Dear {{client_name}},\n\nWe have an inspection booked for your vehicle ({{vehicle_reg}}) on {{scheduled_date}} with {{solver_name}} and have been trying to reach you to confirm.\n\nIf we do not hear from you, we may need to release this appointment. Please reply to confirm or reschedule.\n\nWarm regards,\nSolvit AM Team"},
    {"id": "phase2_not_ready", "phase": 2, "reason": "not_ready",
     "label": "Inspection — Not ready",
     "subject": "Ready to reschedule your inspection? — {{vehicle_reg}}",
     "body": "Dear {{client_name}},\n\nWe noted you were not ready for the inspection. We are checking in to see whether you are now available.\n\nPlease reply with a preferred date and time.\n\nWarm regards,\nSolvit AM Team"},
    # NEW — Approval templates
    {"id": "phase3_approval", "phase": 3, "reason": None,
     "label": "Approval — Documents requested (consolidated)",
     "subject": "Documents needed to approve your vehicle valuation — {{vehicle_reg}}",
     "body": """Dear {{client_name}},

Your vehicle valuation report for {{vehicle_reg}} has been completed by our inspection team, but we are unable to finalise the approval because the following document(s) have not yet been received:

{{missing_documents_list}}

To proceed with the approval, kindly send the document(s) by reply to this email. Both our Customer Service and Valuations teams are copied so either team can receive your reply.

If you have any questions, please reply or contact us directly.

Warm regards,
Solvit Valuations Team"""},
    {"id": "phase3_no_logbook", "phase": 3, "reason": "no_logbook",
     "label": "Approval — No logbook (single)",
     "subject": "Logbook needed for your vehicle valuation — {{vehicle_reg}}",
     "body": """Dear {{client_name}},

Your vehicle valuation report for {{vehicle_reg}} has been completed but we need a copy of the vehicle logbook to finalise the approval.

Please reply to this email with a clear photo or scan of the logbook.

Warm regards,
Solvit Valuations Team"""},
    {"id": "phase3_no_sticker", "phase": 3, "reason": "no_sticker",
     "label": "Approval — No insurance sticker (single)",
     "subject": "Insurance sticker needed for your vehicle valuation — {{vehicle_reg}}",
     "body": """Dear {{client_name}},

Your vehicle valuation report for {{vehicle_reg}} is ready for approval but we need a copy of the current insurance sticker.

Please reply to this email with a clear photo of the sticker.

Warm regards,
Solvit Valuations Team"""},
    {"id": "phase3_no_letter", "phase": 3, "reason": "no_letter",
     "label": "Approval — No valuation letter (single)",
     "subject": "Valuation letter needed — {{vehicle_reg}}",
     "body": """Dear {{client_name}},

Your vehicle valuation for {{vehicle_reg}} requires a signed valuation request letter on your organisation's letterhead before we can finalise the approval.

Please reply to this email with the letter attached.

Warm regards,
Solvit Valuations Team"""},
    {"id": "phase3_followup", "phase": 3, "reason": "followup",
     "label": "Approval — Follow-up reminder",
     "subject": "Reminder: documents still pending — {{vehicle_reg}}",
     "body": """Dear {{client_name}},

We previously wrote to request the following document(s) for the approval of your vehicle valuation ({{vehicle_reg}}):

{{missing_documents_list}}

Your report is held pending receipt of the above. Please reply to this email with the document(s) at your earliest convenience.

Warm regards,
Solvit Valuations Team"""},
    # Generic follow-up (preserved)
    {"id": "followup", "phase": 0, "reason": None,
     "label": "3-day follow-up (Scheduling/Inspection)",
     "subject": "Following up — vehicle valuation {{vehicle_reg}}",
     "body": "Dear {{client_name}},\n\nWe sent you an email a few days ago regarding your vehicle valuation ({{vehicle_reg}}) and haven't heard back.\n\nThis is our final automated follow-up. Please reply or call us on +254 700 000 000.\n\nWarm regards,\nSolvit AM Team"},
]


@router.post("/rules/seed")
async def seed_defaults(user=Depends(get_current_user)):
    """Seed rules + templates. Idempotent."""
    now = NOW()
    rules_added = 0
    templates_added = 0

    for rule in DEFAULT_RULES:
        existing = await database.fetch_one(
            email_rules.select().where(email_rules.c.id == rule["id"])
        )
        if not existing:
            await database.execute(email_rules.insert().values(**rule, updated_at=now))
            rules_added += 1

    for tmpl in DEFAULT_TEMPLATES:
        existing = await database.fetch_one(
            email_templates.select().where(email_templates.c.id == tmpl["id"])
        )
        if not existing:
            await database.execute(email_templates.insert().values(**tmpl, updated_at=now))
            templates_added += 1

    return {"rules_added": rules_added, "templates_added": templates_added}


@router.get("/rules")
async def get_rules(user=Depends(get_current_user)):
    rows = await database.fetch_all(
        email_rules.select().order_by(email_rules.c.phase, email_rules.c.reason_code)
    )
    if not rows:
        await seed_defaults(user)
        rows = await database.fetch_all(
            email_rules.select().order_by(email_rules.c.phase, email_rules.c.reason_code)
        )
    return rows


class RuleUpdate(BaseModel):
    timing:         str
    delay_minutes:  int = 0
    delay_days:     int = 0
    followup_days:  int = 3
    enabled:        bool = True


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, body: RuleUpdate, user=Depends(get_current_user)):
    existing = await database.fetch_one(
        email_rules.select().where(email_rules.c.id == rule_id)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")

    await database.execute(
        email_rules.update()
        .where(email_rules.c.id == rule_id)
        .values(**body.model_dump(), updated_at=NOW())
    )
    return {"ok": True}


@router.get("/templates")
async def get_templates(user=Depends(get_current_user)):
    rows = await database.fetch_all(
        email_templates.select().order_by(email_templates.c.phase, email_templates.c.reason)
    )
    if not rows:
        await seed_defaults(user)
        rows = await database.fetch_all(
            email_templates.select().order_by(email_templates.c.phase, email_templates.c.reason)
        )
    return rows


class TemplateUpdate(BaseModel):
    subject: str
    body:    str


@router.put("/templates/{template_id}")
async def update_template(template_id: str, body: TemplateUpdate, user=Depends(get_current_user)):
    existing = await database.fetch_one(
        email_templates.select().where(email_templates.c.id == template_id)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")

    await database.execute(
        email_templates.update()
        .where(email_templates.c.id == template_id)
        .values(subject=body.subject, body=body.body, updated_at=NOW())
    )
    return {"ok": True}
