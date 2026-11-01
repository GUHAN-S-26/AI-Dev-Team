"""Test execution through the Docker sandbox."""

from __future__ import annotations

import re
from pathlib import Path

from app.schemas.models import TestReport
from app.tools.docker_manager import DockerSandbox


class TestRunner:
    def __init__(self, sandbox: DockerSandbox) -> None:
        self.sandbox = sandbox

    def run_pytest(self, workspace: Path, args: list[str] | None = None) -> TestReport:
        result = self.sandbox.run(workspace, ["python", "-m", "pytest", *(args or [])])
        passed = failed = skipped = 0
        match = re.search(r"(\d+) passed", result.stdout)
        if match:
            passed = int(match.group(1))
        match = re.search(r"(\d+) failed", result.stdout)
        if match:
            failed = int(match.group(1))
        match = re.search(r"(\d+) skipped", result.stdout)
        if match:
            skipped = int(match.group(1))
        return TestReport(
            suite_name="pytest",
            status="PASS" if result.exit_code == 0 else "FAIL",
            passed=passed,
            failed=failed,
            skipped=skipped,
            output=(result.stdout + result.stderr),
        )
