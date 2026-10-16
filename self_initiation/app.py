"""Self-Initiation Valuation Tool.

A fork of the private valuations tool for insurer-paid valuations: the client uploads the
insurer's instruction letter and their logbook, picks the insurer, and once the letter checks
out the job is created in Solvit under the self-initiate broker. No payment step.
"""

import logging
import os
import secrets

from dotenv import load_dotenv
from flask import Flask, abort, redirect, request, session

from models import db

load_dotenv()
logging.basicConfig(level=logging.INFO)


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres://"):  # Render and Heroku style URLs
        url = url.replace("postgres://", "postgresql://", 1)
    return url or "sqlite:///self_initiation_dev.db"


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)

    # Same cookie setup as the private tool so the page works inside the website iframe
    # (SESSION_COOKIE_SECURE=false is only for local http development, where iframes don't matter)
    secure = os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false"
    app.config["SESSION_COOKIE_SECURE"] = secure
    app.config["SESSION_COOKIE_SAMESITE"] = "None" if secure else "Lax"
    app.config["SQLALCHEMY_DATABASE_URI"] = _database_url()
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # two files of up to 10 MB plus form fields
    if config:
        app.config.update(config)

    db.init_app(app)

    from views.admin import admin_bp
    from views.public import public_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()

    @app.before_request
    def check_csrf():
        if request.method == "POST" and not app.config.get("TESTING_SKIP_CSRF"):
            token = session.get("csrf_token")
            if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
                abort(400, "Your session expired. Please reload the page and try again.")

    @app.context_processor
    def inject_csrf():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return {"csrf_token": session["csrf_token"]}

    @app.after_request
    def allow_iframe(response):
        # Embeddable on the website, as with the private tool. Admin pages stay un-embeddable.
        if request.path.startswith("/admin"):
            response.headers["X-Frame-Options"] = "DENY"
        else:
            response.headers.pop("X-Frame-Options", None)
            allowed = os.getenv("FRAME_ANCESTORS", "*")
            response.headers["Content-Security-Policy"] = f"frame-ancestors {allowed}"
        return response

    @app.get("/")
    def index():
        return redirect("/self-initiate")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=False)
