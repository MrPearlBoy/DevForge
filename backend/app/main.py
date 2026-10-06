"""DevForge API — FastAPI application entry point.

Run from backend/:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.session import SessionLocal, init_db
from app.db.models import Project
from app.execution.preview import stop_all as stop_previews
from app.routers import approvals, execution, projects
from app.llm.client import create_llm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("devforge")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Any workflow that was mid-flight when the backend restarted is marked
    # as interrupted; the user can press Start to resume from the saved stage.
    with SessionLocal() as db:
        stale = db.query(Project).filter(Project.status.in_(["running", "waiting_approval"])).all()
        for p in stale:
            p.status = "interrupted"
            p.error = "backend restarted while the workflow was in flight — press Start to resume"
        if stale:
            db.commit()
            log.warning("marked %d in-flight project(s) as interrupted", len(stale))
    log.info("DevForge API ready (workspaces: %s)", settings.workspaces_path)
    try:
        yield
    finally:
        stop_previews()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "DevForge: AI-Assisted Software Engineering Platform using Multi-Agent "
        "Collaboration. Six specialized agents (Requirement → Architecture → "
        "Coding → Testing → Security → Documentation) are orchestrated by an "
        "explicit state machine with human approval gates and automated "
        "self-healing decision loops, plus sandboxed execution and git delivery."
    ),
    lifespan=lifespan,
)

_origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins != ["*"] else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(approvals.router)
app.include_router(execution.router)


@app.get("/api/health", tags=["meta"])
async def health() -> dict:
    provider = create_llm().name  # cheap: no API call is made
    return {"status": "ok", "service": settings.app_name, "version": settings.version, "llm_provider": provider}
