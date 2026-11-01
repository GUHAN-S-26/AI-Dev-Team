from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from app.config import Settings
from app.database.repository import Repository
from app.orchestrator.engine import Orchestrator
from app.schemas.models import ProjectRequest
from app.security.audit_logger import AuditLogger
from app.security.auth import AuthService, Role
from app.web.dashboard import DashboardApplication


def _request(
    url: str,
    method: str = "GET",
    body: dict[str, object] | None = None,
    cookie: str | None = None,
    csrf: str | None = None,
) -> tuple[int, dict[str, object]]:
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-CSRF-Token"] = csrf
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_project_delete_removes_scoped_storage_and_database_records(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        projects_dir=tmp_path / "projects",
        workspaces_dir=tmp_path / "workspaces",
    )
    settings.ensure_directories()
    repository = Repository(settings.database_path)
    orchestrator = Orchestrator(settings, repository)
    target = orchestrator.create_project(ProjectRequest(name="Car Landing Page", requirement="Build a car landing page"))
    survivor = orchestrator.create_project(ProjectRequest(name="Keep Me", requirement="Build a safe test page"))
    artifact_dir = settings.data_dir / "artifacts" / target.project_id
    artifact_dir.mkdir(parents=True)
    (Path(target.root_path) / "important.txt").write_text("target", encoding="utf-8")
    (settings.workspaces_dir / target.project_id / "frontend").mkdir(parents=True, exist_ok=True)
    (settings.workspaces_dir / target.project_id / "frontend" / "page.html").write_text("target", encoding="utf-8")
    (artifact_dir / "report.json").write_text("{}", encoding="utf-8")

    app = DashboardApplication(settings, repository)
    try:
        deleted_name = app.workspace.delete_project(target.project_id)
    finally:
        app.workspace.close()

    assert deleted_name == "Car Landing Page"
    assert repository.get_project(target.project_id) is None
    assert repository.list_agents(target.project_id) == []
    assert not Path(target.root_path).exists()
    assert not (settings.workspaces_dir / target.project_id).exists()
    assert not artifact_dir.exists()
    assert repository.get_project(survivor.project_id) is not None
    assert Path(survivor.root_path).exists()


def test_dashboard_delete_requires_csrf_and_removes_project(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        projects_dir=tmp_path / "projects",
        workspaces_dir=tmp_path / "workspaces",
    )
    settings.ensure_directories()
    repository = Repository(settings.database_path)
    app = DashboardApplication(settings, repository)
    auth = AuthService(repository, AuditLogger(repository))
    auth.create_user("admin", "a-secure-admin-password", Role.ADMIN)
    project = app.orchestrator.create_project(
        ProjectRequest(name="Delete Through API", requirement="Build a delete test page")
    )
    server = __import__("http.server", fromlist=["ThreadingHTTPServer"]).ThreadingHTTPServer(
        ("127.0.0.1", 0), app.handler()
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        request = urllib.request.Request(
            base + "/api/auth/login",
            data=json.dumps({"username": "admin", "password": "a-secure-admin-password"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            cookie = response.headers["Set-Cookie"].split(";", 1)[0]
            session = json.loads(response.read())
        status, _ = _request(
            base + f"/api/projects/{project.project_id}",
            "DELETE",
            cookie=cookie,
        )
        assert status == 403
        status, result = _request(
            base + f"/api/projects/{project.project_id}",
            "DELETE",
            cookie=cookie,
            csrf=str(session["csrf"]),
        )
        assert status == 200
        assert result["status"] == "deleted"
        assert repository.get_project(project.project_id) is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        app.workspace.close()
