from __future__ import annotations

from pathlib import Path

from app.database.repository import Repository
from app.schemas.models import ChatMessage, PreviewSession, Project, new_id


def test_phase_three_schema_and_project_scoped_records(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "state.sqlite3")
    assert repository.schema_version() == 2
    user_id = new_id("USER")
    repository.create_user(user_id, "workspace-user", "test-hash", "developer")
    first = Project(name="First", requirement="Build first", root_path=str(tmp_path / "first"))
    second = Project(name="Second", requirement="Build second", root_path=str(tmp_path / "second"))
    repository.create_project(first)
    repository.create_project(second)
    repository.add_project_member(first.project_id, user_id)
    assert [item.project_id for item in repository.list_projects_for_user(user_id)] == [first.project_id]
    assert repository.has_project_access(first.project_id, user_id)
    assert not repository.has_project_access(second.project_id, user_id)
    repository.save_chat_message(
        ChatMessage(project_id=first.project_id, user_id=user_id, role="user", content="Build a landing page")
    )
    assert [item.content for item in repository.list_chat_messages(first.project_id)] == ["Build a landing page"]
    assert repository.list_chat_messages(second.project_id) == []
    session = PreviewSession(project_id=first.project_id, status="RUNNING", port=8123, url="http://127.0.0.1:8123/")
    repository.save_preview_session(session)
    assert repository.get_preview_session(first.project_id) == session
