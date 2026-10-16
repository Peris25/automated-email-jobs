"""Document reading with GPT-4o vision, repurposed from the private valuations tool.

Two reads only:
  read_logbook_reg()  -> the plate, to pre-fill the form (client can correct it)
  read_letter()       -> insurer, letter date, reg and reference, for verification

Both fail soft: if the model or the file is unreadable they return empty values,
which the verification step then treats as "could not confirm" and holds for review.
"""

import base64
import json
import logging
import os
import re
from datetime import date

import pymupdf

log = logging.getLogger(__name__)

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
MAX_PDF_PAGES = 2


def _image_urls(data: bytes, mime_type: str) -> list[str]:
    """Turn an upload into data URLs the vision model accepts. PDFs are rendered page by page."""
    if mime_type == "application/pdf":
        urls = []
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            for page in list(pdf)[:MAX_PDF_PAGES]:
                png = page.get_pixmap(dpi=150).tobytes("png")
                urls.append("data:image/png;base64," + base64.b64encode(png).decode())
        return urls
    return [f"data:{mime_type};base64," + base64.b64encode(data).decode()]


def _ask(system_prompt: str, data: bytes, mime_type: str) -> dict:
    import openai  # imported lazily so tests and local runs without a key still import this module

    content = [{"type": "text", "text": "Read this document."}]
    content += [{"type": "image_url", "image_url": {"url": u}} for u in _image_urls(data, mime_type)]
    response = openai.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
    )
    text = response.choices[0].message.content or "{}"
    log.info("OCR response: %s", text)
    return json.loads(text)


def normalize_reg(reg: str | None) -> str:
    """'kda 421x' / 'KDA-421X' -> 'KDA 421X'. Kenyan plates are 3 letters, 3 digits, 1 letter."""
    if not reg:
        return ""
    compact = re.sub(r"[^A-Z0-9]", "", reg.upper())
    m = re.fullmatch(r"([A-Z]{3})(\d{3}[A-Z]?)", compact)
    return f"{m.group(1)} {m.group(2)}" if m else compact


def _parse_date(value) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


LOGBOOK_PROMPT = (
    "You read Kenyan vehicle logbooks. Return JSON only: "
    '{"registration_number": "<plate as printed, or empty string>"}'
)

LETTER_PROMPT = (
    "You read motor valuation instruction letters sent by insurance companies (sometimes via a broker). "
    "Identify the insurance company that is instructing or paying for the valuation. This is usually the "
    "letterhead, but if a broker writes on behalf of an insurer, return the insurer, not the broker. "
    "Return JSON only, using empty strings when a value is not present: "
    '{"insurer_name": "<full insurer name as written>", '
    '"letter_date": "<date the letter was written, as YYYY-MM-DD>", '
    '"registration_number": "<vehicle plate mentioned in the letter>", '
    '"reference": "<claim, policy or reference number if any>"}'
)


def read_logbook_reg(data: bytes, mime_type: str) -> str:
    try:
        return normalize_reg(_ask(LOGBOOK_PROMPT, data, mime_type).get("registration_number"))
    except Exception:
        log.exception("Logbook read failed")
        return ""


def read_letter(data: bytes, mime_type: str) -> dict:
    try:
        raw = _ask(LETTER_PROMPT, data, mime_type)
    except Exception:
        log.exception("Letter read failed")
        raw = {}
    return {
        "insurer_name": (raw.get("insurer_name") or "").strip(),
        "letter_date": _parse_date(raw.get("letter_date")),
        "registration_number": normalize_reg(raw.get("registration_number")),
        "reference": (raw.get("reference") or "").strip(),
    }
