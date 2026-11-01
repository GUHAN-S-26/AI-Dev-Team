from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from app.config import Settings
from app.qa.playwright_runner import BrowserViewport, PlaywrightRunner
from app.tools.docker_manager import SandboxResult


class FakePlaywrightSandbox:
    def run(self, workspace: Path, command: list[str]) -> SandboxResult:
        config_path = workspace / command[1]
        config = json.loads(config_path.with_name("config.json").read_text())
        output = Path(config["output"])
        for viewport in config["viewports"]:
            folder = output / "screenshots" / viewport["name"]
            folder.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (viewport["width"], viewport["height"]), (20, 40, 60, 255)).save(folder / "current.png")
        report = output / "playwright" / "reports"
        report.mkdir(parents=True, exist_ok=True)
        (report / "raw-result.json").write_text(json.dumps({
            "screenshots": [], "component_screenshots": [], "traces": [], "reports": [],
            "videos": [], "console_errors": [], "failed_requests": [],
            "browser_errors": [], "broken_images": [], "workflow_results": [],
        }))
        return SandboxResult(0, "", "")


def test_playwright_artifacts_baseline_then_visual_pass(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects", workspaces_dir=tmp_path / "workspaces")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runner = PlaywrightRunner(settings)
    runner.sandbox = FakePlaywrightSandbox()  # type: ignore[assignment]
    viewports = [BrowserViewport(name="desktop", width=320, height=480)]
    first = runner.run("PROJECT-test", workspace, start_command=["python", "app.py"], viewports=viewports)
    assert first.status == "BASELINE_CREATED"
    assert (tmp_path / "data/artifacts/PROJECT-test/screenshots/desktop/baseline.png").is_file()
    second = runner.run("PROJECT-test", workspace, start_command=["python", "app.py"], viewports=viewports)
    assert second.status == "PASS"
    assert second.visual_diffs[0]["status"] == "PASS"
