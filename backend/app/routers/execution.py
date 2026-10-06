"""Manual execution endpoints: re-run tests, re-run security scan,
git operations and historical log retrieval."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import SecurityFinding, TestResult
from app.db.session import get_db
from app.execution import git_service, preview, runner
from app.routers.projects import _get_project_or_404
from app.utils.files import workspace_root

router = APIRouter(prefix="/api/projects/{project_id}/execution", tags=["execution"])
settings = get_settings()


@router.post("/preview/start")
async def start_preview(project_id: str, db: Session = Depends(get_db)) -> dict:
    _get_project_or_404(db, project_id)
    try:
        await asyncio.to_thread(preview.start, project_id)
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"preview_url": f"/api/projects/{project_id}/execution/preview/"}


@router.post("/preview/stop", status_code=204)
async def stop_preview(project_id: str, db: Session = Depends(get_db)) -> None:
    _get_project_or_404(db, project_id)
    await asyncio.to_thread(preview.stop, project_id)


@router.api_route("/preview/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def preview_request(
    project_id: str,
    path: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    _get_project_or_404(db, project_id)
    port = preview.get_port(project_id)
    if port is None:
        raise HTTPException(409, "preview is not running; start it from the Preview tab")
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 1_000_000:
        raise HTTPException(413, "preview request body exceeds 1 MB")
    body = await request.body()
    if len(body) > 1_000_000:
        raise HTTPException(413, "preview request body exceeds 1 MB")
    try:
        status, content_type, content = await asyncio.to_thread(
            preview.proxy_request,
            port,
            request.method,
            path,
            request.url.query,
            body,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except (OSError, TimeoutError) as exc:
        raise HTTPException(502, f"preview server request failed: {exc}") from exc
    return Response(
        content=content,
        status_code=status,
        media_type=content_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/retest")
async def retest(project_id: str, db: Session = Depends(get_db)) -> dict:
    _get_project_or_404(db, project_id)
    ws = workspace_root(project_id)
    if not (ws / "tests").is_dir():
        raise HTTPException(400, "workspace has no tests/ directory yet")
    report = await asyncio.to_thread(runner.run_pytest, ws, settings.test_timeout)
    db.add(
        TestResult(
            project_id=project_id,
            run_number=1,
            passed=report["passed"],
            total=report["total"],
            failed=report["failed_count"],
            exit_code=report["exit_code"],
            duration_s=report["duration_s"],
            summary=report["summary"],
            output=report["output"][:40000],
        )
    )
    db.commit()
    return report


@router.post("/rescan")
async def rescan(project_id: str, db: Session = Depends(get_db)) -> dict:
    _get_project_or_404(db, project_id)
    ws = workspace_root(project_id)
    if not (ws / "src").is_dir():
        raise HTTPException(400, "workspace has no src/ directory yet")
    report = await asyncio.to_thread(runner.run_security_scan, ws, settings.scan_timeout)
    db.query(SecurityFinding).filter_by(project_id=project_id, status="open").update({"status": "resolved"})
    for f in report["findings"]:
        db.add(
            SecurityFinding(
                project_id=project_id,
                severity=f["severity"],
                category=f["category"],
                message=f["message"],
                file=f.get("file") or None,
                line=f.get("line"),
            )
        )
    db.commit()
    return report


@router.post("/git/commit")
async def git_commit(project_id: str, db: Session = Depends(get_db)) -> dict:
    p = _get_project_or_404(db, project_id)
    ws = workspace_root(project_id)
    info = await asyncio.to_thread(git_service.deliver, ws, p.name)
    return info


@router.get("/git/info")
async def git_info(project_id: str, db: Session = Depends(get_db)) -> dict:
    _get_project_or_404(db, project_id)
    return git_service.describe(workspace_root(project_id))


@router.get("/logs")
async def get_logs(project_id: str, limit: int = Query(default=200, le=1000), db: Session = Depends(get_db)) -> list[dict]:
    from app.db.models import WorkflowEvent

    _get_project_or_404(db, project_id)
    rows = (
        db.query(WorkflowEvent)
        .filter(WorkflowEvent.project_id == project_id)
        .order_by(WorkflowEvent.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "type": r.type,
            "stage": r.stage,
            "message": r.message,
            "payload": r.payload,
            "ts": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reversed(rows)
    ]
