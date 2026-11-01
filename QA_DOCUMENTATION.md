# QA Documentation

## Test layers

- Unit and control-plane tests run with pytest.
- Ruff, strict mypy, and Bandit protect the platform code.
- Docker QA runs generated project tests as non-root with network disabled.
- Playwright QA runs through PlaywrightRunner in the approved browser image.
- Visual QA stores deterministic viewport screenshots, baselines, diffs, traces, videos, and HTML/JSON reports.

## Artifact layout

    data/artifacts/PROJECT-ID/
      screenshots/{desktop,tablet,mobile,failures}/
      playwright/{traces,reports,videos}/
      visual-diffs/
      qa-report.json
      final-report.json

A first screenshot creates an explicit BASELINE_CREATED result. Later differences produce a FAIL result and a diff image. The system does not auto-approve visual changes; a human must review expected changes.

## Skips

Skipped tests are not counted as passes. The original live project contained seven conditional browser/frontend skips because no application URL/browser image was supplied to that project test invocation. The Phase 2 runner now provides the required isolated browser contract; a full browser execution remains blocked in this environment until sufficient disk capacity is available for the pinned image.

