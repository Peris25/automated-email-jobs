from datetime import date

from services.verify import best_insurer, insurer_matches, name_score, normalize_name, verify


class Ins:
    def __init__(self, id, name, aliases=""):
        self.id, self.name, self.aliases = id, name, aliases

    def alias_list(self):
        return [a.strip() for a in self.aliases.split(",") if a.strip()]


APA = Ins(1, "APA", "APA Insurance")
BRITAM = Ins(2, "Britam", "British American")
JUBILEE = Ins(3, "Jubilee Allianz")
GA = Ins(4, "GA Insurance")
ALL = [APA, BRITAM, JUBILEE, GA]
TODAY = date(2026, 10, 16)


def test_normalize_strips_letterhead_noise():
    assert normalize_name("APA Insurance Company Ltd.") == "apa"
    assert normalize_name("Britam General Insurance Company (Kenya) Limited") == "britam"


def test_letterhead_variants_match_dropdown():
    assert insurer_matches(APA, ALL, "APA Insurance Company Ltd")
    assert insurer_matches(BRITAM, ALL, "British-American Insurance Company (K) Ltd")
    assert insurer_matches(JUBILEE, ALL, "Jubilee Allianz General Insurance (Kenya) Limited")
    assert insurer_matches(GA, ALL, "GA Insurance Limited")


def test_wrong_insurer_does_not_match():
    assert not insurer_matches(APA, ALL, "Britam General Insurance")
    assert not insurer_matches(GA, ALL, "APA Insurance")


def test_best_insurer_preselects():
    assert best_insurer(ALL, "APA INSURANCE LTD") is APA
    assert best_insurer(ALL, "Some Unknown Underwriters") is None


def test_name_score_handles_typos():
    assert name_score("Britam", "Britan Insurance") > 0.8


def letter(name="APA Insurance Ltd", d=date(2026, 9, 1), reg="KDA 421X"):
    return {"insurer_name": name, "letter_date": d, "registration_number": reg}


def test_clean_letter_passes():
    v = verify(APA, ALL, letter(), "KDA 421X", False, today=TODAY)
    assert v.passed and v.insurer_match and v.date_ok and v.reg_match


def test_old_letter_held():
    v = verify(APA, ALL, letter(d=date(2026, 6, 1)), "KDA 421X", False, today=TODAY)
    assert not v.passed and "older than 90 days" in v.reasons[0]


def test_boundary_90_days_passes():
    v = verify(APA, ALL, letter(d=date(2026, 7, 18)), "KDA 421X", False, today=TODAY)
    assert v.passed


def test_future_and_missing_dates_held():
    assert not verify(APA, ALL, letter(d=date(2026, 12, 1)), "", False, today=TODAY).passed
    assert not verify(APA, ALL, letter(d=None), "", False, today=TODAY).passed


def test_unreadable_insurer_held():
    v = verify(APA, ALL, letter(name=""), "KDA 421X", False, today=TODAY)
    assert not v.passed and "insurer name" in v.reasons[0]


def test_reused_letter_held():
    v = verify(APA, ALL, letter(), "KDA 421X", True, today=TODAY)
    assert not v.passed


def test_reg_mismatch_is_informational_only():
    v = verify(APA, ALL, letter(reg="KCB 100A"), "KDA 421X", False, today=TODAY)
    assert v.passed and v.reg_match is False
