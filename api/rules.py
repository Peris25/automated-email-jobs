"""
Rules and Templates API
GET/PUT /api/rules           — timing rules
GET/PUT /api/templates/{id}  — email templates
POST    /api/rules/seed      — seed defaults into DB
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

# ── Default rules ─────────────────────────────────────────────
DEFAULT_RULES = [
    {"id": "unreachable",   "reason": "Unreachable",   "timing": "next_day_8am",      "delay_minutes": 15,  "delay_days": 0, "followup_days": 3, "enabled": True},
    {"id": "not_picking",   "reason": "Not picking",   "timing": "next_day_8am",   "delay_minutes": 0,   "delay_days": 0, "followup_days": 3, "enabled": True},
    {"id": "not_ready", "reason": "Not ready", "timing": "days", "delay_minutes": 0, "delay_days": 3, "followup_days": 3, "enabled": True},
]

# ── Default templates ─────────────────────────────────────────
DEFAULT_TEMPLATES = [
    {
        "id": "phase1_not_picking", "phase": 1, "reason": "not_picking",
        "label": "Phase 1 — Not picking",
        "subject": "Your vehicle valuation — {{vehicle_reg}}",
        "body": "Dear {{client_name}},\n\nWe have been trying to reach you by phone regarding the valuation of your vehicle ({{vehicle_reg}}).\n\nPlease reply to this email or call us so we can confirm a date and time that works for you.\n\nWarm regards,\nSolvit AM Team",
    },
    {
        "id": "phase1_unreachable", "phase": 1, "reason": "unreachable",
        "label": "Phase 1 — Unreachable",
        "subject": "We've been unable to reach you — {{vehicle_reg}}",
        "body": "Dear {{client_name}},\n\nWe have made several attempts to contact you regarding the valuation of your vehicle ({{vehicle_reg}}) but have been unable to reach you.\n\nPlease reply to this email at your earliest convenience.\n\nWarm regards,\nSolvit AM Team",
    },
    {
        "id": "phase1_not_ready", "phase": 1, "reason": "not_ready",
        "label": "Phase 1 — Not ready",
        "subject": "Valuation update needed — {{vehicle_reg}}",
        "body": "Dear {{client_name}},\n\nWe understand you may not have been ready for the inspection. We are following up to check whether you are now available to proceed.\n\nPlease reply and we will arrange a new time.\n\nWarm regards,\nSolvit AM Team",
    },
    {
        "id": "phase2_not_picking", "phase": 2, "reason": "not_picking",
        "label": "Phase 2 — Not picking",
        "subject": "Inspection confirmation needed — {{vehicle_reg}}",
        "body": "Dear {{client_name}},\n\nYour vehicle inspection has been scheduled for {{scheduled_date}} with {{solver_name}}, but we have been unable to confirm the appointment with you by phone.\n\nPlease confirm by replying to this email.\n\nWarm regards,\nSolvit AM Team",
    },
    {
        "id": "phase2_unreachable", "phase": 2, "reason": "unreachable",
        "label": "Phase 2 — Unreachable",
        "subject": "Inspection appointment — action required — {{vehicle_reg}}",
        "body": "Dear {{client_name}},\n\nWe have an inspection booked for your vehicle ({{vehicle_reg}}) on {{scheduled_date}} with {{solver_name}} and have been trying to reach you to confirm.\n\nIf we do not hear from you, we may need to release this appointment. Please reply to confirm or reschedule.\n\nWarm regards,\nSolvit AM Team",
    },
    {
        "id": "phase2_not_ready", "phase": 2, "reason": "not_ready",
        "label": "Phase 2 — Not ready",
        "subject": "Ready to reschedule your inspection? — {{vehicle_reg}}",
        "body": "Dear {{client_name}},\n\nWe noted you were not ready for the inspection. We are checking in to see whether you are now available.\n\nPlease reply with a preferred date and time.\n\nWarm regards,\nSolvit AM Team",
    },
    {
        "id": "followup", "phase": 0, "reason": None,
        "label": "3-day follow-up (all)",
        "subject": "Following up — vehicle valuation {{vehicle_reg}}",
        "body": "Dear {{client_name}},\n\nWe sent you an email a few days ago regarding your vehicle valuation ({{vehicle_reg}}) and haven't heard back.\n\nThis is our final automated follow-up. Please reply or call us on +254 700 000 000.\n\nWarm regards,\nSolvit AM Team",
    },
]


# ── Seed endpoint ─────────────────────────────────────────────

@router.post("/rules/seed")
async def seed_defaults(user=Depends(get_current_user)):
    """Seed default rules and templates into DB. Safe to run multiple times."""
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


# ── Rules CRUD ────────────────────────────────────────────────

@router.get("/rules")
async def get_rules(user=Depends(get_current_user)):
    rows = await database.fetch_all(email_rules.select().order_by(email_rules.c.id))
    if not rows:
        # Auto-seed on first load
        await seed_defaults(user)
        rows = await database.fetch_all(email_rules.select().order_by(email_rules.c.id))
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


# ── Templates CRUD ────────────────────────────────────────────

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
