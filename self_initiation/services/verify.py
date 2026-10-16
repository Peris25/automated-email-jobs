"""Letter verification, the gate that replaces "M-Pesa payment succeeded" from the private tool.

A request passes only when:
  1. the insurer read off the letter matches the insurer the client selected (tolerant match), and
  2. the letter is dated within the last LETTER_MAX_AGE_DAYS days, and
  3. the same letter file has not already been used on another request.

Anything else is held for a manual check, never rejected outright. Whether the reg on the
letter matches the reg on the form is recorded for reviewers but does not block in v1.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from difflib import SequenceMatcher

LETTER_MAX_AGE_DAYS = int(os.getenv("LETTER_MAX_AGE_DAYS", "90"))
MATCH_THRESHOLD = 0.85

# Words that differ between letterheads and our list without changing who the insurer is
NOISE_WORDS = {
    "insurance", "assurance", "insurers", "company", "co", "companies", "ltd", "limited",
    "plc", "kenya", "ke", "k", "the", "of", "group", "holdings", "general", "and",
}


def normalize_name(name: str | None) -> str:
    text = (name or "").lower().replace("&", " and ")
    words = re.sub(r"[^a-z0-9 ]", " ", text).split()
    return " ".join(w for w in words if w not in NOISE_WORDS)


def name_score(candidate: str, letter_name: str) -> float:
    """1.0 for an exact normalized match, 0.95 when one name sits inside the other, else similarity."""
    a, b = normalize_name(candidate), normalize_name(letter_name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if f" {a} " in f" {b} " or f" {b} " in f" {a} ":
        return 0.95
    return SequenceMatcher(None, a, b).ratio()


def insurer_score(insurer, letter_name: str) -> float:
    names = [insurer.name, *insurer.alias_list()]
    return max(name_score(n, letter_name) for n in names)


def best_insurer(insurers, letter_name: str):
    """The insurer from our list that best matches the letter, or None if nothing is close enough."""
    scored = [(insurer_score(i, letter_name), i) for i in insurers]
    scored = [s for s in scored if s[0] >= MATCH_THRESHOLD]
    return max(scored, key=lambda s: s[0])[1] if scored else None


def insurer_matches(selected, insurers, letter_name: str) -> bool:
    """Selected insurer must clear the threshold and no other insurer may match the letter better."""
    own = insurer_score(selected, letter_name)
    if own < MATCH_THRESHOLD:
        return False
    return all(insurer_score(i, letter_name) <= own for i in insurers if i.id != selected.id)


@dataclass
class Verification:
    insurer_match: bool
    date_ok: bool
    reg_match: bool | None
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.reasons


def verify(selected, insurers, letter: dict, form_reg: str, letter_reused: bool,
           today: date | None = None) -> Verification:
    today = today or date.today()
    reasons = []

    letter_name = letter.get("insurer_name") or ""
    ins_ok = bool(letter_name) and insurer_matches(selected, insurers, letter_name)
    if not letter_name:
        reasons.append("Could not read the insurer name on the letter")
    elif not ins_ok:
        reasons.append(f'Letter names "{letter_name}" but client selected "{selected.name}"')

    letter_date = letter.get("letter_date")
    date_ok = False
    if not letter_date:
        reasons.append("Could not read the date on the letter")
    elif letter_date > today + timedelta(days=1):
        reasons.append(f"Letter is dated in the future ({letter_date:%d %b %Y})")
    elif (today - letter_date).days > LETTER_MAX_AGE_DAYS:
        reasons.append(f"Letter is dated {letter_date:%d %b %Y}, older than {LETTER_MAX_AGE_DAYS} days")
    else:
        date_ok = True

    if letter_reused:
        reasons.append("This exact letter file was already used on another request")

    letter_reg = letter.get("registration_number") or ""
    reg_match = None
    if letter_reg and form_reg:
        reg_match = re.sub(r"\s", "", letter_reg) == re.sub(r"\s", "", form_reg.upper())

    return Verification(insurer_match=ins_ok, date_ok=date_ok, reg_match=reg_match, reasons=reasons)
