"""
Solvit Valuation Communication Portal — Backend
================================================
Run locally:   uvicorn main:app --reload --port 8000
Deploy:        Render Web Service pointing to this file

Data sources (switchable via env var DATA_SOURCE):
  - "csv"   → upload CSV/Excel files via /api/upload/jobs
  - "zoho"  → live sync from Zoho Analytics
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from db.database import init_db
from api import jobs, activity, dashboard, auth, upload, zoho_sync
from scheduler.runner import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    start_scheduler()
    yield
    # Shutdown (nothing to clean up)


app = FastAPI(
    title="Solvit Valuation Communication Portal API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ────────────────────────────────────────────────
app.include_router(auth.router,      prefix="/api/auth",      tags=["Auth"])
app.include_router(jobs.router,      prefix="/api",           tags=["Jobs"])
app.include_router(activity.router,  prefix="/api",           tags=["Activity"])
app.include_router(dashboard.router, prefix="/api",           tags=["Dashboard"])
app.include_router(upload.router,    prefix="/api/upload",    tags=["Upload"])
app.include_router(zoho_sync.router, prefix="/api/zoho",      tags=["Zoho"])

# ── Serve portal static files (same origin as API) ───────────
PORTAL_DIR = os.getenv("PORTAL_DIR", os.path.join(os.path.dirname(__file__), "portal"))
if os.path.exists(PORTAL_DIR) and os.path.exists(os.path.join(PORTAL_DIR, "index.html")):
    app.mount("/static", StaticFiles(directory=PORTAL_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def serve_portal():
        return FileResponse(os.path.join(PORTAL_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
