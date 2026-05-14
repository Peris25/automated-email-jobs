"""
Database — SQLAlchemy async engine.
Locally:  SQLite via aiosqlite  (no config needed)
Render:   PostgreSQL via asyncpg (DATABASE_URL set automatically)
"""

import os
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import (
    MetaData, Table, Column, Integer, Text,
    Boolean, ForeignKey
)

# ── Connection URL ────────────────────────────────────────────
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

# ── Tables ────────────────────────────────────────────────────
metadata = MetaData()

jobs = Table(
    "jobs", metadata,
    Column("id",                  Text,    primary_key=True),
    Column("vehicle_reg",         Text,    nullable=False),
    Column("client_name",         Text,    nullable=False),
    Column("client_email",        Text,    nullable=False),
    Column("client_phone",        Text),
    Column("phase",               Integer, server_default="1"),
    Column("reason",              Text),
    Column("initiated_date",      Text),
    Column("scheduled_date",      Text),
    Column("solver_name",         Text),
    Column("solver_phone",        Text),
    Column("solver_email",        Text), 
    Column("emails_sent",         Integer, server_default="0"),
    Column("last_email_sent_at",  Text),
    Column("status",              Text,    server_default="awaiting_reply"),
    Column("job_status",          Text,    server_default="pending"),
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
    Column("graph_message_id",     Text),
    Column("internet_message_id",  Text),
    Column("delivery_status",      Text,    server_default="sent"),
    Column("reply_at",             Text),
)


# ── Thin DB wrapper ───────────────────────────────────────────
class _DB:
    """Mimics the databases library interface so api routes need no changes."""

    async def execute(self, query, values: dict | None = None):
        async with engine.begin() as conn:
            if values:
                await conn.execute(query, values)
            else:
                await conn.execute(query)

    async def fetch_all(self, query):
        async with engine.connect() as conn:
            result = await conn.execute(query)
            return result.fetchall()

    async def fetch_one(self, query):
        async with engine.connect() as conn:
            result = await conn.execute(query)
            return result.fetchone()

    async def connect(self): pass
    async def disconnect(self): pass


database = _DB()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
