"""Project-scoped Docker preview lifecycle and loopback health checks."""

from __future__ import annotations

import http.client
import ipaddress
import re
import shutil
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.database.repository import Repository
from app.schemas.models import PreviewSession


class PreviewError(RuntimeError):
    pass


_PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_COMMAND_BINARIES = frozenset({"node", "npm", "pnpm", "python", "python3", "uv", "uvicorn"})
# The bind is container-only; Docker publishes the host port on loopback.
_CONTAINER_BIND_HOST = str(ipaddress.IPv4Address(0))
_DEFAULT_PREVIEW_COMMAND = ["python", "backend/server.py", "--host", _CONTAINER_BIND_HOST]


def _now() -> datetime:
    return datetime.now(UTC)


class PreviewManager:
    """Run one loopback-only preview container per project.

    Preview containers are deliberately separate from the test sandbox. They
    need a published local port for the browser, but never publish on a host
    interface other than 127.0.0.1 and never mount the Docker socket.
    """

    def __init__(self, settings: Settings, repository: Repository) -> None:
        self.settings = settings
        self.repository = repository

    @staticmethod
    def validate_command(command: list[str]) -> list[str]:
        if not command or len(command) > 32:
            raise PreviewError("preview command must contain 1-32 argv entries")
        if any(not part or len(part) > 240 or "\x00" in part for part in command):
            raise PreviewError("preview command contains an invalid argument")
        binary = Path(command[0]).name
        if binary not in _COMMAND_BINARIES:
            raise PreviewError("preview command executable is not allowlisted")
        return list(command)

    def _workspace(self, project_id: str) -> Path:
        if not _PROJECT_ID.fullmatch(project_id):
            raise PreviewError("invalid project ID")
        project = self.repository.get_project(project_id)
        if project is None:
            raise PreviewError("project not found")
        workspace = Path(project.root_path).resolve()
        projects_root = self.settings.projects_dir.resolve()
        if workspace != projects_root and projects_root not in workspace.parents:
            raise PreviewError("project workspace is outside the projects root")
        if not workspace.is_dir():
            raise PreviewError("project workspace is unavailable")
        return workspace

    @staticmethod
    def _port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])

    @staticmethod
    def _container_name(project_id: str) -> str:
        return "ai-dev-preview-" + project_id.lower().replace("_", "-")

    def _docker(self, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        if shutil.which("docker") is None:
            raise PreviewError("Docker is required for project previews")
        try:
            return subprocess.run(
                ["docker", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise PreviewError("preview Docker operation timed out") from error

    def _stop_container(self, name: str) -> None:
        result = self._docker(["rm", "--force", name])
        if result.returncode not in {0, 1}:
            raise PreviewError("preview container cleanup failed")

    def _ready(self, port: int) -> bool:
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1.5)
            connection.request("GET", "/")
            response = connection.getresponse()
            status = response.status
            response.close()
            connection.close()
            return status == 200
        except (OSError, TimeoutError):
            return False

    def start(self, project_id: str, command: list[str] | None = None) -> PreviewSession:
        workspace = self._workspace(project_id)
        # The generated server binds loopback by default. Inside the isolated
        # container Docker forwards the host-loopback port to the container
        # interface, so the controlled default binds all container interfaces.
        # The published host port below remains 127.0.0.1 only.
        selected = self.validate_command(command or _DEFAULT_PREVIEW_COMMAND)
        existing = self.repository.get_preview_session(project_id)
        if existing and existing.container_name:
            self._stop_container(existing.container_name)
        port = self._port()
        name = self._container_name(project_id)
        session = PreviewSession(
            project_id=project_id,
            status="STARTING",
            port=port,
            url=f"http://127.0.0.1:{port}/",
            container_name=name,
            command=selected,
            updated_at=_now(),
        )
        self.repository.save_preview_session(session)
        workspace_group = workspace.stat().st_gid
        docker_args = [
            "run",
            "--detach",
            "--rm",
            "--name",
            name,
            "--user",
            f"65532:{workspace_group}",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit",
            "128",
            "--cpus",
            "1",
            "--memory",
            "512m",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=128m",
            "--network=bridge",
            "--publish",
            f"127.0.0.1:{port}:8000",
            "--volume",
            f"{workspace}:/workspace:ro",
            "--workdir",
            "/workspace",
            self.settings.docker_image,
            *selected,
        ]
        result = self._docker(docker_args)
        if result.returncode != 0:
            failed = session.model_copy(update={"status": "ERROR", "error": "preview container failed to start", "updated_at": _now()})
            self.repository.save_preview_session(failed)
            return failed
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self._ready(port):
                running = session.model_copy(update={"status": "RUNNING", "updated_at": _now()})
                self.repository.save_preview_session(running)
                return running
            time.sleep(0.25)
        self._stop_container(name)
        failed = session.model_copy(update={"status": "ERROR", "error": "preview did not become ready", "updated_at": _now()})
        self.repository.save_preview_session(failed)
        return failed

    def stop(self, project_id: str) -> PreviewSession:
        session = self.repository.get_preview_session(project_id)
        if session and session.container_name:
            self._stop_container(session.container_name)
        stopped = (session or PreviewSession(project_id=project_id)).model_copy(
            update={"status": "STOPPED", "url": None, "port": None, "container_name": None, "updated_at": _now()}
        )
        self.repository.save_preview_session(stopped)
        return stopped

    def status(self, project_id: str) -> PreviewSession:
        session = self.repository.get_preview_session(project_id)
        if session is None:
            return PreviewSession(project_id=project_id)
        if session.status == "RUNNING" and session.port and not self._ready(session.port):
            stopped = session.model_copy(update={"status": "STOPPED", "url": None, "port": None, "container_name": None, "updated_at": _now()})
            self.repository.save_preview_session(stopped)
            return stopped
        return session
