"""Authoritative typed domain contracts.

These schemas are also the boundary between untrusted model output and the
deterministic control plane.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProjectStatus(StrEnum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    DEVELOPMENT = "DEVELOPMENT"
    INTEGRATION = "INTEGRATION"
    QA = "QA"
    DELIVERY = "DELIVERY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentRole(StrEnum):
    PLANNING = "planning"
    FRONTEND = "frontend"
    BACKEND = "backend"
    TESTING = "testing"


class AgentStatus(StrEnum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    OUTPUT_VALIDATION = "OUTPUT_VALIDATION"
    REPORTED = "REPORTED"
    MEMORY_COMMITTED = "MEMORY_COMMITTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MessageType(StrEnum):
    TASK_ASSIGNMENT = "TASK_ASSIGNMENT"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    BUG_FOUND = "BUG_FOUND"
    CONTRACT_UPDATED = "CONTRACT_UPDATED"
    DEPENDENCY_BLOCKED = "DEPENDENCY_BLOCKED"
    SUB_AGENT_REQUEST = "SUB_AGENT_REQUEST"
    REVIEW_REQUEST = "REVIEW_REQUEST"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"
    TOOL_REQUEST = "TOOL_REQUEST"
    TOOL_RESULT = "TOOL_RESULT"
    CONTEXT_REQUEST = "CONTEXT_REQUEST"


class ApprovalDecision(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ProjectRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    requirement: str = Field(min_length=10, max_length=100_000)


class Project(StrictModel):
    project_id: str = Field(default_factory=lambda: new_id("PROJECT"))
    name: str
    requirement: str
    status: ProjectStatus = ProjectStatus.CREATED
    root_path: str
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class Agent(StrictModel):
    agent_id: str
    role: str
    project_id: str
    parent_agent_id: str | None = None
    task_id: str | None = None
    instruction_version: str = "1.0"
    private_memory_namespace: str
    authorized_paths: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.CREATED
    max_active_tasks: int = Field(default=1, ge=1)
    max_tokens: int = Field(default=30_000, ge=100)
    created_at: datetime = Field(default_factory=now_utc)


class Task(StrictModel):
    task_id: str = Field(default_factory=lambda: new_id("TASK"))
    project_id: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    assigned_agent: str
    parent_task_id: str | None = None
    priority: Priority = Priority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1)
    authorized_paths: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class TaskExecution(StrictModel):
    execution_id: str = Field(default_factory=lambda: new_id("EXEC"))
    task_id: str
    project_id: str
    attempt_number: int = Field(ge=1)
    agent_id: str
    status: str = "RUNNING"
    started_at: datetime = Field(default_factory=now_utc)
    ended_at: datetime | None = None
    input_ref: str | None = None
    output_ref: str | None = None
    error_classification: str | None = None
    workspace_ref: str | None = None
    commit_ref: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost: float = 0.0


class Message(StrictModel):
    message_id: str = Field(default_factory=lambda: new_id("MSG"))
    from_agent: str
    to_agent: str
    project_id: str
    task_id: str | None = None
    message_type: MessageType
    content: dict[str, Any]
    status: Literal["PENDING", "DELIVERED", "FAILED"] = "PENDING"
    idempotency_key: str
    created_at: datetime = Field(default_factory=now_utc)
    delivered_at: datetime | None = None


class ChatMessage(StrictModel):
    """Project-scoped user/orchestrator conversation record."""

    message_id: str = Field(default_factory=lambda: new_id("CHAT"))
    project_id: str
    user_id: str
    role: Literal["user", "assistant", "system", "event"]
    content: str = Field(min_length=1, max_length=200_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)


class PreviewSession(StrictModel):
    """Persisted state for one project-local Docker preview runtime."""

    project_id: str
    status: Literal["STOPPED", "STARTING", "RUNNING", "ERROR"] = "STOPPED"
    port: int | None = Field(default=None, ge=1, le=65535)
    url: str | None = None
    container_name: str | None = None
    command: list[str] = Field(default_factory=list)
    error: str | None = None
    updated_at: datetime = Field(default_factory=now_utc)


class MemoryEntry(StrictModel):
    memory_id: str = Field(default_factory=lambda: new_id("MEM"))
    project_id: str
    namespace: str
    owner_agent_id: str
    content: dict[str, Any]
    source_task_id: str | None = None
    schema_version: str = "1.0"
    approved: bool = False
    created_at: datetime = Field(default_factory=now_utc)


class Approval(StrictModel):
    approval_id: str = Field(default_factory=lambda: new_id("APPROVAL"))
    project_id: str
    action: str
    scope: dict[str, Any]
    decision: ApprovalDecision = ApprovalDecision.PENDING
    approver_id: str | None = None
    artifact_ref: str | None = None
    reason: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    decided_at: datetime | None = None


class PlanTask(StrictModel):
    task_id: str = Field(default_factory=lambda: new_id("TASK"))
    title: str
    description: str
    assigned_agent: str
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1)
    authorized_paths: list[str] = Field(default_factory=list)
    priority: Priority = Priority.MEDIUM

    @field_validator("assigned_agent")
    @classmethod
    def valid_agent(cls, value: str) -> str:
        if value not in {role.value for role in AgentRole}:
            raise ValueError("task must be assigned to a primary agent role")
        return value


class Architecture(StrictModel):
    summary: str
    components: list[str] = Field(min_length=1)
    technology_choices: dict[str, str] = Field(default_factory=dict)
    folder_structure: list[str] = Field(default_factory=list)
    database_schema: list[str] = Field(default_factory=list)


class ApiContract(StrictModel):
    contract_id: str
    version: str
    endpoint: str
    method: str
    authentication: str
    request_schema: dict[str, Any] = Field(default_factory=dict)
    response_schema: dict[str, Any] = Field(default_factory=dict)
    error_responses: list[dict[str, Any]] = Field(default_factory=list)
    compatibility_policy: str
    owner: str
    approved: bool = False


class Plan(StrictModel):
    project_id: str
    project_brief: str
    functional_requirements: list[str] = Field(min_length=1)
    non_functional_requirements: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    architecture: Architecture
    api_contracts: list[ApiContract] = Field(default_factory=list)
    tasks: list[PlanTask] = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=now_utc)


class SubAgentRequest(StrictModel):
    parent_agent_id: str
    project_id: str
    task_id: str
    role: str = Field(min_length=1, max_length=80)
    instructions: str = Field(min_length=1, max_length=10_000)
    authorized_paths: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    max_tokens: int = Field(default=10_000, ge=100, le=100_000)


class BugReport(StrictModel):
    bug_id: str = Field(default_factory=lambda: new_id("BUG"))
    project_id: str
    related_task_ids: list[str] = Field(min_length=1)
    severity: Literal["low", "medium", "high", "critical"]
    priority: Priority
    environment: str
    commit_ref: str | None = None
    reproduction_steps: list[str] = Field(min_length=1)
    expected_behavior: str
    actual_behavior: str
    evidence: list[str] = Field(default_factory=list)
    suspected_component: str
    assigned_owner: str
    verification_status: Literal["OPEN", "FIXED", "VERIFIED", "WONT_FIX"] = "OPEN"


class TestReport(StrictModel):
    suite_name: str
    status: Literal["PASS", "FAIL", "ERROR", "SKIPPED"]
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0)
    output: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class AgentWorkResult(StrictModel):
    """Validated proposal returned by implementation/QA agents."""

    summary: str
    completed: bool = False
    requested_tools: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class ContractChangeProposal(StrictModel):
    contract_id: str
    current_version: str
    proposed_version: str
    breaking: bool = False
    reason: str
    affected_tasks: list[str] = Field(default_factory=list)


class FinalReport(StrictModel):
    project_id: str
    summary: str
    delivered_features: list[str]
    architecture_summary: str
    source_refs: list[str]
    build_instructions: list[str]
    test_reports: list[TestReport]
    known_issues: list[str]
    security_checks: list[str]
    outstanding_approvals: list[str]
    model_usage: dict[str, Any]
    generated_at: datetime = Field(default_factory=now_utc)
