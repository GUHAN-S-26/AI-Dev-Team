"""Git worktree operations owned by the trusted control plane."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


class GitWorktreeManager:
    _branch_re = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,80}$")

    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()

    def _run(self, args: list[str]) -> str:
        completed = subprocess.run(
            ["git", *args], cwd=self.repository, capture_output=True, text=True, check=False
        )
        if completed.returncode:
            raise GitError(completed.stderr.strip() or completed.stdout.strip())
        return completed.stdout.strip()

    def create_worktree(self, branch: str, path: Path, base: str = "main") -> Path:
        if not self._branch_re.fullmatch(branch) or not self._branch_re.fullmatch(base):
            raise GitError("invalid branch name")
        target = path.resolve()
        if target.exists():
            status = subprocess.run(["git", "status", "--short", "--branch"], cwd=target,
                                    capture_output=True, text=True, check=False)
            if status.returncode == 0:
                return target
            raise GitError("worktree path already exists and is not a valid worktree")
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run(["worktree", "add", "-b", branch, str(target), base])
        return target

    def status(self, worktree: Path) -> str:
        completed = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=worktree,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            raise GitError(completed.stderr.strip())
        return completed.stdout

    def diff(self, worktree: Path) -> str:
        completed = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--binary"],
            cwd=worktree,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            raise GitError(completed.stderr.strip())
        return completed.stdout

    def changed_paths(self) -> list[str]:
        completed = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=self.repository,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            raise GitError(completed.stderr.strip() or "unable to inspect worktree changes")
        paths: list[str] = []
        for line in completed.stdout.splitlines():
            if len(line) < 4:
                continue
            path = line[3:]
            if " -> " in path:
                raise GitError("renamed paths require explicit review")
            candidate = Path(path)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise GitError("worktree reported an invalid changed path")
            paths.append(candidate.as_posix())
        return sorted(set(paths))

    def commit_paths(self, paths: list[str], message: str) -> str | None:
        if not paths or not message.strip() or len(message) > 500:
            raise GitError("a non-empty commit message and at least one path are required")
        if any(not path or Path(path).is_absolute() or ".." in Path(path).parts for path in paths):
            raise GitError("commit paths must be relative and cannot traverse")
        self._run(["add", "--", *paths])
        staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=self.repository,
                                capture_output=True, text=True, check=False)
        if staged.returncode == 0:
            return None
        if staged.returncode != 1:
            raise GitError(staged.stderr.strip() or "unable to inspect staged changes")
        self._run(["-c", "user.name=AI Dev Team", "-c", "user.email=ai-dev-team@localhost",
                   "commit", "-m", message])
        return self._run(["rev-parse", "HEAD"])
