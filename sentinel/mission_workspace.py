"""Read-only workspace observation for Phase 1 missions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class WorkspaceObservation:
    root: str
    git_available: bool
    branch: str
    head_sha: str
    origin_main_sha: str
    dirty: bool
    untracked_count: int

    def to_evidence(self) -> dict[str, object]:
        return {
            "workspace_root": self.root,
            "git_available": self.git_available,
            "branch": self.branch,
            "head_sha": self.head_sha,
            "origin_main_sha": self.origin_main_sha,
            "dirty": self.dirty,
            "untracked_count": self.untracked_count,
        }


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def observe_workspace(root: Path | str = ".") -> WorkspaceObservation:
    workspace = Path(root).resolve()
    try:
        branch = _git(workspace, "branch", "--show-current") or "DETACHED"
        head_sha = _git(workspace, "rev-parse", "HEAD")
        origin_main_sha = _git(workspace, "rev-parse", "origin/main")
        status_lines = tuple(
            line for line in _git(workspace, "status", "--porcelain").splitlines()
            if line
        )
    except RuntimeError:
        return WorkspaceObservation(
            root=str(workspace),
            git_available=False,
            branch="UNKNOWN",
            head_sha="UNKNOWN",
            origin_main_sha="UNKNOWN",
            dirty=True,
            untracked_count=0,
        )

    return WorkspaceObservation(
        root=str(workspace),
        git_available=True,
        branch=branch,
        head_sha=head_sha,
        origin_main_sha=origin_main_sha,
        dirty=bool(status_lines),
        untracked_count=sum(1 for line in status_lines if line.startswith("??")),
    )
