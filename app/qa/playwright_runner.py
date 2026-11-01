"""Orchestrator-controlled Playwright browser QA and visual evidence collection."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.qa.visual_diff import compare_images
from app.tools.docker_manager import DockerSandbox


class BrowserViewport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["desktop", "tablet", "mobile"]
    width: int = Field(ge=320, le=3840)
    height: int = Field(ge=480, le=2160)


class PlaywrightReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    status: Literal["PASS", "FAIL", "ERROR", "BASELINE_CREATED"]
    screenshots: list[str] = Field(default_factory=list)
    component_screenshots: list[str] = Field(default_factory=list)
    traces: list[str] = Field(default_factory=list)
    reports: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)
    console_errors: list[str] = Field(default_factory=list)
    failed_requests: list[str] = Field(default_factory=list)
    browser_errors: list[str] = Field(default_factory=list)
    broken_images: list[str] = Field(default_factory=list)
    visual_diffs: list[dict[str, Any]] = Field(default_factory=list)
    workflow_results: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


_PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _remove_worker_tree(path: Path) -> None:
    """Remove a task-created tree without chmodding container-owned files."""
    if path.is_symlink():
        path.unlink(missing_ok=True)
        return
    if path.is_dir():
        for entry in os.scandir(path):
            _remove_worker_tree(Path(entry.path))
        try:
            path.rmdir()
        except OSError:
            pass
        return
    path.unlink(missing_ok=True)


@contextmanager
def _worker_directory(workspace: Path) -> Iterator[Path]:
    temporary = Path(tempfile.mkdtemp(prefix="playwright-", dir=str(workspace)))
    try:
        yield temporary
    finally:
        _remove_worker_tree(temporary)


class PlaywrightRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sandbox = DockerSandbox(
            settings.playwright_image,
            settings.playwright_timeout_seconds,
            settings.max_output_chars,
        )

    def run(
        self,
        project_id: str,
        workspace: Path,
        *,
        start_command: list[str],
        readiness_url: str = "http://127.0.0.1:8000/",
        viewports: list[BrowserViewport] | None = None,
        component_selectors: list[str] | None = None,
        workflows: list[dict[str, str]] | None = None,
        test_timeout_seconds: int = 20,
        visual_threshold: float = 0.01,
    ) -> PlaywrightReport:
        if not _PROJECT_ID.fullmatch(project_id):
            raise ValueError("invalid project ID")
        if not workspace.is_dir() or not start_command:
            raise ValueError("workspace and non-empty start command are required")
        workspace = workspace.resolve()
        if any("\x00" in part for part in start_command):
            raise ValueError("start command contains a NUL byte")
        selected = viewports or [
            BrowserViewport(name="desktop", width=1440, height=900),
            BrowserViewport(name="tablet", width=768, height=1024),
            BrowserViewport(name="mobile", width=390, height=844),
        ]
        artifact_root = self.settings.data_dir / "artifacts" / project_id
        artifact_root.mkdir(parents=True, exist_ok=True)
        with _worker_directory(workspace) as temp_root:
            # TemporaryDirectory defaults to 0700.  The browser container is
            # intentionally non-root, so expose only this ephemeral worker
            # directory and its output to UID 65532; the project mount remains
            # governed by the normal workspace permissions.
            temp_root.chmod(0o775)
            worker = temp_root / "browser_worker.py"
            config = temp_root / "config.json"
            output = temp_root / "output"
            shutil.copy2(Path(__file__).with_name("browser_worker.py"), worker)
            worker.chmod(0o644)
            config.write_text(
                json.dumps(
                    {
                        "output": str(output),
                        "container_output": str(
                            Path("/workspace") / output.relative_to(workspace)
                        ),
                        "start_command": start_command,
                        "url": readiness_url,
                        "readiness_timeout": self.settings.playwright_timeout_seconds,
                        "test_timeout": test_timeout_seconds,
                        "viewports": [item.model_dump() for item in selected],
                        "component_selectors": component_selectors or [],
                        "workflows": workflows or [],
                    }
                ),
                encoding="utf-8",
            )
            config.chmod(0o644)
            output.mkdir()
            output.chmod(0o775)
            result = self.sandbox.run(
                workspace,
                ["python", str(worker.relative_to(workspace)), "--config", str(config.relative_to(workspace))],
            )
            if result.exit_code != 0:
                message = (result.stderr or result.stdout)[-2000:]
                return PlaywrightReport(project_id=project_id, status="ERROR", error=message)
            raw = output / "playwright" / "reports" / "raw-result.json"
            events = json.loads(raw.read_text(encoding="utf-8"))
            for directory in ("screenshots", "playwright"):
                source = output / directory
                if source.exists():
                    shutil.copytree(source, artifact_root / directory, dirs_exist_ok=True)
            report = PlaywrightReport(project_id=project_id, status="PASS", **events)
        functional_failure = (
            report.console_errors
            or report.failed_requests
            or report.browser_errors
            or report.broken_images
            or any(item.get("status") == "FAIL" for item in report.workflow_results)
        )
        visual_results: list[dict[str, Any]] = []
        baseline_created = False
        for viewport in selected:
            current = artifact_root / "screenshots" / viewport.name / "current.png"
            baseline = artifact_root / "screenshots" / viewport.name / "baseline.png"
            diff = artifact_root / "visual-diffs" / (viewport.name + ".png")
            if not baseline.exists():
                shutil.copy2(current, baseline)
                visual_results.append({"viewport": viewport.name, "status": "BASELINE_CREATED"})
                baseline_created = True
            else:
                visual_results.append(
                    {
                        "viewport": viewport.name,
                        **compare_images(baseline, current, diff, visual_threshold),
                    }
                )
        report.visual_diffs = visual_results
        if functional_failure or any(item["status"] == "FAIL" for item in visual_results):
            report.status = "FAIL"
        elif baseline_created and all(item["status"] == "BASELINE_CREATED" for item in visual_results):
            report.status = "BASELINE_CREATED"
        else:
            report.status = "PASS"
        report_path = artifact_root / "playwright" / "reports" / "report.html"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report.reports = [str(report_path)]
        report_path.write_text(
            "<html><body><h1>Playwright QA</h1><pre>"
            + json.dumps(report.model_dump(mode="json"), indent=2)
            + "</pre></body></html>",
            encoding="utf-8",
        )
        (artifact_root / "qa-report.json").write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        return report
