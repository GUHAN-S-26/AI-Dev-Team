from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.docker_manager import DockerSandbox, SandboxError


def test_docker_network_requires_explicit_approval(tmp_path: Path) -> None:
    sandbox = DockerSandbox()
    with pytest.raises(SandboxError, match="explicit approval"):
        sandbox.run(tmp_path, ["python", "-c", "print('no')"], network=True)


def test_docker_command_rejects_nul(tmp_path: Path) -> None:
    with pytest.raises(SandboxError, match="invalid"):
        DockerSandbox().run(tmp_path, ["python\x00", "-c", "pass"])
