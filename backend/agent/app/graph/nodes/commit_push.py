"""
commit_push node — stage changes, commit with [AI-AGENT] prefix, push to branch.

Compliance rules (SOURCE_OF_TRUTH §2):
  - Commit message MUST start with [AI-AGENT].
  - NEVER push to main or master.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

from git import Repo as GitRepo  # type: ignore[import-untyped]

from ...db import insert_trace
from ...events import emit_thought
from ..state import AgentState, FixRecord

logger = logging.getLogger("rift.node.commit_push")

_PROTECTED_BRANCHES = {"main", "master", "develop", "release"}


def _auth_remote_url(url: str) -> str:
    """
    Inject GITHUB_TOKEN into an HTTPS git remote URL for authentication.
    Transforms:  https://github.com/user/repo.git
    Into:        https://x-access-token:<token>@github.com/user/repo.git
    """
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        return url
    # Already has credentials embedded
    if "@" in url.split("//", 1)[-1]:
        return url
    # Only modify HTTPS URLs
    m = re.match(r"https://(.+)", url)
    if m:
        return f"https://x-access-token:{token}@{m.group(1)}"
    return url


async def commit_push(state: AgentState) -> AgentState:
    """
    Commit all applied fixes and push to the healing branch.
    """
    run_id = state["run_id"]
    repo_dir = state.get("repo_dir", "")
    branch_name = state["branch_name"]
    fixes = state.get("fixes", [])
    iteration = state.get("iteration", 1)
    total_commits = state.get("total_commits", 0)
    step = iteration * 10 + 6

    # Safety: never push to protected branches
    if branch_name.lower() in _PROTECTED_BRANCHES:
        error = f"BLOCKED: Refusing to push to protected branch '{branch_name}'"
        logger.error(error)
        await emit_thought(run_id, "commit_push", error, step)
        return {
            "error_message": error,
            "status": "quarantined",
            "quarantine_reason": error,
            "current_node": "commit_push",
            "pushed_this_iteration": False,
        }

    # Filter fixes applied in this iteration
    applied = [f for f in fixes if f.status == "applied" and not f.commit_sha]
    if not applied:
        await emit_thought(run_id, "commit_push", "No new fixes to commit", step)
        return {
            "current_node": "commit_push",
            "pushed_this_iteration": False,
        }

    await emit_thought(
        run_id, "commit_push",
        f"Committing {len(applied)} fix(es) to branch {branch_name}…",
        step,
    )

    def _do_commit() -> tuple[str, int]:
        repo = GitRepo(repo_dir)

        # Configure git user for commits inside this repo
        with repo.config_writer("repository") as cw:
            cw.set_value("user", "name", "RIFT AI Agent")
            cw.set_value("user", "email", "rift-agent@noreply.github.com")

        # Ensure we're on the right branch
        if repo.active_branch.name != branch_name:
            repo.heads[branch_name].checkout()  # type: ignore[union-attr]

        # Stage all changes
        repo.git.add(A=True)

        # Build commit message summarising the fixes
        bug_types = sorted({f.bug_type for f in applied})
        msg = f"[AI-AGENT] Fix {len(applied)} issue(s): {', '.join(bug_types)} (iter {iteration})"

        repo.index.commit(msg)
        commit_sha = repo.head.commit.hexsha[:7]

        # Inject auth token into remote URL for push
        origin = repo.remotes.origin
        original_url = origin.url
        auth_url = _auth_remote_url(original_url)
        if auth_url != original_url:
            origin.set_url(auth_url)

        try:
            # Force push to the healing branch — safe because we never push to
            # protected branches (guarded above) and the branch is created per-run.
            # This handles the case where a previous run already pushed to this branch.
            push_info = origin.push(branch_name, force=True)
            if push_info:
                first = push_info[0]
                flags = getattr(first, "flags", 0)
                summary = getattr(first, "summary", "")
                # REJECTED / REMOTE_REJECTED / ERROR / REMOTE_FAILURE
                bad_mask = (
                    first.REJECTED
                    | first.REMOTE_REJECTED
                    | first.ERROR
                    | first.REMOTE_FAILURE
                )
                if flags & bad_mask:
                    raise RuntimeError(f"Push rejected: {summary}")
        finally:
            # Restore original URL (don't persist token on disk)
            if auth_url != original_url:
                origin.set_url(original_url)

        return commit_sha, 1

    try:
        commit_sha, commits_added = await asyncio.to_thread(_do_commit)
    except Exception as exc:
        error = f"Git commit/push failed: {exc}"
        logger.exception(error)
        await emit_thought(run_id, "commit_push", error, step + 1)

        # Mark fixes as failed
        for f in applied:
            f.status = "failed"

        return {
            "fixes": fixes,
            "error_message": error,
            "current_node": "commit_push",
            "pushed_this_iteration": False,
        }

    # Update fix records with commit SHA
    for f in applied:
        f.commit_sha = commit_sha
        f.commit_message = f"[AI-AGENT] Fix {f.bug_type}: {f.description[:80]}"

    await emit_thought(
        run_id, "commit_push",
        f"Pushed commit {commit_sha} to {branch_name}",
        step + 1,
    )

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="commit_push",
        action_type="git_push",
        action_label=f"Committed and pushed {len(applied)} fix(es)",
        payload={
            "commit_sha": commit_sha,
            "branch": branch_name,
            "fixes_committed": len(applied),
        },
    )

    return {
        "fixes": fixes,
        "total_commits": total_commits + commits_added,
        "current_node": "commit_push",
        "pushed_this_iteration": True,
    }
