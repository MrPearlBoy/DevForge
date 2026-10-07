from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.orchestrator import workflow_engine
from app.orchestrator.state import CodeArtifact, CodeFile, TestReport as WorkflowTestReport, WorkflowState


def test_heal_context_includes_tests_and_stops_when_mock_repeats_code(tmp_path, monkeypatch) -> None:
    source = "def value():\n    return 1\n"
    test_source = "from src.core import value\n\ndef test_value():\n    assert value() == 2\n"
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "core.py").write_text(source, encoding="utf-8")
    (tmp_path / "tests" / "test_core.py").write_text(test_source, encoding="utf-8")
    monkeypatch.setattr(workflow_engine, "workspace_root", lambda _project_id: tmp_path)

    state = WorkflowState(
        project_id="test-project",
        stage="coding",
        status="running",
        code=CodeArtifact(files=[CodeFile(path="src/core.py", content=source)]),
        tests=WorkflowTestReport(passed=False, failed_count=1, summary="1 failed"),
        feedback={"code": "TEST_FAILURES:\nFAILED tests/test_core.py::test_value"},
        skip_code_gate=True,
    )
    engine = workflow_engine.WorkflowEngine.__new__(workflow_engine.WorkflowEngine)
    engine.project_id = "test-project"
    engine.name = "Test Project"
    engine.task = "Build a test project"
    engine.state = state
    engine.client = SimpleNamespace(name="mock")
    engine._sync = lambda: None
    engine._emit = AsyncMock()
    failures: list[str] = []

    async def fail(message: str) -> None:
        failures.append(message)

    engine._fail = fail
    contexts: list[dict] = []

    async def coding_run(_agent, ctx, _emit, _client):
        contexts.append(ctx)
        return CodeArtifact(files=[CodeFile(path="src/core.py", content=source)])

    monkeypatch.setattr(workflow_engine.CodingAgent, "run", coding_run)

    asyncio.run(engine._stage_coding())

    assert contexts[0]["mode"] == "heal"
    assert "FAILED tests/test_core.py::test_value" in contexts[0]["feedback"]
    existing = {item["path"]: item["content"] for item in contexts[0]["existing_files"]}
    assert existing["tests/test_core.py"] == test_source
    assert existing["src/core.py"] == source
    assert failures and "made no implementation changes" in failures[0]
    assert "deterministic mock provider" in failures[0]


def test_heal_applies_changed_files_and_preserves_unchanged_code(tmp_path, monkeypatch) -> None:
    old_source = "def value():\n    return 1\n"
    fixed_source = "def value():\n    return 2\n"
    unchanged_source = "def other():\n    return 'kept'\n"
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "core.py").write_text(old_source, encoding="utf-8")
    (tmp_path / "src" / "other.py").write_text(unchanged_source, encoding="utf-8")
    (tmp_path / "tests" / "test_core.py").write_text("def test_value():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(workflow_engine, "workspace_root", lambda _project_id: tmp_path)

    state = WorkflowState(
        project_id="test-project",
        stage="coding",
        status="running",
        code=CodeArtifact(
            files=[
                CodeFile(path="src/core.py", content=old_source),
                CodeFile(path="src/other.py", content=unchanged_source),
            ]
        ),
        tests=WorkflowTestReport(passed=False, failed_count=1, summary="1 failed"),
        feedback={"code": "TEST_FAILURES:\nFAILED tests/test_core.py::test_value"},
        skip_code_gate=True,
    )
    engine = workflow_engine.WorkflowEngine.__new__(workflow_engine.WorkflowEngine)
    engine.project_id = "test-project"
    engine.name = "Test Project"
    engine.task = "Build a test project"
    engine.state = state
    engine.client = SimpleNamespace(name="ollama")
    engine._sync = lambda: None
    engine._emit = AsyncMock()
    engine._fail = AsyncMock()

    async def coding_run(_agent, _ctx, _emit, _client):
        return CodeArtifact(files=[CodeFile(path="src/core.py", content=fixed_source)])

    monkeypatch.setattr(workflow_engine.CodingAgent, "run", coding_run)

    asyncio.run(engine._stage_coding())

    merged = {item.path: item.content for item in state.code.files}
    assert merged == {"src/core.py": fixed_source, "src/other.py": unchanged_source}
    assert (tmp_path / "src" / "core.py").read_text(encoding="utf-8") == fixed_source
    assert (tmp_path / "src" / "other.py").read_text(encoding="utf-8") == unchanged_source
    assert state.stage == "testing"
    assert not state.skip_code_gate
    engine._fail.assert_not_awaited()


def test_repair_reruns_the_existing_tests_without_regenerating_them(tmp_path, monkeypatch) -> None:
    test_source = "def test_existing_suite():\n    assert True\n"
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_existing.py"
    test_file.write_text(test_source, encoding="utf-8")
    monkeypatch.setattr(workflow_engine, "workspace_root", lambda _project_id: tmp_path)

    state = WorkflowState(
        project_id="test-project",
        stage="testing",
        status="running",
        code=CodeArtifact(files=[CodeFile(path="src/core.py", content="")]),
        tests=WorkflowTestReport(passed=False, failed_count=1, summary="1 failed"),
    )
    engine = workflow_engine.WorkflowEngine.__new__(workflow_engine.WorkflowEngine)
    engine.project_id = "test-project"
    engine.name = "Test Project"
    engine.task = "Build a test project"
    engine.state = state
    engine.client = SimpleNamespace(name="mock")
    engine._sync = lambda: None
    engine._emit = AsyncMock()
    session = SimpleNamespace(add=lambda _result: None, commit=lambda: None)

    class FakeSessionContext:
        def __enter__(self):
            return session

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(workflow_engine, "SessionLocal", FakeSessionContext)
    monkeypatch.setattr(
        workflow_engine.runner,
        "run_pytest",
        lambda _workspace, _timeout: {
            "passed": True,
            "total": 1,
            "passed_count": 1,
            "failed_count": 0,
            "error_count": 0,
            "exit_code": 0,
            "duration_s": 0.01,
            "summary": "1 passed",
            "output": "1 passed in 0.01s",
            "failures": [],
        },
    )
    testing_run = AsyncMock(side_effect=AssertionError("tests should not be regenerated during repair"))
    monkeypatch.setattr(workflow_engine.TestingAgent, "run", testing_run)

    asyncio.run(engine._stage_testing())

    testing_run.assert_not_awaited()
    assert test_file.read_text(encoding="utf-8") == test_source
    assert state.tests and state.tests.passed
    assert state.stage == "security"
