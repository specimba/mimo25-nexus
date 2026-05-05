"""Recovery boot — rebuild state from git + filesystem after crash."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class RecoveryState:
    """Compact state recovered from available evidence."""
    project_root: str = ""
    git_branch: str = ""
    recent_commits: list[dict[str, str]] = field(default_factory=list)
    recent_files: list[str] = field(default_factory=list)
    inferred_goal: str = ""
    session_age_seconds: float = 0.0
    recovery_timestamp: float = field(default_factory=time.time)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "git_branch": self.git_branch,
            "recent_commits": self.recent_commits,
            "recent_files": self.recent_files,
            "inferred_goal": self.inferred_goal,
            "session_age_seconds": self.session_age_seconds,
            "recovery_timestamp": self.recovery_timestamp,
            "errors": self.errors,
        }


class RecoveryBoot:
    """Rebuild NEXUS session state from git history and filesystem evidence."""

    def __init__(self, project_root: Optional[str] = None) -> None:
        self._root = Path(project_root) if project_root else Path.cwd()

    # -----------------------------------------------------------------------
    # rebuild_state
    # -----------------------------------------------------------------------

    def rebuild_state(self) -> dict[str, Any]:
        """Rebuild session state from available evidence.

        Checks git log for recent commits, filesystem for recent changes,
        and infers the current goal from patterns.

        Returns a compact state dict.
        """
        state = RecoveryState(project_root=str(self._root))

        # 1. Git state
        state.git_branch = self._git_branch()
        state.recent_commits = self._git_recent_commits(limit=10)

        # 2. Recently changed files (by mtime, last 2 hours)
        state.recent_files = self._recent_files(max_age_seconds=7200)

        # 3. Infer goal from evidence
        state.inferred_goal = self._infer_goal(state)

        return state.to_dict()

    # -----------------------------------------------------------------------
    # generate_cold_handoff
    # -----------------------------------------------------------------------

    def generate_cold_handoff(self) -> str:
        """Generate COLD_HANDOFF.txt content summarizing current state.

        Suitable for a fresh session to pick up where things left off.
        """
        state_data = self.rebuild_state()

        lines = [
            "=" * 60,
            "COLD HANDOFF — NEXUS OS Recovery",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            "",
            f"## Project",
            f"Root: {state_data['project_root']}",
            f"Branch: {state_data['git_branch'] or '(not a git repo)'}",
            "",
        ]

        # Recent commits
        if state_data["recent_commits"]:
            lines.append("## Recent Commits (last 10)")
            for c in state_data["recent_commits"]:
                lines.append(f"  {c['hash'][:8]}  {c['message'][:72]}")
            lines.append("")
        else:
            lines.append("## Recent Commits")
            lines.append("  (none found)")
            lines.append("")

        # Recently changed files
        if state_data["recent_files"]:
            lines.append("## Recently Changed Files (last 2h)")
            for f in state_data["recent_files"][:20]:
                lines.append(f"  {f}")
            if len(state_data["recent_files"]) > 20:
                lines.append(f"  ... and {len(state_data['recent_files']) - 20} more")
            lines.append("")
        else:
            lines.append("## Recently Changed Files")
            lines.append("  (none detected)")
            lines.append("")

        # Inferred goal
        lines.append("## Inferred Goal")
        lines.append(f"  {state_data['inferred_goal']}")
        lines.append("")

        # Errors during recovery
        if state_data["errors"]:
            lines.append("## Recovery Warnings")
            for e in state_data["errors"]:
                lines.append(f"  ⚠ {e}")
            lines.append("")

        lines.append("=" * 60)
        lines.append("End of handoff. Good luck, next agent.")
        lines.append("=" * 60)

        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _run_git(self, args: list[str], timeout: int = 5) -> str:
        """Run a git command and return stdout. Returns empty on failure."""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return ""

    def _git_branch(self) -> str:
        return self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])

    def _git_recent_commits(self, limit: int = 10) -> list[dict[str, str]]:
        """Get recent git commits as [{hash, message, author, date}]."""
        fmt = "%H|%s|%an|%ai"
        raw = self._run_git(["log", f"--format={fmt}", f"-{limit}", "--no-decorate"])
        if not raw:
            return []
        commits: list[dict[str, str]] = []
        for line in raw.splitlines():
            parts = line.split("|", 3)
            if len(parts) >= 2:
                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                    "author": parts[2] if len(parts) > 2 else "",
                    "date": parts[3] if len(parts) > 3 else "",
                })
        return commits

    def _recent_files(self, max_age_seconds: int = 7200) -> list[str]:
        """Find files modified within the last ``max_age_seconds``."""
        cutoff = time.time() - max_age_seconds
        recent: list[tuple[float, str]] = []
        root_str = str(self._root)

        for dirpath, dirnames, filenames in os.walk(root_str):
            # Skip hidden dirs and common noise
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in {"__pycache__", "node_modules", ".git", "venv", ".venv"}
            ]
            for fname in filenames:
                if fname.startswith("."):
                    continue
                fpath = os.path.join(dirpath, fname)
                try:
                    mtime = os.path.getmtime(fpath)
                    if mtime >= cutoff:
                        rel = os.path.relpath(fpath, root_str)
                        recent.append((mtime, rel))
                except OSError:
                    continue

        # Sort newest first
        recent.sort(reverse=True)
        return [f for _, f in recent]

    def _infer_goal(self, state: RecoveryState) -> str:
        """Infer what the project was working on from available evidence."""
        # Check if there's a TODO or goal file
        for goal_file in ("TODO.md", "GOAL.md", "TASK.md", "PLAN.md"):
            gpath = self._root / goal_file
            if gpath.exists():
                try:
                    content = gpath.read_text(encoding="utf-8", errors="replace")[:500]
                    return f"[from {goal_file}] {content.strip()[:200]}"
                except OSError:
                    pass

        # Infer from recent commit messages
        if state.recent_commits:
            msgs = [c["message"] for c in state.recent_commits[:3]]
            return "Recent work: " + " | ".join(msgs)

        # Infer from recently changed files
        if state.recent_files:
            dirs = set()
            for f in state.recent_files[:10]:
                parts = f.split("/")
                if len(parts) > 1:
                    dirs.add(parts[0])
            return f"Recently active in: {', '.join(sorted(dirs))}"

        return "Unable to infer goal — no recent activity detected"
