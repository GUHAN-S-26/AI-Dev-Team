"""Small transactional SQLite repository.

SQLite is the authoritative state store in the MVP. Service methods accept
typed models and serialize only validated data as JSON.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from app.schemas.models import (
    Agent,
    Approval,
    ChatMessage,
    MemoryEntry,
    Message,
    Plan,
    PreviewSession,
    Project,
    Task,
    TaskExecution,
)

T = TypeVar("T")


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Repository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _initialize(self) -> None:
        with self.transaction() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY, name TEXT NOT NULL, requirement TEXT NOT NULL,
                    status TEXT NOT NULL, root_path TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, role TEXT NOT NULL,
                    parent_agent_id TEXT, task_id TEXT, payload TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
                CREATE TABLE IF NOT EXISTS agent_memory (
                    memory_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, namespace TEXT NOT NULL,
                    owner_agent_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_memory (
                    memory_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, namespace TEXT NOT NULL,
                    owner_agent_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, assigned_agent TEXT NOT NULL,
                    status TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
                CREATE TABLE IF NOT EXISTS task_dependencies (
                    task_id TEXT NOT NULL, dependency_id TEXT NOT NULL,
                    PRIMARY KEY(task_id, dependency_id), FOREIGN KEY(task_id) REFERENCES tasks(task_id),
                    FOREIGN KEY(dependency_id) REFERENCES tasks(task_id)
                );
                CREATE TABLE IF NOT EXISTS executions (
                    execution_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, project_id TEXT NOT NULL,
                    status TEXT NOT NULL, payload TEXT NOT NULL, started_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
                    project_id TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, action TEXT NOT NULL,
                    decision TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS file_ownership (
                    ownership_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, agent_id TEXT NOT NULL,
                    pattern TEXT NOT NULL, shared INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS file_locks (
                    resource_path TEXT PRIMARY KEY, project_id TEXT NOT NULL, task_id TEXT NOT NULL,
                    owner_agent_id TEXT NOT NULL, acquired_at TEXT NOT NULL, expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tool_calls (
                    tool_call_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, agent_id TEXT NOT NULL,
                    task_id TEXT, tool_name TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY, project_id TEXT, event_type TEXT NOT NULL,
                    actor_id TEXT, task_id TEXT, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, workflow_state TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL,
                    path TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_usage (
                    usage_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, task_id TEXT,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS schema_versions (
                    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL, role TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL, csrf_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL, created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );
                """
            )
            db.execute(
                "INSERT OR IGNORE INTO schema_versions(version, applied_at) VALUES (?, ?)",
                (1, _now()),
            )
            current = db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_versions").fetchone()
            version = int(current[0]) if current else 0
            if version < 2:
                db.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS project_members (
                        project_id TEXT NOT NULL, user_id TEXT NOT NULL,
                        member_role TEXT NOT NULL DEFAULT 'owner', created_at TEXT NOT NULL,
                        PRIMARY KEY(project_id, user_id),
                        FOREIGN KEY(project_id) REFERENCES projects(project_id),
                        FOREIGN KEY(user_id) REFERENCES users(user_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_project_members_user
                        ON project_members(user_id, project_id);
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        message_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                        user_id TEXT NOT NULL, role TEXT NOT NULL,
                        content TEXT NOT NULL, metadata TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(project_id) REFERENCES projects(project_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_chat_messages_project
                        ON chat_messages(project_id, created_at);
                    CREATE TABLE IF NOT EXISTS preview_sessions (
                        project_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                        port INTEGER, url TEXT, container_name TEXT,
                        command TEXT NOT NULL, error TEXT, updated_at TEXT NOT NULL,
                        FOREIGN KEY(project_id) REFERENCES projects(project_id)
                    );

                    """,
                )
                db.execute(
                    "INSERT INTO schema_versions(version, applied_at) VALUES (?, ?)",
                    (2, _now()),
                )

    def schema_version(self) -> int:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_versions").fetchone()
        return int(row[0]) if row else 0

    def backup_to(self, target: Path) -> Path:
        """Create a consistent SQLite backup without exposing database contents."""
        destination = target.resolve()
        if destination == self.path.resolve():
            raise ValueError("backup target must differ from the active database")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            source = sqlite3.connect(self.path)
            backup = sqlite3.connect(destination)
            try:
                source.backup(backup)
                result = backup.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise sqlite3.DatabaseError("backup integrity check failed")
            finally:
                backup.close()
                source.close()
        return destination

    def restore_from(self, source_path: Path, *, confirm: bool = False) -> None:
        """Restore from a backup only when the caller explicitly confirms it."""
        if not confirm:
            raise PermissionError("database restore requires explicit confirmation")
        source = source_path.resolve()
        if source == self.path.resolve() or not source.is_file():
            raise ValueError("restore source must be an existing separate file")
        with self._lock:
            incoming = sqlite3.connect(source)
            target = sqlite3.connect(self.path)
            try:
                incoming.backup(target)
                result = target.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise sqlite3.DatabaseError("restored database integrity check failed")
            finally:
                target.close()
                incoming.close()
        os.utime(self.path, None)

    def create_project(self, project: Project) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    project.project_id,
                    project.name,
                    project.requirement,
                    project.status.value,
                    project.root_path,
                    _dt(project.created_at),
                    _dt(project.updated_at),
                ),
            )

    def get_project(self, project_id: str) -> Project | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        return Project.model_validate(dict(row)) if row else None

    def update_project(self, project: Project) -> None:
        with self.transaction() as db:
            db.execute(
                "UPDATE projects SET name=?, requirement=?, status=?, root_path=?, updated_at=? "
                "WHERE project_id=?",
                (
                    project.name,
                    project.requirement,
                    project.status.value,
                    project.root_path,
                    _dt(project.updated_at),
                    project.project_id,
                ),
            )

    def save_agent(self, agent: Agent) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO agents(agent_id, project_id, role, parent_agent_id, task_id, payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    agent.agent_id,
                    agent.project_id,
                    agent.role,
                    agent.parent_agent_id,
                    agent.task_id,
                    _json(agent.model_dump(mode="json")),
                ),
            )

    def list_agents(self, project_id: str) -> list[Agent]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT payload FROM agents WHERE project_id=? ORDER BY agent_id", (project_id,)
            )
        return [Agent.model_validate(json.loads(row[0])) for row in rows]

    def save_plan(self, project_id: str, plan: Plan) -> None:
        self.save_project_memory(
            MemoryEntry(
                project_id=project_id,
                namespace="approved-plan",
                owner_agent_id="orchestrator",
                content=plan.model_dump(mode="json"),
                approved=False,
            )
        )

    def save_task(self, task: Task) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO tasks(task_id, project_id, assigned_agent, status, payload, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    task.task_id,
                    task.project_id,
                    task.assigned_agent,
                    task.status.value,
                    _json(task.model_dump(mode="json")),
                    _dt(task.created_at),
                    _dt(task.updated_at),
                ),
            )
            db.execute("DELETE FROM task_dependencies WHERE task_id=?", (task.task_id,))
            db.executemany(
                "INSERT INTO task_dependencies(task_id, dependency_id) VALUES (?, ?)",
                [(task.task_id, dependency) for dependency in task.dependencies],
            )

    def get_task(self, task_id: str) -> Task | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT payload FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return Task.model_validate(json.loads(row[0])) if row else None

    def list_tasks(self, project_id: str) -> list[Task]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT payload FROM tasks WHERE project_id=? ORDER BY task_id", (project_id,)
            )
        return [Task.model_validate(json.loads(row[0])) for row in rows]

    def save_execution(self, execution: TaskExecution) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO executions(execution_id, task_id, project_id, status, payload, started_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    execution.execution_id,
                    execution.task_id,
                    execution.project_id,
                    execution.status,
                    _json(execution.model_dump(mode="json")),
                    _dt(execution.started_at),
                ),
            )

    def list_executions(self, task_id: str | None = None) -> list[TaskExecution]:
        with self._lock, self._connect() as db:
            if task_id:
                rows = db.execute(
                    "SELECT payload FROM executions WHERE task_id=? ORDER BY started_at", (task_id,)
                )
            else:
                rows = db.execute("SELECT payload FROM executions ORDER BY started_at")
        return [TaskExecution.model_validate(json.loads(row[0])) for row in rows]

    def save_message(self, message: Message) -> bool:
        with self.transaction() as db:
            try:
                db.execute(
                    "INSERT INTO messages(message_id, idempotency_key, project_id, status, payload, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        message.message_id,
                        message.idempotency_key,
                        message.project_id,
                        message.status,
                        _json(message.model_dump(mode="json")),
                        _dt(message.created_at),
                    ),
                )
                return True
            except sqlite3.IntegrityError as error:
                if "idempotency_key" in str(error):
                    return False
                raise

    def list_messages(self, project_id: str, to_agent: str | None = None) -> list[Message]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT payload FROM messages WHERE project_id=? ORDER BY created_at", (project_id,)
            )
        messages = [Message.model_validate(json.loads(row[0])) for row in rows]
        return [message for message in messages if to_agent is None or message.to_agent == to_agent]

    def mark_message_delivered(self, message_id: str) -> None:
        with self.transaction() as db:
            row = db.execute(
                "SELECT payload FROM messages WHERE message_id=?", (message_id,)
            ).fetchone()
            if not row:
                return
            message = Message.model_validate(json.loads(row[0]))
            message.status = "DELIVERED"
            message.delivered_at = datetime.now(UTC)
            db.execute(
                "UPDATE messages SET status=?, payload=? WHERE message_id=?",
                (message.status, _json(message.model_dump(mode="json")), message_id),
            )

    def save_agent_memory(self, entry: MemoryEntry) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO agent_memory(memory_id, project_id, namespace, owner_agent_id, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    entry.memory_id,
                    entry.project_id,
                    entry.namespace,
                    entry.owner_agent_id,
                    _json(entry.model_dump(mode="json")),
                    _dt(entry.created_at),
                ),
            )

    def save_project_memory(self, entry: MemoryEntry) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO project_memory(memory_id, project_id, namespace, owner_agent_id, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    entry.memory_id,
                    entry.project_id,
                    entry.namespace,
                    entry.owner_agent_id,
                    _json(entry.model_dump(mode="json")),
                    _dt(entry.created_at),
                ),
            )

    def list_memory(
        self, project_id: str, namespace: str, private_owner: str | None = None
    ) -> list[MemoryEntry]:
        with self._lock, self._connect() as db:
            if private_owner:
                rows = db.execute(
                    "SELECT payload FROM agent_memory WHERE project_id=? AND namespace=? AND owner_agent_id=? "
                    "ORDER BY created_at",
                    (project_id, namespace, private_owner),
                )
            else:
                rows = db.execute(
                    "SELECT payload FROM project_memory WHERE project_id=? AND namespace=? ORDER BY created_at",
                    (project_id, namespace),
                )
        return [MemoryEntry.model_validate(json.loads(row[0])) for row in rows]

    def save_approval(self, approval: Approval) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO approvals(approval_id, project_id, action, decision, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    approval.approval_id,
                    approval.project_id,
                    approval.action,
                    approval.decision.value,
                    _json(approval.model_dump(mode="json")),
                    _dt(approval.created_at),
                ),
            )

    def get_approval(self, approval_id: str) -> Approval | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT payload FROM approvals WHERE approval_id=?", (approval_id,)
            ).fetchone()
        return Approval.model_validate(json.loads(row[0])) if row else None

    def list_approvals(self, project_id: str, action: str | None = None) -> list[Approval]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT payload FROM approvals WHERE project_id=? ORDER BY created_at",
                (project_id,),
            )
        approvals = [Approval.model_validate(json.loads(row[0])) for row in rows]
        return [approval for approval in approvals if action is None or approval.action == action]

    def audit(
        self,
        event_type: str,
        *,
        project_id: str | None,
        actor_id: str | None,
        task_id: str | None,
        payload: dict[str, Any],
        event_id: str,
    ) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO audit_events(event_id, project_id, event_type, actor_id, task_id, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, project_id, event_type, actor_id, task_id, _json(payload), _now()),
            )

    def checkpoint(
        self, project_id: str, workflow_state: str, payload: dict[str, Any], checkpoint_id: str
    ) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO workflow_checkpoints(checkpoint_id, project_id, workflow_state, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (checkpoint_id, project_id, workflow_state, _json(payload), _now()),
            )

    def latest_checkpoint(self, project_id: str) -> tuple[str, dict[str, Any]] | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT workflow_state, payload FROM workflow_checkpoints WHERE project_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def save_usage(
        self, project_id: str, task_id: str | None, payload: dict[str, Any], usage_id: str
    ) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO model_usage(usage_id, project_id, task_id, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (usage_id, project_id, task_id, _json(payload), _now()),
            )

    def usage_totals(self, project_id: str, task_id: str | None = None) -> tuple[int, int]:
        with self._lock, self._connect() as db:
            if task_id is None:
                rows = db.execute("SELECT payload FROM model_usage WHERE project_id=?", (project_id,))
            else:
                rows = db.execute(
                    "SELECT payload FROM model_usage WHERE project_id=? AND task_id=?",
                    (project_id, task_id),
                )
        prompt = completion = 0
        for row in rows:
            payload = json.loads(row[0])
            prompt += int(payload.get("prompt_tokens", 0))
            completion += int(payload.get("completion_tokens", 0))
        return prompt, completion

    def save_tool_call(
        self,
        tool_call_id: str,
        project_id: str,
        agent_id: str,
        task_id: str | None,
        tool_name: str,
        status: str,
        payload: dict[str, Any],
    ) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO tool_calls(tool_call_id, project_id, agent_id, task_id, tool_name, status, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tool_call_id,
                    project_id,
                    agent_id,
                    task_id,
                    tool_name,
                    status,
                    _json(payload),
                    _now(),
                ),
            )

    def set_file_ownership(
        self, ownership_id: str, project_id: str, agent_id: str, pattern: str, shared: bool
    ) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO file_ownership VALUES (?, ?, ?, ?, ?)",
                (ownership_id, project_id, agent_id, pattern, int(shared)),
            )

    def list_file_ownership(self, project_id: str) -> list[tuple[str, str, bool]]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT agent_id, pattern, shared FROM file_ownership WHERE project_id=?",
                (project_id,),
            )
        return [(row[0], row[1], bool(row[2])) for row in rows]

    def save_artifact(self, artifact_id: str, project_id: str, kind: str, path: str,
                      payload: dict[str, Any]) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO artifacts(artifact_id, project_id, kind, path, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (artifact_id, project_id, kind, path, _json(payload), _now()),
            )

    def list_artifacts(self, project_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT kind, path, payload, created_at FROM artifacts WHERE project_id=? ORDER BY created_at",
                (project_id,),
            )
        artifacts = [{"kind": row[0], "path": row[1], "payload": json.loads(row[2]), "created_at": row[3]}
                     for row in rows]
        return [artifact for artifact in artifacts if kind is None or artifact["kind"] == kind]

    def list_projects(self) -> list[Project]:
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT * FROM projects ORDER BY updated_at DESC")
        return [Project.model_validate(dict(row)) for row in rows]

    def delete_project(self, project_id: str) -> bool:
        """Delete one project and every persisted project-scoped record.

        The table names are intentionally fixed rather than dynamically built
        from caller input.  Task dependencies are removed first because they
        reference the tasks being removed; the remaining project-scoped rows
        are then deleted in one transaction before the project row itself.
        Filesystem cleanup is owned by the workspace service.
        """
        with self.transaction() as db:
            exists = db.execute(
                "SELECT 1 FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            if exists is None:
                return False
            db.execute(
                "DELETE FROM task_dependencies WHERE task_id IN "
                "(SELECT task_id FROM tasks WHERE project_id = ?) OR dependency_id IN "
                "(SELECT task_id FROM tasks WHERE project_id = ?)",
                (project_id, project_id),
            )
            for statement in (
                "DELETE FROM file_locks WHERE project_id = ?",
                "DELETE FROM tool_calls WHERE project_id = ?",
                "DELETE FROM executions WHERE project_id = ?",
                "DELETE FROM tasks WHERE project_id = ?",
                "DELETE FROM agents WHERE project_id = ?",
                "DELETE FROM agent_memory WHERE project_id = ?",
                "DELETE FROM project_memory WHERE project_id = ?",
                "DELETE FROM messages WHERE project_id = ?",
                "DELETE FROM approvals WHERE project_id = ?",
                "DELETE FROM file_ownership WHERE project_id = ?",
                "DELETE FROM audit_events WHERE project_id = ?",
                "DELETE FROM workflow_checkpoints WHERE project_id = ?",
                "DELETE FROM artifacts WHERE project_id = ?",
                "DELETE FROM model_usage WHERE project_id = ?",
                "DELETE FROM project_members WHERE project_id = ?",
                "DELETE FROM chat_messages WHERE project_id = ?",
                "DELETE FROM preview_sessions WHERE project_id = ?",
            ):
                db.execute(statement, (project_id,))
            db.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            return True

    def add_project_member(self, project_id: str, user_id: str, member_role: str = "owner") -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO project_members(project_id, user_id, member_role, created_at) "
                "VALUES (?, ?, ?, ?)",
                (project_id, user_id, member_role, _now()),
            )

    def has_project_access(self, project_id: str, user_id: str, *, admin: bool = False) -> bool:
        if admin:
            with self._lock, self._connect() as db:
                return db.execute(
                    "SELECT 1 FROM projects WHERE project_id=?", (project_id,)
                ).fetchone() is not None
        with self._lock, self._connect() as db:
            return db.execute(
                "SELECT 1 FROM project_members WHERE project_id=? AND user_id=?",
                (project_id, user_id),
            ).fetchone() is not None

    def list_projects_for_user(self, user_id: str, *, admin: bool = False) -> list[Project]:
        with self._lock, self._connect() as db:
            if admin:
                rows = db.execute("SELECT * FROM projects ORDER BY updated_at DESC")
            else:
                rows = db.execute(
                    "SELECT p.* FROM projects p JOIN project_members m ON m.project_id=p.project_id "
                    "WHERE m.user_id=? ORDER BY p.updated_at DESC",
                    (user_id,),
                )
        return [Project.model_validate(dict(row)) for row in rows]

    def save_chat_message(self, message: ChatMessage) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO chat_messages(message_id, project_id, user_id, role, content, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    message.message_id,
                    message.project_id,
                    message.user_id,
                    message.role,
                    message.content,
                    _json(message.metadata),
                    _dt(message.created_at),
                ),
            )

    def list_chat_messages(self, project_id: str, limit: int = 200) -> list[ChatMessage]:
        bounded_limit = max(1, min(limit, 500))
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT * FROM chat_messages WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, bounded_limit),
            ).fetchall()
        return [
            ChatMessage(
                message_id=row["message_id"],
                project_id=row["project_id"],
                user_id=row["user_id"],
                role=row["role"],
                content=row["content"],
                metadata=json.loads(row["metadata"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in reversed(rows)
        ]

    def save_preview_session(self, session: PreviewSession) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO preview_sessions(project_id, status, port, url, container_name, "
                "command, error, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session.project_id,
                    session.status,
                    session.port,
                    session.url,
                    session.container_name,
                    _json(session.command),
                    session.error,
                    _dt(session.updated_at),
                ),
            )

    def get_preview_session(self, project_id: str) -> PreviewSession | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT * FROM preview_sessions WHERE project_id=?", (project_id,)
            ).fetchone()
        if row is None:
            return None
        return PreviewSession(
            project_id=row["project_id"],
            status=row["status"],
            port=row["port"],
            url=row["url"],
            container_name=row["container_name"],
            command=json.loads(row["command"]),
            error=row["error"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def list_audit_events(self, project_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 1000))
        with self._lock, self._connect() as db:
            if project_id:
                rows = db.execute(
                    "SELECT event_id, project_id, event_type, actor_id, task_id, payload, created_at "
                    "FROM audit_events WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                    (project_id, bounded_limit),
                )
            else:
                rows = db.execute(
                    "SELECT event_id, project_id, event_type, actor_id, task_id, payload, created_at "
                    "FROM audit_events ORDER BY created_at DESC LIMIT ?", (bounded_limit,)
                )
        return [
            {
                "event_id": row[0],
                "project_id": row[1],
                "event_type": row[2],
                "actor_id": row[3],
                "task_id": row[4],
                "payload": json.loads(row[5]),
                "created_at": row[6],
            }
            for row in rows
        ]

    def list_tool_calls(self, project_id: str, limit: int = 200) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 1000))
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT tool_call_id, agent_id, task_id, tool_name, status, payload, created_at "
                "FROM tool_calls WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, bounded_limit),
            )
        return [
            {
                "tool_call_id": row[0], "agent_id": row[1], "task_id": row[2],
                "tool_name": row[3], "status": row[4], "payload": json.loads(row[5]),
                "created_at": row[6],
            }
            for row in rows
        ]

    def usage_summary(self, project_id: str) -> dict[str, int]:
        prompt, completion = self.usage_totals(project_id)
        return {"prompt_tokens": prompt, "completion_tokens": completion,
                "total_tokens": prompt + completion}

    def create_user(self, user_id: str, username: str, password_hash: str, role: str) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO users(user_id, username, password_hash, role, is_active, created_at) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (user_id, username, password_hash, role, _now()),
            )

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def create_session(
        self, session_id: str, token_hash: str, user_id: str, csrf_hash: str,
        expires_at: str,
    ) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO sessions(session_id, token_hash, user_id, csrf_hash, expires_at, created_at, last_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, token_hash, user_id, csrf_hash, expires_at, _now(), _now()),
            )

    def get_session(self, token_hash: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT s.*, u.username, u.role, u.is_active FROM sessions s "
                "JOIN users u ON u.user_id=s.user_id WHERE s.token_hash=?", (token_hash,)
            ).fetchone()
        return dict(row) if row else None

    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def update_session_csrf(self, session_id: str, csrf_hash: str) -> None:
        with self.transaction() as db:
            db.execute(
                "UPDATE sessions SET csrf_hash=?, last_seen_at=? WHERE session_id=?",
                (csrf_hash, _now(), session_id),
            )

    def touch_session(self, session_id: str) -> None:
        with self.transaction() as db:
            db.execute("UPDATE sessions SET last_seen_at=? WHERE session_id=?", (_now(), session_id))

    def delete_session(self, token_hash: str) -> None:
        with self.transaction() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    def delete_expired_sessions(self, now: str) -> int:
        with self.transaction() as db:
            result = db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            return int(result.rowcount)
