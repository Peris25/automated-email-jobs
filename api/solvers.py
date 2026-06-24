"""
Solvers directory — CRUD endpoints (v1.3)
==========================================
The solver directory maps solver name → email so the system can send
consolidated pending-jobs summaries to each solver.

GET    /api/solvers                    — list all solvers
POST   /api/solvers                    — add a solver
PUT    /api/solvers/{id}               — update a solver
DELETE /api/solvers/{id}               — delete a solver
GET    /api/phase-settings             — current per-phase toggles
PUT    /api/phase-settings/{phase}     — update toggle
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import sqlalchemy as sa

from db.database import database, solvers, phase_settings
from api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

NOW = lambda: datetime.now(timezone.utc).isoformat()


# Solvers

class SolverIn(BaseModel):
    name:   str
    email:  str
    phone:  str | None = None
    active: bool = True


@router.get("/solvers")
async def list_solvers(user=Depends(get_current_user)):
    rows = await database.fetch_all(
        solvers.select().order_by(solvers.c.name)
    )
    return rows


@router.post("/solvers")
async def add_solver(body: SolverIn, user=Depends(get_current_user)):
    existing = await database.fetch_one(
        solvers.select().where(sa.func.lower(solvers.c.name) == body.name.strip().lower())
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"A solver named '{existing['name']}' already exists.")

    now = NOW()
    new_id = await database.execute(
        solvers.insert().values(
            name=body.name.strip(),
            email=body.email.strip().lower(),
            phone=(body.phone or "").strip() or None,
            active=body.active,
            created_at=now, updated_at=now,
        )
    )
    return {"ok": True, "id": new_id}


@router.put("/solvers/{solver_id}")
async def update_solver(solver_id: int, body: SolverIn, user=Depends(get_current_user)):
    existing = await database.fetch_one(
        solvers.select().where(solvers.c.id == solver_id)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Solver not found")

    name_clash = await database.fetch_one(
        solvers.select().where(
            (sa.func.lower(solvers.c.name) == body.name.strip().lower()) &
            (solvers.c.id != solver_id)
        )
    )
    if name_clash:
        raise HTTPException(status_code=409, detail=f"Another solver named '{name_clash['name']}' already exists.")

    await database.execute(
        solvers.update()
        .where(solvers.c.id == solver_id)
        .values(
            name=body.name.strip(),
            email=body.email.strip().lower(),
            phone=(body.phone or "").strip() or None,
            active=body.active,
            updated_at=NOW(),
        )
    )
    return {"ok": True}


@router.delete("/solvers/{solver_id}")
async def delete_solver(solver_id: int, user=Depends(get_current_user)):
    existing = await database.fetch_one(
        solvers.select().where(solvers.c.id == solver_id)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Solver not found")
    await database.execute(
        solvers.delete().where(solvers.c.id == solver_id)
    )
    return {"ok": True}


# Phase settings

class PhaseSettingUpdate(BaseModel):
    solver_summary_enabled: bool


@router.get("/phase-settings")
async def list_phase_settings(user=Depends(get_current_user)):
    rows = await database.fetch_all(
        phase_settings.select().order_by(phase_settings.c.phase)
    )
    return rows


@router.put("/phase-settings/{phase}")
async def update_phase_setting(phase: int, body: PhaseSettingUpdate, user=Depends(get_current_user)):
    if phase not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="phase must be 1, 2, or 3")

    existing = await database.fetch_one(
        phase_settings.select().where(phase_settings.c.phase == phase)
    )
    if existing:
        await database.execute(
            phase_settings.update()
            .where(phase_settings.c.phase == phase)
            .values(solver_summary_enabled=body.solver_summary_enabled, updated_at=NOW())
        )
    else:
        await database.execute(
            phase_settings.insert().values(
                phase=phase,
                solver_summary_enabled=body.solver_summary_enabled,
                updated_at=NOW(),
            )
        )
    return {"ok": True}
