"""Restricted Docker execution; no host shell fallback is provided."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class SandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str


class DockerSandbox:
    def __init__(
        self,
        image: str = "python:3.12-slim",
        timeout_seconds: int = 300,
        max_output_chars: int = 20_000,
    ) -> None:
        self.image = image
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    def run(self, workspace: Path, command: list[str], *, network: bool = False,
            network_approved: bool = False) -> SandboxResult:
        if not command or any("\x00" in part for part in command):
            raise SandboxError("empty or invalid sandbox command")
        if network and not network_approved:
            raise SandboxError("network access requires explicit approval")
        if shutil.which("docker") is None:
            raise SandboxError("Docker is required for code execution and is not available")
        workspace_group = workspace.resolve().stat().st_gid
        if workspace_group == 0:
            raise SandboxError("workspace must not use the root group")
        docker_command = [
            "docker",
            "run",
            "--rm",
            "--user",
            f"65532:{workspace_group}",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit",
            "256",
            "--cpus",
            "2",
            "--memory",
            "1g",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m",
        ]
        docker_command.append("--network=bridge" if network else "--network=none")
        docker_command.extend(
            ["-v", f"{workspace.resolve()}:/workspace:rw", "-w", "/workspace", self.image]
        )
        docker_command.extend(command)
        try:
            completed = subprocess.run(
                docker_command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise SandboxError("sandbox execution timed out") from error
        return SandboxResult(
            completed.returncode,
            completed.stdout[-self.max_output_chars :],
            completed.stderr[-self.max_output_chars :],
        )
