"""
Migration script — v1.4 (Solver-summary-only uploads + Call back reason)
========================================================================
Relaxes jobs.client_email from NOT NULL to nullable.
Idempotent — safe to run multiple times.

USAGE:
    python migrations/004_relax_client_email.py
"""

import asyncio
import os
import sys
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import engine, init_db, IS_SQLITE


async def column_is_nullable(conn, table: str, column: str) -> bool:
    if IS_SQLITE:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        for row in result.fetchall():
            if row[1] == column:
                return row[3] == 0
        return False
    else:
        result = await conn.execute(text(
            f"SELECT is_nullable FROM information_schema.columns "
            f"WHERE table_name='{table}' AND column_name='{column}'"
        ))
        row = result.fetchone()
        return row and row[0] == 'YES'


async def migrate():
    print("Running migration: 004_relax_client_email")

    here = os.path.dirname(os.path.abspath(__file__))
    for prior in ("002_add_approval_phase.py", "003_add_solver_directory.py"):
        prior_path = os.path.join(here, prior)
        if os.path.exists(prior_path):
            print(f"  · ensuring {prior} has been applied...")
            import importlib.util
            spec = importlib.util.spec_from_file_location("_prior_migration", prior_path)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            await mod.migrate()
            print(f"  · {prior} done")

    await init_db()
    print("  ✓ all tables ensured")

    async with engine.begin() as conn:
        already_nullable = await column_is_nullable(conn, "jobs", "client_email")
        if already_nullable:
            print("  · jobs.client_email is already nullable — nothing to do")
            print("\nMigration v1.4 complete (no-op).")
            return

        if IS_SQLITE:
            print("  · SQLite detected — rebuilding jobs table to relax NOT NULL on client_email")
            await conn.execute(text("PRAGMA foreign_keys=OFF"))

            cols_info = await conn.execute(text("PRAGMA table_info(jobs)"))
            cols = cols_info.fetchall()
            col_defs = []
            col_names = []
            for cid, name, ctype, notnull, dflt, pk in cols:
                col_names.append(name)
                pieces = [name, ctype or 'TEXT']
                if pk:
                    pieces.append('PRIMARY KEY')
                if notnull and name != 'client_email':
                    pieces.append('NOT NULL')
                if dflt is not None:
                    pieces.append(f"DEFAULT {dflt}")
                col_defs.append(' '.join(pieces))

            new_table_sql = f"CREATE TABLE jobs_new ({', '.join(col_defs)})"
            await conn.execute(text(new_table_sql))
            copy_sql = f"INSERT INTO jobs_new ({', '.join(col_names)}) SELECT {', '.join(col_names)} FROM jobs"
            await conn.execute(text(copy_sql))
            await conn.execute(text("DROP TABLE jobs"))
            await conn.execute(text("ALTER TABLE jobs_new RENAME TO jobs"))
            await conn.execute(text("PRAGMA foreign_keys=ON"))
            print("  ✓ rebuilt jobs table — client_email now nullable")
        else:
            await conn.execute(text("ALTER TABLE jobs ALTER COLUMN client_email DROP NOT NULL"))
            print("  ✓ relaxed NOT NULL on jobs.client_email")

    print("\nMigration v1.4 complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
