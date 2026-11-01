"""Only route for agent-requested side effects."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.database.repository import Repository
from app.schemas.models import Agent, Task, new_id
from app.schemas.tool_models import PathRequest, WriteFileRequest
from app.security.audit_logger import AuditLogger
from app.security.permission_manager import AuthorizationError, PermissionManager
from app.tools.docker_manager import DockerSandbox
from app.tools.filesystem import FileSystemTools
from app.tools.git_manager import GitError, GitWorktreeManager


class ToolRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=200)


class ToolResult(BaseModel):
    tool_call_id: str
    tool_name: str
    status: Literal["SUCCEEDED", "REJECTED", "FAILED"]
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ToolGateway:
    def __init__(
        self, repository: Repository, permissions: PermissionManager, audit: AuditLogger,
        sandbox: DockerSandbox | None = None,
    ) -> None:
        self.repository = repository
        self.permissions = permissions
        self.audit = audit
        self.files = FileSystemTools(permissions)
        self.sandbox = sandbox

    def execute(
        self, request: ToolRequest, *, agent: Agent, task: Task, workspace: Path
    ) -> ToolResult:
        call_id = new_id("TOOL")
        if request.tool_name not in agent.allowed_tools:
            return self._reject(call_id, request, agent, task, "tool is not in agent allowlist")
        try:
            self._validate_arguments(request)
            result: dict[str, Any]
            if request.tool_name == "read_file":
                result = {
                    "content": self.files.read_file(
                        workspace, request.arguments["path"], agent, task
                    )
                }
            elif request.tool_name == "list_directory":
                result = {
                    "entries": self.files.list_directory(
                        workspace, request.arguments.get("path", "."), agent, task
                    )
                }
            elif request.tool_name in {"create_file", "modify_file"}:
                self.files.write_file(
                    workspace,
                    request.arguments["path"],
                    request.arguments["content"],
                    agent,
                    task,
                    operation=request.tool_name,
                )
                result = {"written": request.arguments["path"]}
            elif request.tool_name == "delete_file":
                self.files.delete_file(workspace, request.arguments["path"], agent, task)
                result = {"deleted": request.arguments["path"]}
            elif request.tool_name == "commit_changes":
                for path in request.arguments["paths"]:
                    self.permissions.resolve_authorized_path(
                        workspace=workspace,
                        requested=path,
                        agent=agent,
                        task=task,
                        operation="commit",
                    )
                commit = GitWorktreeManager(workspace).commit_paths(
                    request.arguments["paths"], request.arguments["message"]
                )
                result = {"commit": commit}
            elif request.tool_name == "search_workspace":
                result = {"matches": self.files.search_workspace(
                    workspace, request.arguments.get("path", "."), request.arguments["query"], agent, task
                )}
            elif request.tool_name == "git_diff":
                result = {"diff": GitWorktreeManager(workspace).diff(workspace)}
            elif request.tool_name in {"run_formatter", "run_tests"}:
                if self.sandbox is None:
                    raise RuntimeError("sandbox is not configured")
                command = ["python", "-m", "compileall", "-q", "."] if request.tool_name == "run_formatter" \
                    else ["python", "-m", "pytest"]
                sandbox_result = self.sandbox.run(workspace, command)
                result = {"exit_code": sandbox_result.exit_code, "stdout": sandbox_result.stdout,
                          "stderr": sandbox_result.stderr}
                if sandbox_result.exit_code != 0:
                    raise RuntimeError("sandbox command failed")
            else:
                return self._reject(
                    call_id, request, agent, task, "tool is not implemented in this gateway"
                )
            self.repository.save_tool_call(
                call_id,
                agent.project_id,
                agent.agent_id,
                task.task_id,
                request.tool_name,
                "SUCCEEDED",
                {"idempotency_key": request.idempotency_key},
            )
            return ToolResult(
                tool_call_id=call_id, tool_name=request.tool_name, status="SUCCEEDED", result=result
            )
        except (KeyError, ValueError, TypeError, OSError, AuthorizationError, GitError) as error:
            self.repository.save_tool_call(
                call_id,
                agent.project_id,
                agent.agent_id,
                task.task_id,
                request.tool_name,
                "FAILED",
                {"error": str(error)},
            )
            return ToolResult(
                tool_call_id=call_id, tool_name=request.tool_name, status="FAILED", error=str(error)
            )

    @staticmethod
    def _validate_arguments(request: ToolRequest) -> None:
        if request.tool_name in {"read_file", "delete_file"}:
            PathRequest.model_validate(request.arguments)
        elif request.tool_name == "list_directory":
            PathRequest.model_validate({"path": request.arguments.get("path", ".")})
        elif request.tool_name in {"create_file", "modify_file"}:
            WriteFileRequest.model_validate(request.arguments)
        elif request.tool_name == "commit_changes":
            paths = request.arguments.get("paths")
            message = request.arguments.get("message")
            if (not isinstance(paths, list) or not paths or not all(isinstance(path, str) for path in paths)
                    or not isinstance(message, str) or not message.strip() or len(message) > 500):
                raise ValueError("commit_changes requires relative paths and a bounded message")
        elif request.tool_name == "search_workspace":
            if not isinstance(request.arguments.get("query"), str):
                raise ValueError("search_workspace requires a query")
        elif request.tool_name in {"run_formatter", "run_tests", "git_diff"} and request.arguments:
            raise ValueError(f"{request.tool_name} does not accept arguments")

    def _reject(
        self, call_id: str, request: ToolRequest, agent: Agent, task: Task, reason: str
    ) -> ToolResult:
        self.repository.save_tool_call(
            call_id,
            agent.project_id,
            agent.agent_id,
            task.task_id,
            request.tool_name,
            "REJECTED",
            {"reason": reason},
        )
        self.audit.record(
            "TOOL_REQUEST_REJECTED",
            project_id=agent.project_id,
            actor_id=agent.agent_id,
            task_id=task.task_id,
            payload={"tool": request.tool_name, "reason": reason},
        )
        return ToolResult(
            tool_call_id=call_id, tool_name=request.tool_name, status="REJECTED", error=reason
        )
