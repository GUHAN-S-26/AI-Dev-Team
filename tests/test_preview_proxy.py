from __future__ import annotations

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.config import Settings
from app.database.repository import Repository
from app.orchestrator.engine import Orchestrator
from app.schemas.models import PreviewSession, ProjectRequest
from app.security.audit_logger import AuditLogger
from app.security.auth import AuthService, Role
from app.web.dashboard import DashboardApplication


class _PreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/":
            body = b'<html><link rel="stylesheet" href="/styles.css"><h1>Preview app</h1></html>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/styles.css":
            body = b"body { color: green; }"
            self.send_response(200)
            self.send_header("Content-Type", "text/css")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def test_dashboard_preview_is_project_scoped_and_same_origin(tmp_path: Path) -> None:
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
    project = Orchestrator(settings, repository).create_project(
        ProjectRequest(name="Proxy test", requirement="Build a proxy test page")
    )
    preview_server = ThreadingHTTPServer(("127.0.0.1", 0), _PreviewHandler)
    preview_thread = threading.Thread(target=preview_server.serve_forever, daemon=True)
    preview_thread.start()
    repository.save_preview_session(
        PreviewSession(
            project_id=project.project_id,
            status="RUNNING",
            port=preview_server.server_port,
            url=f"http://127.0.0.1:{preview_server.server_port}/",
        )
    )
    dashboard_server = ThreadingHTTPServer(("127.0.0.1", 0), app.handler())
    dashboard_thread = threading.Thread(target=dashboard_server.serve_forever, daemon=True)
    dashboard_thread.start()
    base = f"http://127.0.0.1:{dashboard_server.server_port}"
    try:
        login_request = urllib.request.Request(
            base + "/api/auth/login",
            data=json.dumps({"username": "admin", "password": "a-secure-admin-password"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(login_request) as response:
            cookie = response.headers["Set-Cookie"].split(";", 1)[0]
            csrf = json.loads(response.read())["csrf"]
        headers = {"Cookie": cookie, "X-CSRF-Token": csrf}
        workspace_request = urllib.request.Request(base + f"/api/projects/{project.project_id}/workspace", headers=headers)
        with urllib.request.urlopen(workspace_request) as response:
            workspace = json.loads(response.read())
        assert workspace["preview"]["url"] == (
            f"http://127.0.0.1:{dashboard_server.server_port}/api/projects/"
            f"{project.project_id}/preview/"
        )
        assert workspace["preview"]["port"] is None
        proxy_request = urllib.request.Request(
            base + f"/api/projects/{project.project_id}/preview/", headers=headers
        )
        with urllib.request.urlopen(proxy_request) as response:
            body = response.read().decode()
            assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
            assert "frame-ancestors 'self'" in response.headers["Content-Security-Policy"]
        assert f"/api/projects/{project.project_id}/preview/styles.css" in body
        assert "<h1>Preview app</h1>" in body
    finally:
        dashboard_server.shutdown()
        dashboard_server.server_close()
        dashboard_thread.join(timeout=2)
        preview_server.shutdown()
        preview_server.server_close()
        preview_thread.join(timeout=2)
        app.workspace.close()
