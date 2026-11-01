"""Isolated browser-worker entry point executed only inside the Playwright Docker image."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


def main() -> None:
    os.umask(0o002)
    parser = argparse.ArgumentParser(description="Run the isolated Playwright browser worker")
    parser.add_argument("--config", default=os.environ.get("PW_CONFIG"))
    arguments = parser.parse_args()
    if not arguments.config:
        raise RuntimeError("browser worker configuration is required")
    config = json.loads(Path(arguments.config).read_text(encoding="utf-8"))
    root = Path("/workspace")
    output = Path(config.get("container_output", config["output"]))
    output.mkdir(parents=True, exist_ok=True)
    screenshots = output / "screenshots"
    traces = output / "playwright" / "traces"
    reports = output / "playwright" / "reports"
    videos = output / "playwright" / "videos"
    for path in (screenshots, traces, reports, videos):
        path.mkdir(parents=True, exist_ok=True)
    events: dict[str, Any] = {
        "console_errors": [], "failed_requests": [], "browser_errors": [],
        "broken_images": [], "screenshots": [], "component_screenshots": [],
        "traces": [], "videos": [], "workflow_results": [],
    }
    parsed_url = urlparse(config["url"])
    if parsed_url.scheme != "http" or parsed_url.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("readiness URL must be loopback HTTP")
    process = subprocess.Popen(config["start_command"], cwd=str(root),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ready = False
        deadline = time.monotonic() + config["readiness_timeout"]
        while time.monotonic() < deadline:
            try:
                connection = http.client.HTTPConnection(parsed_url.hostname, parsed_url.port or 80, timeout=2)
                connection.request("GET", parsed_url.path or "/")
                ready_response = connection.getresponse()
                connection.close()
                if ready_response.status == 200:
                    ready = True
                    break
            except (OSError, TimeoutError):
                time.sleep(0.25)
        if not ready:
            raise RuntimeError("application readiness timeout")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            for viewport in config["viewports"]:
                name = viewport["name"]
                context = browser.new_context(
                    viewport={"width": viewport["width"], "height": viewport["height"]},
                    record_video_dir=str(videos / name),
                )
                context.tracing.start(screenshots=True, snapshots=True)
                page = context.new_page()
                auth_bootstrap_pending = [True]

                def record_console(
                    message: Any, bootstrap: list[bool] = auth_bootstrap_pending
                ) -> None:
                    # The unauthenticated session probe is intentionally a
                    # 401 before the login workflow. Keep real console errors
                    # visible while avoiding a false browser-health failure.
                    if (
                        message.type == "error"
                        and not (
                            bootstrap[0]
                            and "status of 401" in message.text
                        )
                    ):
                        events["console_errors"].append(message.text)

                page.on("console", record_console)
                page.on("pageerror", lambda error: events["browser_errors"].append(str(error)))
                page.on("requestfailed", lambda request: events["failed_requests"].append(
                    (request.url or "") + " " + str(request.failure)
                ))
                page_response = page.goto(
                    config["url"],
                    wait_until="networkidle",
                    timeout=config["test_timeout"] * 1000,
                )
                if page_response is None or page_response.status != 200:
                    status = page_response.status if page_response is not None else "no response"
                    raise PlaywrightError(f"application page returned HTTP {status}")
                auth_bootstrap_pending[0] = False
                folder = screenshots / name
                folder.mkdir(parents=True, exist_ok=True)
                screenshot = folder / "current.png"
                page.screenshot(path=str(screenshot), full_page=True)
                events["screenshots"].append(str(screenshot.relative_to(output)))
                for index, selector in enumerate(config["component_selectors"]):
                    locator = page.locator(selector).first
                    if locator.count():
                        component = folder / f"component-{index}.png"
                        locator.screenshot(path=str(component))
                        events["component_screenshots"].append(str(component.relative_to(output)))
                for image in page.locator("img").all():
                    healthy = image.evaluate(
                        "element => element.complete && element.naturalWidth > 0"
                    )
                    if not healthy:
                        events["broken_images"].append(str(image.get_attribute("src")))
                for workflow in config["workflows"]:
                    try:
                        if workflow["action"] == "click":
                            page.locator(workflow["selector"]).click(
                                timeout=config["test_timeout"] * 1000
                            )
                        elif workflow["action"] == "fill":
                            page.locator(workflow["selector"]).fill(workflow.get("value", ""))
                        elif workflow["action"] == "goto":
                            page.goto(workflow["value"], wait_until="networkidle",
                                      timeout=config["test_timeout"] * 1000)
                        elif workflow["action"] == "assert_text":
                            locator = page.locator(workflow["selector"]).first
                            expected = workflow.get("value", "")
                            deadline = time.monotonic() + config["test_timeout"]
                            actual = ""
                            while time.monotonic() < deadline:
                                locator.wait_for(state="visible", timeout=250)
                                actual = locator.inner_text()
                                if expected in actual:
                                    break
                                time.sleep(0.05)
                            else:
                                raise PlaywrightError(
                                    f"expected text {expected!r} in {actual!r}"
                                )
                        elif workflow["action"] == "assert_visible":
                            page.locator(workflow["selector"]).first.wait_for(
                                state="visible", timeout=config["test_timeout"] * 1000
                            )
                        events["workflow_results"].append({"workflow": workflow, "status": "PASS"})
                    except PlaywrightError as error:
                        events["workflow_results"].append(
                            {"workflow": workflow, "status": "FAIL", "error": str(error)}
                        )
                trace = traces / (name + ".zip")
                context.tracing.stop(path=str(trace))
                events["traces"].append(str(trace.relative_to(output)))
                video = page.video
                context.close()
                if video:
                    try:
                        events["videos"].append(str(Path(video.path()).relative_to(output)))
                    except (OSError, ValueError):
                        events["browser_errors"].append("video artifact unavailable")
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    (reports / "raw-result.json").write_text(json.dumps(events), encoding="utf-8")


if __name__ == "__main__":
    main()
