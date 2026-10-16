import io
import json
from datetime import date, timedelta

import pytest

from models import Insurer, SelfInitRequest, db
from services import ocr, solvit
from tests.conftest import PDF, PNG

RECENT = date.today() - timedelta(days=10)


@pytest.fixture
def fake_ocr(monkeypatch):
    letter = {"insurer_name": "APA Insurance Company Ltd", "letter_date": RECENT,
              "registration_number": "KDA 421X", "reference": "CLM/123"}
    monkeypatch.setattr(ocr, "read_logbook_reg", lambda data, mime: "KDA 421X")
    monkeypatch.setattr(ocr, "read_letter", lambda data, mime: dict(letter))
    return letter


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_create_job(req, docs_url=""):
        calls.append(solvit.build_payload(req, docs_url))
        return True, json.dumps({"status": 200})

    monkeypatch.setattr(solvit, "create_job", fake_create_job)
    return calls


def upload(client, letter=PDF, phone="0712345678"):
    return client.post("/self-initiate", data={
        "firstName": "Jane", "lastName": "Wanjiku", "phone": phone, "email": "",
        "letter": (io.BytesIO(letter), "letter.pdf"),
        "logbook": (io.BytesIO(PNG), "logbook.png"),
    }, content_type="multipart/form-data")


def insurer_id(name):
    return Insurer.query.filter_by(name=name).one().id


def test_happy_path_creates_job(client, fake_ocr, sent):
    r = upload(client)
    assert r.status_code == 302 and r.location.endswith("/self-initiate/details")

    page = client.get("/self-initiate/details").get_data(as_text=True)
    assert 'value="KDA 421X"' in page
    assert f'value="{insurer_id("APA")}" selected' in page  # pre-selected from the letter

    r = client.post("/self-initiate/details", data={"reg": "kda421x", "insurer_id": insurer_id("APA")})
    assert r.location.endswith("/self-initiate/done")

    req = SelfInitRequest.query.one()
    assert req.status == "initiated" and req.phone == "254712345678"
    assert len(sent) == 1
    p = sent[0]
    assert p["insuranceCompanyRequestId"] == "ID_APA"
    assert p["vehicleRegNo"] == "KDA 421X"
    assert p["customerMobile"] == "712345678"
    assert p["paymentType"] == "1"
    assert p["latitude"] == ""
    assert "CLM/123" in p["comment"] and "/admin/requests/" in p["comment"]
    assert "Your valuation is booked" in client.get("/self-initiate/done").get_data(as_text=True)


def test_wrong_insurer_is_held_not_sent(client, fake_ocr, sent):
    upload(client)
    client.post("/self-initiate/details", data={"reg": "KDA 421X", "insurer_id": insurer_id("Britam")})
    req = SelfInitRequest.query.one()
    assert req.status == "held" and not req.insurer_match
    assert sent == []
    assert "Request received" in client.get("/self-initiate/done").get_data(as_text=True)


def test_reused_letter_is_held(client, fake_ocr, sent):
    upload(client)
    client.post("/self-initiate/details", data={"reg": "KDA 421X", "insurer_id": insurer_id("APA")})
    client.get("/self-initiate/new")
    upload(client)
    client.post("/self-initiate/details", data={"reg": "KDA 421X", "insurer_id": insurer_id("APA")})
    statuses = [r.status for r in SelfInitRequest.query.order_by(SelfInitRequest.id)]
    assert statuses == ["initiated", "held"]


def test_optional_location_and_time_reach_solvit(client, fake_ocr, sent):
    upload(client)
    client.post("/self-initiate/details", data={
        "reg": "KDA 421X", "insurer_id": insurer_id("APA"), "location": "Westlands",
        "latitude": "-1.26", "longitude": "36.80", "preferred_at": "2099-01-05T10:30",
    })
    p = sent[0]
    assert (p["date"], p["time"], p["latitude"]) == ("2099-01-05", "10:30", -1.26)


def test_solvit_failure_is_kept_for_retry(client, fake_ocr, monkeypatch):
    monkeypatch.setattr(solvit, "create_job", lambda req, url="": (False, '{"status": 500}'))
    upload(client)
    client.post("/self-initiate/details", data={"reg": "KDA 421X", "insurer_id": insurer_id("APA")})
    assert SelfInitRequest.query.one().status == "send_failed"


def test_upload_validation(client, fake_ocr):
    r = upload(client, letter=b"not a real file", phone="12345")
    assert r.status_code == 400
    page = r.get_data(as_text=True)
    assert "valid Kenyan mobile" in page and "instruction letter" in page
    assert SelfInitRequest.query.count() == 0


def test_details_requires_insurer(client, fake_ocr, sent):
    upload(client)
    r = client.post("/self-initiate/details", data={"reg": "KDA 421X", "insurer_id": ""})
    assert r.status_code == 400 and sent == []


def test_admin_requires_login(client):
    assert client.get("/admin/").location.startswith("/admin/login")


def login(client):
    client.post("/admin/login", data={"password": "secret"})


def test_admin_approves_held_request(client, fake_ocr, sent):
    upload(client)
    client.post("/self-initiate/details", data={"reg": "KDA 421X", "insurer_id": insurer_id("Britam")})
    req = SelfInitRequest.query.one()
    login(client)
    assert "SI-" in client.get("/admin/").get_data(as_text=True)
    assert client.get(f"/admin/requests/{req.id}").status_code == 200
    doc = req.document("letter")
    assert client.get(f"/admin/documents/{doc.id}").data == PDF

    client.post(f"/admin/requests/{req.id}/approve", data={"insurer_id": insurer_id("APA"), "note": "checked"})
    db.session.refresh(req)
    assert req.status == "initiated" and sent[0]["insuranceCompanyRequestId"] == "ID_APA"


def test_admin_rejects(client, fake_ocr, sent):
    upload(client)
    client.post("/self-initiate/details", data={"reg": "KDA 421X", "insurer_id": insurer_id("Britam")})
    req = SelfInitRequest.query.one()
    login(client)
    client.post(f"/admin/requests/{req.id}/reject", data={"note": "fake letter"})
    db.session.refresh(req)
    assert req.status == "rejected" and sent == []


def test_insurer_csv_import(client):
    login(client)
    csv_text = "name,solvit_company_id,aliases,active\nAPA,NEW_APA,,yes\nCIC,ID_CIC,CIC General,yes\n,missing,,\n"
    client.post("/admin/insurers/import", data={"file": (io.BytesIO(csv_text.encode()), "i.csv")},
                content_type="multipart/form-data")
    assert Insurer.query.filter_by(name="APA").one().solvit_company_id == "NEW_APA"
    assert Insurer.query.filter_by(name="CIC").one().alias_list() == ["CIC General"]


def test_csrf_enforced(app):
    app.config["TESTING_SKIP_CSRF"] = False
    r = app.test_client().post("/admin/login", data={"password": "secret"})
    assert r.status_code == 400


def test_normalize_reg():
    assert ocr.normalize_reg("kda-421x") == "KDA 421X"
    assert ocr.normalize_reg("KBZ 12") == "KBZ12"
