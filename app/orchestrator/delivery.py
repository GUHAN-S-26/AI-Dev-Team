"""Final report and artifact generation."""

from __future__ import annotations

import json
from pathlib import Path

from app.database.repository import Repository
from app.schemas.models import FinalReport, new_id


class DeliveryManager:
    def __init__(self, repository: Repository, artifacts_dir: Path) -> None:
        self.repository = repository
        self.artifacts_dir = artifacts_dir

    def publish(self, report: FinalReport) -> Path:
        target_dir = (self.artifacts_dir / report.project_id).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / "final-report.json"
        path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")
        self.repository.save_artifact(new_id("ARTIFACT"), report.project_id, "final-report", str(path), {})
        return path
