"""Project repositories and isolated Git worktrees."""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.tools.git_manager import GitError, GitWorktreeManager


class WorkspaceManager:
    def __init__(self, projects_dir: Path, workspaces_dir: Path) -> None:
        self.projects_dir = projects_dir
        self.workspaces_dir = workspaces_dir

    def initialize_project(self, project_id: str) -> Path:
        root = (self.projects_dir / project_id).resolve()
        root.mkdir(parents=True, exist_ok=True)
        if not (root / ".git").exists():
            self._run(root, ["git", "init", "-b", "main"])
            self._run(
                root,
                [
                    "git",
                    "-c",
                    "user.name=AI Dev Team",
                    "-c",
                    "user.email=ai-dev-team@localhost",
                    "add",
                    ".",
                ],
            )
            self._run(
                root,
                [
                    "git",
                    "-c",
                    "user.name=AI Dev Team",
                    "-c",
                    "user.email=ai-dev-team@localhost",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "Initialize project",
                ],
            )
        return root

    def create_agent_worktree(self, project_id: str, role: str, root: Path) -> Path:
        manager = GitWorktreeManager(root)
        path = self.workspaces_dir / project_id / role
        return manager.create_worktree(role, path, "main")

    @staticmethod
    def _run(cwd: Path, args: list[str]) -> None:
        completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
        if completed.returncode:
            raise GitError(completed.stderr.strip() or completed.stdout.strip())
