from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.config import Settings
from app.database.repository import Repository
from app.security.audit_logger import AuditLogger
from app.security.auth import AuthService, Role
from app.web.dashboard import DashboardApplication


def request(
    url: str,
    method: str = "GET",
    body: dict[str, object] | None = None,
    cookie: str | None = None,
    csrf: str | None = None,
) -> tuple[int, dict[str, object], dict[str, str]]:
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-CSRF-Token"] = csrf
    data = json.dumps(body).encode() if body is not None else None
    request_object = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request_object) as response:
            return response.status, json.loads(response.read()), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read()), dict(error.headers)


def test_workspace_chat_and_project_isolation(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects", workspaces_dir=tmp_path / "workspaces")
    settings.ensure_directories()
    repository = Repository(settings.database_path)
    application = DashboardApplication(settings, repository)
    auth = AuthService(repository, AuditLogger(repository))
    auth.create_user("workspace-admin", "a-secure-workspace-password", Role.ADMIN)
    auth.create_user("workspace-viewer", "a-secure-viewer-password", Role.VIEWER)
    server = __import__("http.server", fromlist=["ThreadingHTTPServer"]).ThreadingHTTPServer(
        ("127.0.0.1", 0), application.handler()
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, login, headers = request(
            base + "/api/auth/login",
            "POST",
            {"username": "workspace-admin", "password": "a-secure-workspace-password"},
        )
        assert status == 200
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        csrf = str(login["csrf"])
        status, first, _ = request(
            base + "/api/projects", "POST", {"name": "First", "requirement": "Build first app"}, cookie, csrf
        )
        assert status == 201
        first_id = str(first["project"]["project_id"])
        status, second, _ = request(
            base + "/api/projects", "POST", {"name": "Second", "requirement": "Build second app"}, cookie, csrf
        )
        assert status == 201
        second_id = str(second["project"]["project_id"])
        status, workspace, _ = request(base + f"/api/projects/{first_id}/workspace", cookie=cookie)
        assert status == 200
        assert workspace["project"]["project_id"] == first_id
        status, workspace, _ = request(
            base + f"/api/projects/{first_id}/chat", "POST", {"content": "Add a responsive home page"}, cookie, csrf
        )
        assert status == 200
        assert any(item["content"] == "Add a responsive home page" for item in workspace["chat"])
        status, second_workspace, _ = request(base + f"/api/projects/{second_id}/workspace", cookie=cookie)
        assert status == 200
        assert second_workspace["chat"] == []
        status, viewer_login, viewer_headers = request(
            base + "/api/auth/login",
            "POST",
            {"username": "workspace-viewer", "password": "a-secure-viewer-password"},
        )
        assert status == 200
        viewer_cookie = viewer_headers["Set-Cookie"].split(";", 1)[0]
        status, _, _ = request(base + f"/api/projects/{first_id}/workspace", cookie=viewer_cookie)
        assert status == 404
        del viewer_login
        time.sleep(0.05)
    finally:
        application.workspace.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
