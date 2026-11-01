"""Deterministic validation and approval-controlled integration."""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.database.repository import Repository
from app.schemas.models import ApprovalDecision
from app.security.approval_manager import ApprovalManager
from app.security.audit_logger import AuditLogger
from app.tools.git_manager import GitError


class IntegrationManager:
    def __init__(
        self,
        repository: Repository,
        approvals: ApprovalManager,
        audit: AuditLogger,
        require_approval: bool = True,
    ) -> None:
        self.repository = repository
        self.approvals = approvals
        self.audit = audit
        self.require_approval = require_approval

    def validate_branch(self, worktree: Path) -> dict[str, str | bool]:
        checks: dict[str, str | bool] = {}
        for name, command in {
            "status": ["git", "status", "--short"],
            "diff_check": ["git", "diff", "--check"],
        }.items():
            result = subprocess.run(
                command, cwd=worktree, capture_output=True, text=True, check=False
            )
            checks[name] = result.returncode == 0
            if result.returncode:
                checks[f"{name}_output"] = result.stderr.strip() or result.stdout.strip()
        if not all(value is True for key, value in checks.items() if not key.endswith("_output")):
            raise GitError("branch validation failed")
        return checks

    def request_merge(self, project_id: str, branch: str, diff_ref: str) -> str:
        approval = self.approvals.request(
            project_id, "merge_to_main", {"branch": branch}, artifact_ref=diff_ref
        )
        return approval.approval_id

    def merge_after_approval(self, project_id: str, repository_root: Path, branch: str) -> str:
        if self.require_approval:
            approval = self.approvals.require_approved(project_id, "merge_to_main")
            if approval.decision is not ApprovalDecision.APPROVED:
                raise PermissionError("merge approval was not granted")
        result = subprocess.run(
            [
                "git",
                "-c",
                "user.name=AI Dev Team",
                "-c",
                "user.email=ai-dev-team@localhost",
                "merge",
                "--no-ff",
                "--no-edit",
                branch,
            ],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise GitError(result.stderr.strip() or result.stdout.strip())
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        self.audit.record(
            "BRANCH_MERGED",
            project_id=project_id,
            actor_id="integration-manager",
            payload={"branch": branch, "commit": commit},
        )
        return commit
