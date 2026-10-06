"""Focused tests for the existing-project regeneration API behavior."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.orchestrator.state import WorkflowState
from app.routers import projects


class FakeQuery:
    def filter_by(self, **kwargs):
        self.filters = kwargs
        return self

    def update(self, values):
        self.values = values
        return 0


class FakeDB:
    def __init__(self):
        self.events = []
        self.commits = 0

    def query(self, _model):
        return FakeQuery()

    def commit(self):
        self.commits += 1

    def add(self, event):
        self.events.append(event)


class FakeEngine:
    def __init__(self):
        self._task = None
        self.state = SimpleNamespace(stage="created", status="idle")
        self.started = False

    async def start(self):
        self.started = True
        self.state.stage = "requirement"
        self.state.status = "running"
        return True


def test_completed_project_is_reset_and_restarted() -> None:
    project = SimpleNamespace(
        id="regeneration-test",
        name="Regeneration Test",
        task="The original project request.",
        status="completed",
        stage="completed",
        awaiting_gate=None,
        error=None,
        artifacts="old state",
    )
    db = FakeDB()
    old_engine = FakeEngine()
    new_engine = FakeEngine()

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / project.id
        workspace.mkdir()
        (workspace / "old-generated-file.txt").write_text("old", encoding="utf-8")
        with (
            patch.object(projects, "_get_project_or_404", return_value=project),
            patch.object(projects, "get_engine", side_effect=[old_engine, new_engine]),
            patch.object(projects, "discard_engine") as discard,
            patch.object(projects, "workspace_root", return_value=workspace),
        ):
            result = asyncio.run(
                projects.regenerate_project(
                    project.id,
                    projects.ProjectRegenerate(task="Build the revised browser-based application."),
                    db,
                )
            )

        assert result == {"started": True, "stage": "requirement", "status": "running"}
        assert project.task == "Build the revised browser-based application."
        assert project.stage == "created"
        assert project.status == "idle"
        assert project.awaiting_gate is None
        assert project.error is None
        assert WorkflowState.model_validate_json(project.artifacts).stage == "created"
        assert not (workspace / "old-generated-file.txt").exists()
        assert len(db.events) == 1
        assert db.events[0].stage == "created"
        assert new_engine.started
        discard.assert_called_once_with(project.id)


def test_running_project_cannot_be_regenerated() -> None:
    project = SimpleNamespace(id="active-project", status="running")
    db = FakeDB()
    engine = FakeEngine()

    with (
        patch.object(projects, "_get_project_or_404", return_value=project),
        patch.object(projects, "get_engine", return_value=engine),
        patch.object(projects, "discard_engine") as discard,
    ):
        try:
            asyncio.run(
                projects.regenerate_project(
                    project.id,
                    projects.ProjectRegenerate(task="A valid revised project description."),
                    db,
                )
            )
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("expected regeneration of a running project to be rejected")

    discard.assert_not_called()
    assert not db.events


def main() -> int:
    test_completed_project_is_reset_and_restarted()
    test_running_project_cannot_be_regenerated()
    print("PASS  regeneration starts a clean new run and rejects active projects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
