"""
Database — SQLAlchemy async engine.
Locally:  SQLite via aiosqlite  (no config needed)
Render:   PostgreSQL via asyncpg (DATABASE_URL set automatically)

CHANGES IN THIS VERSION (v1.3):
- Added `solvers` table
- Added `phase_settings` table

PREVIOUS CHANGES (v1.2):
- Added phase 3 (Approval)
- Added `missing_documents` column to jobs
- v1.1 changes preserved: uploads, job_snapshots, phase-split rules, pipeline tracking
"""

import os
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import (
    MetaData, Table, Column, Integer, Text,
    Boolean, ForeignKey
)

# Connection URL
_raw_url = os.getenv("DATABASE_URL", "")

if _raw_url.startswith("postgres://"):
    DATABASE_URL = _raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_url.startswith("postgresql://"):
    DATABASE_URL = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = "sqlite+aiosqlite:///./solvit_dev.db"

IS_SQLITE = DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine = create_async_engine(DATABASE_URL, echo=False, connect_args=connect_args)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Tables
metadata = MetaData()

jobs = Table(
    "jobs", metadata,
    Column("id",                  Text,    primary_key=True),
    Column("vehicle_reg",         Text,    nullable=False),
    Column("client_name",         Text,    nullable=False),
    Column("client_email",        Text),
    Column("client_phone",        Text),
    Column("phase",               Integer, server_default="1"),
    Column("reason",              Text),
    Column("missing_documents",   Text),
    Column("initiated_date",      Text),
    Column("scheduled_date",      Text),
    Column("solver_name",         Text),
    Column("solver_phone",        Text),
    Column("solver_email",        Text),
    Column("emails_sent",         Integer, server_default="0"),
    Column("last_email_sent_at",  Text),
    Column("status",              Text,    server_default="awaiting_reply"),
    Column("job_status",          Text,    server_default="pending"),
    Column("current_status",      Text),
    Column("previous_status",     Text),
    Column("source",              Text,    server_default="csv"),
    Column("zoho_row_id",         Text),
    Column("flagged_manual",      Boolean, server_default="0"),
    Column("reason_logged_at",    Text),
    Column("created_at",          Text),
    Column("updated_at",          Text),
)

email_log = Table(
    "email_log", metadata,
    Column("id",                   Integer, primary_key=True, autoincrement=True),
    Column("job_id",               Text,    ForeignKey("jobs.id"), nullable=False),
    Column("sent_at",              Text),
    Column("template_key",         Text,    nullable=False),
    Column("subject",              Text,    nullable=False),
    Column("to_email",             Text,    nullable=False),
    Column("cc_emails",            Text),
    Column("graph_message_id",     Text),
    Column("internet_message_id",  Text),
    Column("delivery_status",      Text,    server_default="sent"),
    Column("reply_at",             Text),
)

email_rules = Table(
    "email_rules", metadata,
    Column("id",           Text, primary_key=True),
    Column("phase",        Integer, server_default="1"),
    Column("reason",       Text, nullable=False),
    Column("reason_code",  Text),
    Column("timing",       Text, nullable=False),
    Column("delay_days",   Integer, server_default="0"),
    Column("delay_minutes",Integer, server_default="0"),
    Column("followup_days",Integer, server_default="3"),
    Column("enabled",      Boolean, server_default="1"),
    Column("updated_at",   Text),
)

email_templates = Table(
    "email_templates", metadata,
    Column("id",          Text, primary_key=True),
    Column("phase",       Integer, nullable=False),
    Column("reason",      Text),
    Column("label",       Text, nullable=False),
    Column("subject",     Text, nullable=False),
    Column("body",        Text, nullable=False),
    Column("updated_at",  Text),
)

uploads = Table(
    "uploads", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("uploaded_at",     Text,    nullable=False),
    Column("uploaded_by",     Text),
    Column("filename",        Text),
    Column("detected_phase",  Integer),
    Column("row_count",       Integer),
    Column("inserted",        Integer),
    Column("updated",         Integer),
    Column("skipped",         Integer),
    Column("cleared",         Integer, server_default="0"),
    Column("is_baseline",     Boolean, server_default="0"),
    Column("notes",           Text),
)

job_snapshots = Table(
    "job_snapshots", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("upload_id",       Integer, ForeignKey("uploads.id"), nullable=False),
    Column("job_id",          Text,    nullable=False),
    Column("vehicle_reg",     Text),
    Column("phase",           Integer),
    Column("status",          Text),
    Column("reason",          Text),
    Column("missing_documents", Text),
    Column("captured_at",     Text),
)

solvers = Table(
    "solvers", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("name",       Text, nullable=False, unique=True),
    Column("email",      Text, nullable=False),
    Column("phone",      Text),
    Column("active",     Boolean, server_default="1"),
    Column("created_at", Text),
    Column("updated_at", Text),
)

phase_settings = Table(
    "phase_settings", metadata,
    Column("phase",                  Integer, primary_key=True),
    Column("solver_summary_enabled", Boolean, server_default="0"),
    Column("updated_at",             Text),
)


class _DB:
    """Mimics the databases library interface so api routes need no changes."""

    async def execute(self, query, values: dict | None = None):
        async with engine.begin() as conn:
            if values:
                result = await conn.execute(query, values)
            else:
                result = await conn.execute(query)
            try:
                if result.inserted_primary_key:
                    return result.inserted_primary_key[0]
            except Exception:
                pass
            return None

    async def fetch_all(self, query):
        async with engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [dict(r._mapping) for r in rows]

    async def fetch_one(self, query):
        async with engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            return dict(row._mapping) if row else None

    async def connect(self): pass
    async def disconnect(self): pass


database = _DB()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
