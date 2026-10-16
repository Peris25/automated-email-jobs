import os
import sys

import pytest

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["ADMIN_PASSWORD"] = "secret"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app  # noqa: E402
from models import Insurer, db  # noqa: E402

PDF = b"%PDF-1.4 fake letter"
PNG = b"\x89PNG fake logbook"


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/test.db",
        "TESTING": True,
        "TESTING_SKIP_CSRF": True,
    })
    with app.app_context():
        db.create_all()
        db.session.add_all([
            Insurer(name="APA", solvit_company_id="ID_APA", aliases="APA Insurance"),
            Insurer(name="Britam", solvit_company_id="ID_BRITAM", aliases="British American"),
            Insurer(name="Jubilee Allianz", solvit_company_id="ID_JUB"),
        ])
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
