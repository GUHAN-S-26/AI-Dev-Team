from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from app.config import Settings
from app.database.repository import Repository
from app.security.audit_logger import AuditLogger
from app.security.auth import AuthService, Role
from app.web.dashboard import DashboardApplication, dashboard_html


def _request(url: str, method: str = "GET", body: dict[str, object] | None = None,
             cookie: str | None = None, csrf: str | None = None) -> tuple[int, dict[str, object], dict[str, str]]:
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-CSRF-Token"] = csrf
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read()), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read()), dict(error.headers)


def test_dashboard_authentication_rbac_csrf_and_project_creation(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects",
                        workspaces_dir=tmp_path / "workspaces", session_ttl_seconds=3600)
    settings.ensure_directories()
    repository = Repository(settings.database_path)
    app = DashboardApplication(settings, repository)
    auth = AuthService(repository, AuditLogger(repository))
    auth.create_user("admin", "a-secure-test-password", Role.ADMIN)
    auth.create_user("viewer", "a-secure-viewer-password", Role.VIEWER)
    server = __import__("http.server", fromlist=["ThreadingHTTPServer"]).ThreadingHTTPServer(
        ("127.0.0.1", 0), app.handler()
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, _, _ = _request(base + "/api/projects")
        assert status == 401
        status, login, headers = _request(base + "/api/auth/login", "POST", {"username": "admin", "password": "a-secure-test-password"})
        assert status == 200
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        csrf = str(login["csrf"])
        status, projects, _ = _request(base + "/api/projects", cookie=cookie)
        assert status == 200
        assert projects["projects"] == []
        status, _, _ = _request(base + "/api/projects", "POST", {"name": "Denied", "requirement": "Build a secure dashboard"}, cookie=cookie)
        assert status == 403
        status, created, _ = _request(base + "/api/projects", "POST", {"name": "Dashboard", "requirement": "Build a secure dashboard"}, cookie, csrf)
        assert status == 201
        assert str(created["project"]["name"]) == "Dashboard"
        status, _viewer_login, viewer_headers = _request(base + "/api/auth/login", "POST", {"username": "viewer", "password": "a-secure-viewer-password"})
        assert status == 200
        viewer_cookie = viewer_headers["Set-Cookie"].split(";", 1)[0]
        status, viewer_session, _ = _request(base + "/api/auth/session", cookie=viewer_cookie)
        assert status == 200
        status, _, _ = _request(base + "/api/projects", "POST", {"name": "Denied", "requirement": "Build a secure dashboard"}, viewer_cookie, str(viewer_session["csrf"]))
        assert status == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_dashboard_html_contains_no_provider_secret_configuration() -> None:
    page = dashboard_html()
    assert "AZURE_OPENAI_API_KEY" not in page
    assert "AZURE_OPENAI_ENDPOINT" not in page
