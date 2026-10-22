"""Loading the insurer list from the Solvit insurer master export (xlsx) or a CSV.

Accepts the master export as-is (columns: id, name, email) as well as our own CSV template
(name, solvit_company_id, aliases, active). Unknown columns, like the contact email, are ignored.
"""

import csv
import io
import os

from sqlalchemy import func

from models import Insurer, db

ID_COLUMNS = ("solvit_company_id", "insurancecompanyrequestid", "company_id", "id")
NAME_COLUMNS = ("name", "company_name", "insurer", "company")


def read_rows(filename: str, data: bytes) -> list[dict]:
    """Returns rows as dicts with lower-cased, underscored header names."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl

        sheet = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        header, body = rows[0], rows[1:]
    else:
        reader = csv.reader(io.StringIO(data.decode("utf-8-sig", errors="replace")))
        header, *body = list(reader) or [[]]

    keys = [str(h or "").strip().lower().replace(" ", "_") for h in header]
    return [
        {k: ("" if v is None else str(v).strip()) for k, v in zip(keys, row)}
        for row in body if any(v not in (None, "") for v in row)
    ]


def _pick(row: dict, columns) -> str:
    return next((row[c] for c in columns if row.get(c)), "")


def upsert(rows: list[dict]) -> tuple[int, int, list[str]]:
    """Upsert by name (case-insensitive). Returns (added, updated, problems)."""
    if rows and not (any(c in rows[0] for c in ID_COLUMNS) and any(c in rows[0] for c in NAME_COLUMNS)):
        return 0, 0, ["The file needs a name column and an id (or solvit_company_id) column."]

    added = updated = 0
    problems = []
    for line_no, row in enumerate(rows, start=2):
        name, company_id = _pick(row, NAME_COLUMNS), _pick(row, ID_COLUMNS)
        if company_id.endswith(".0"):  # numeric IDs read from Excel as floats
            company_id = company_id[:-2]
        if not name or not company_id:
            problems.append(f"Row {line_no}: missing name or ID, skipped")
            continue
        insurer = Insurer.query.filter(func.lower(Insurer.name) == name.lower()).first()
        if insurer:
            updated += 1
        else:
            insurer = Insurer(name=name)
            db.session.add(insurer)
            added += 1
        insurer.solvit_company_id = company_id
        if "aliases" in row:
            insurer.aliases = row["aliases"]
        insurer.active = row.get("active", "").lower() not in ("0", "false", "no", "n")
    db.session.commit()
    return added, updated, problems


def seed_if_empty(path: str | None) -> None:
    """On first start, load INSURERS_SEED_FILE so a fresh environment has a working dropdown."""
    if not path or Insurer.query.first():
        return
    full = path if os.path.isabs(path) else os.path.join(os.path.dirname(os.path.dirname(__file__)), path)
    with open(full, "rb") as f:
        added, _, problems = upsert(read_rows(full, f.read()))
    print(f"Seeded {added} insurers from {path}", *problems, sep="\n")
