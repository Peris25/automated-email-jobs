"""
Database — async PostgreSQL via asyncpg + SQLAlchemy Core.
On Render: set DATABASE_URL in environment variables.
Locally:   can use SQLite for quick dev (set DB_DRIVER=sqlite).
"""

import os
import databases
import sqlalchemy
from sqlalchemy import (
    MetaData, Table, Column, Integer, Text, Date,
    DateTime, Boolean, func, ForeignKey
)

# ── Connection ────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./solvit_dev.db"   # fallback for local dev
)

# Render gives postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

database = databases.Database(DATABASE_URL)
metadata = MetaData()

# ── Tables ────────────────────────────────────────────────────

jobs = Table(
    "jobs", metadata,
    Column("id",                   Text,    primary_key=True),
    Column("vehicle_reg",          Text,    nullable=False),
    Column("client_name",          Text,    nullable=False),
    Column("client_email",         Text,    nullable=False),
    Column("client_phone",         Text),
    Column("phase",                Integer, nullable=False, default=1),
    Column("reason",               Text),           # not_picking | unreachable | not_ready
    Column("initiated_date",       Text),
    Column("scheduled_date",       Text),           # ISO datetime string or null
    Column("solver_name",          Text),
    Column("solver_phone",         Text),
    Column("emails_sent",          Integer, default=0),
    Column("last_email_sent_at",   Text),
    Column("status",               Text,    default="awaiting_reply"),   # awaiting_reply | replied
    Column("job_status",           Text,    default="pending"),          # pending | scheduled | completed | cancelled
    Column("source",               Text,    default="csv"),              # csv | zoho
    Column("zoho_row_id",          Text),           # for dedup when syncing Zoho
    Column("flagged_manual",       Boolean, default=False),
    Column("reason_logged_at",     Text),           # timestamp when reason was set — drives timing rules
    Column("created_at",           Text,    default=func.now()),
    Column("updated_at",           Text,    default=func.now()),
)

email_log = Table(
    "email_log", metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("job_id",           Text,    ForeignKey("jobs.id"), nullable=False),
    Column("sent_at",          Text,    default=func.now()),
    Column("template_key",     Text,    nullable=False),   # phase1 | phase2 | followup
    Column("subject",          Text,    nullable=False),
    Column("to_email",         Text,    nullable=False),
    Column("graph_message_id", Text),                      # from MS Graph — used for reply threading
    Column("internet_message_id", Text),                   # RFC Message-ID header for inbox matching
    Column("delivery_status",  Text,    default="sent"),   # sent | delivered | opened | replied | bounced
    Column("reply_at",         Text),
)

# ── Engine (for table creation only) ─────────────────────────
SYNC_URL = DATABASE_URL.replace("+asyncpg", "").replace("+aiosqlite", "")
engine = sqlalchemy.create_engine(SYNC_URL.replace("postgresql+", "postgresql+psycopg2+").replace("postgresql+psycopg2+asyncpg", ""), connect_args={"check_same_thread": False} if "sqlite" in SYNC_URL else {})

# Use a simpler sync engine approach
if "sqlite" in DATABASE_URL:
    SYNC_URL_CLEAN = DATABASE_URL.replace("+aiosqlite", "")
else:
    SYNC_URL_CLEAN = DATABASE_URL.replace("+asyncpg", "")

try:
    sync_engine = sqlalchemy.create_engine(
        SYNC_URL_CLEAN,
        connect_args={"check_same_thread": False} if "sqlite" in SYNC_URL_CLEAN else {}
    )
except Exception:
    sync_engine = None


async def init_db():
    """Create tables if they don't exist, then connect the async DB pool."""
    if sync_engine:
        metadata.create_all(sync_engine)
    await database.connect()


async def close_db():
    await database.disconnect()
