"""Explicit human approval gates."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.database.repository import Repository
from app.schemas.models import Approval, ApprovalDecision
from app.security.audit_logger import AuditLogger


class ApprovalManager:
    def __init__(self, repository: Repository, audit: AuditLogger) -> None:
        self.repository = repository
        self.audit = audit

    def request(
        self, project_id: str, action: str, scope: dict[str, Any], artifact_ref: str | None = None
    ) -> Approval:
        approval = Approval(
            project_id=project_id, action=action, scope=scope, artifact_ref=artifact_ref
        )
        self.repository.save_approval(approval)
        self.audit.record(
            "APPROVAL_REQUESTED",
            project_id=project_id,
            actor_id="orchestrator",
            payload={"approval_id": approval.approval_id, "action": action},
        )
        return approval

    def decide(
        self, approval_id: str, approver_id: str, approved: bool, reason: str | None = None
    ) -> Approval:
        approval = self.repository.get_approval(approval_id)
        if approval is None:
            raise KeyError(approval_id)
        if approval.decision is not ApprovalDecision.PENDING:
            raise ValueError("approval has already been decided")
        approval.decision = ApprovalDecision.APPROVED if approved else ApprovalDecision.REJECTED
        approval.approver_id = approver_id
        approval.reason = reason
        approval.decided_at = datetime.now(UTC)
        self.repository.save_approval(approval)
        self.audit.record(
            "APPROVAL_DECIDED",
            project_id=approval.project_id,
            actor_id=approver_id,
            payload={"approval_id": approval_id, "decision": approval.decision.value},
        )
        return approval

    def require_approved(self, project_id: str, action: str) -> Approval:
        approvals = self.repository.list_approvals(project_id, action)
        for approval in reversed(approvals):
            if approval.decision is ApprovalDecision.APPROVED:
                return approval
        raise PermissionError(f"human approval required for {action}")
