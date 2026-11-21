#!/usr/bin/env python3
"""Select project snapshots from a pinned GitHub push or approved manual event."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

import gitlab_sync as sync

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/sync-gitlab-projects.yml"


def full_sha(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{40}", value)) and value != "0" * 40


def projects_for_paths(paths: list[str]) -> list[str]:
    if any(path == WORKFLOW or path in ("deploy/gitlab_sync.py", "deploy/gitlab_sync_event.py")
           or path.startswith(("deploy/gitlab-projects/", "deploy/gitlab-runner/")) for path in paths):
        return list(sync.PROJECTS)
    selected = []
    for key, project in sync.PROJECTS.items():
        prefix = project.prefix + "/"
        for path in paths:
            if not path.startswith(prefix):
                continue
            relative = path[len(prefix):]
            if not any(relative == excluded or relative.startswith(excluded + "/")
                       for excluded in sync.EXCLUDED_PATHS):
                selected.append(key)
                break
    return selected


def publication_request(root: Path, event: dict, env: dict) -> tuple[str, list[str]]:
    if env.get("GITHUB_REPOSITORY") != "acesharp81/minslab" or env.get("GITHUB_REF") != "refs/heads/main":
        raise sync.SyncError("Only minslab main can publish project snapshots.")
    event_name = env.get("GITHUB_EVENT_NAME")
    if event_name == "workflow_dispatch":
        inputs = event.get("inputs") or {}
        source, project = inputs.get("source_sha"), inputs.get("project")
        if inputs.get("approved") not in (True, "true") or not full_sha(source) or project not in (*sync.PROJECTS, "all"):
            raise sync.SyncError("Manual publication requires project, full source SHA and approval.")
        return source, list(sync.PROJECTS) if project == "all" else [project]
    if event_name != "push":
        raise sync.SyncError("Unsupported publication event.")
    source = event.get("after")
    if event.get("ref") != "refs/heads/main" or event.get("deleted") or not full_sha(source) or source != env.get("GITHUB_SHA"):
        raise sync.SyncError("Push source must match the pinned main event commit.")
    before = event.get("before")
    if before == "0" * 40:
        return source, list(sync.PROJECTS)
    if not full_sha(before):
        raise sync.SyncError("Push event requires a full before SHA.")
    try:
        sync.git(root, "cat-file", "-e", before + "^{commit}")
    except sync.SyncError:
        # A force update can leave the previous commit unreachable in a fresh checkout.
        # Reconcile all projects; normal (never forced) GitLab pushes still protect history.
        return source, list(sync.PROJECTS)
    paths = sync.git(root, "diff", "--no-renames", "--name-only", "-z", before, source).split("\0")
    # GitHub concurrency may replace a pending run with a newer push. Reconcile
    # all four snapshots whenever relevant changes exist so that an intervening
    # change to another project is not lost. Unchanged exports are no-op pushes.
    return source, list(sync.PROJECTS) if projects_for_paths(paths) else []


def main() -> int:
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        source, projects = publication_request(ROOT, event, dict(os.environ))
        print(f"Source: {source}; projects: {', '.join(projects) or 'none'}", flush=True)
        failed = []
        for project in projects:
            if sync.main([project, "--source", source, "--approve-source", source, "--push", "--diagnose"]):
                failed.append(project)
        if failed:
            print("Publication failed: " + ", ".join(failed), file=sys.stderr)
        return int(bool(failed))
    except (sync.SyncError, OSError, KeyError, ValueError, TypeError, AttributeError) as error:
        print(f"Publication stopped: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
