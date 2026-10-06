"""Lifecycle management for generated project preview servers."""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from app.utils.files import workspace_root

log = logging.getLogger(__name__)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, _req, _fp, _code, _msg, _headers, _newurl):
        return None


_opener = build_opener(ProxyHandler({}), _NoRedirect())


@dataclass
class PreviewProcess:
    process: subprocess.Popen
    port: int
    log_lines: deque[str]


_lock = threading.Lock()
_servers: dict[str, PreviewProcess] = {}


def _available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _capture_output(entry: PreviewProcess) -> None:
    if entry.process.stdout:
        for line in entry.process.stdout:
            entry.log_lines.append(line)


def _cleanup(entry: PreviewProcess) -> None:
    if entry.process.poll() is None:
        try:
            entry.process.terminate()
        except ProcessLookupError:
            return
        try:
            entry.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                entry.process.kill()
            except ProcessLookupError:
                return
            entry.process.wait(timeout=5)


def start(project_id: str) -> int:
    """Start a project's local GUI/API server and return its loopback port."""
    workspace = workspace_root(project_id)
    if not (workspace / "src" / "server.py").is_file():
        raise FileNotFoundError("generated project has no src/server.py to run")

    with _lock:
        existing = _servers.get(project_id)
        if existing and existing.process.poll() is None:
            return existing.port
        if existing:
            _servers.pop(project_id, None)
            _cleanup(existing)

        port = _available_port()
        env = {
            key: os.environ[key]
            for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT")
            if key in os.environ
        }
        env["PORT"] = str(port)
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "src.server"],
                cwd=str(workspace),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError:
            log.exception("could not launch preview server for project %s", project_id)
            raise
        entry = PreviewProcess(process=process, port=port, log_lines=deque(maxlen=100))
        _servers[project_id] = entry
        threading.Thread(target=_capture_output, args=(entry,), daemon=True).start()

        deadline = time.monotonic() + 10
        url = f"http://127.0.0.1:{port}/"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                _servers.pop(project_id, None)
                details = "".join(entry.log_lines)[-4000:]
                _cleanup(entry)
                raise RuntimeError(f"generated project server exited during startup. {details}".strip())
            try:
                with _opener.open(url, timeout=0.5):
                    return port
            except (OSError, URLError):
                time.sleep(0.1)

        _servers.pop(project_id, None)
        details = "".join(entry.log_lines)[-4000:]
        _cleanup(entry)
        raise RuntimeError(f"generated project server did not become ready. {details}".strip())


def get_port(project_id: str) -> int | None:
    """Return the running preview server port, if one is active."""
    with _lock:
        entry = _servers.get(project_id)
        if entry is None:
            return None
        if entry.process.poll() is None:
            return entry.port
        _servers.pop(project_id, None)
        _cleanup(entry)
        return None


def stop(project_id: str) -> None:
    """Stop one project's preview process, if running."""
    with _lock:
        entry = _servers.pop(project_id, None)
        if entry:
            _cleanup(entry)


def stop_all() -> None:
    """Stop all preview processes during application shutdown."""
    with _lock:
        entries = list(_servers.values())
        _servers.clear()
        for entry in entries:
            _cleanup(entry)


def proxy_request(port: int, method: str, path: str, query: str, body: bytes) -> tuple[int, str, bytes]:
    """Forward one browser request to a generated server on loopback only."""
    if any(part == ".." for part in path.replace("\\", "/").split("/")):
        raise ValueError("preview path traversal is not allowed")
    target = f"http://127.0.0.1:{port}/{path.lstrip('/')}"
    if query:
        target += f"?{query}"
    request = Request(target, data=body or None, method=method)
    try:
        response = _opener.open(request, timeout=30)
    except HTTPError as exc:
        with exc:
            return exc.code, exc.headers.get("Content-Type", "application/octet-stream"), exc.read(2_000_000)
    with response:
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        return response.status, content_type, response.read(2_000_000)
