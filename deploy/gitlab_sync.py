#!/usr/bin/env python3
"""Publish selected MinsLab directories as independent GitLab repositories."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Iterator


@dataclass(frozen=True)
class Project:
    name: str
    prefix: str
    remote: str


PROJECTS = {
    "kjon": Project(
        "국정ON", "PoC/07-NationalAssembly",
        "https://gitlab.aigov.go.kr/acesharp/kjon.git",
    ),
    "home": Project(
        "the주택", "PoC/10-home",
        "https://gitlab.aigov.go.kr/acesharp/HOME.git",
    ),
}


class SyncError(RuntimeError):
    pass


def git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, env=env,
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip()
        raise SyncError(message or f"git {args[0]} failed ({result.returncode})")
    return result.stdout.strip()


@dataclass(frozen=True)
class Export:
    project: Project
    source: str
    commit: str
    files: int
    dirty: bool


def prepare_export(root: Path, project: Project, source: str) -> Export:
    """Split committed history without changing branches, index or worktree."""
    if git(root, "rev-parse", "--is-shallow-repository") == "true":
        raise SyncError("전체 Git 이력이 필요합니다. git fetch --unshallow 후 다시 실행하세요.")
    expected_tree = git(root, "rev-parse", f"{source}:{project.prefix}")
    if git(root, "cat-file", "-t", expected_tree) != "tree":
        raise SyncError(f"프로젝트 폴더를 찾을 수 없습니다: {project.prefix}")
    dirty = bool(git(
        root, "status", "--porcelain=v1", "--untracked-files=normal",
        "--", project.prefix,
    ))
    commit = git(root, "subtree", "split", f"--prefix={project.prefix}", source)
    if git(root, "rev-parse", f"{commit}^{{tree}}") != expected_tree:
        raise SyncError(f"분리 결과가 원본 프로젝트와 다릅니다: {project.name}")
    files = len(git(root, "ls-tree", "-r", "--name-only", "-z", commit).split("\0"))
    # ls-tree -z ends with NUL. Empty trees are not valid subtree exports.
    return Export(project, source, commit, files - 1, dirty)


@contextmanager
def push_environment() -> Iterator[dict[str, str]]:
    """Read CI credentials through askpass, never through URLs or files."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    if not env.get("GITLAB_TOKEN"):
        yield env
        return
    if not env.get("GITLAB_USERNAME"):
        raise SyncError("GITLAB_TOKEN 사용 시 GITLAB_USERNAME도 설정하세요.")
    with tempfile.TemporaryDirectory(prefix="minslab-gitlab-auth-") as directory:
        askpass = Path(directory) / "askpass.py"
        askpass.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "prompt = sys.argv[1].lower()\n"
            "if 'username' in prompt:\n"
            "    print(os.environ['GITLAB_USERNAME'])\n"
            "elif 'password' in prompt:\n"
            "    print(os.environ['GITLAB_TOKEN'])\n"
            "else:\n"
            "    sys.exit(1)\n",
            encoding="utf-8",
        )
        askpass.chmod(0o700)
        env.update(GIT_ASKPASS=str(askpass), LC_ALL="C")
        yield env


def publish(root: Path, export: Export, env: dict[str, str]) -> str:
    if export.dirty:
        raise SyncError(f"{export.project.prefix}에 미커밋 변경이 있습니다. 먼저 검토·커밋하세요.")
    options = ["-c", "push.followTags=false"]
    if env.get("GITLAB_TOKEN"):
        # Do not let a credential helper save the CI token.
        options += ["-c", "credential.helper="]
    return git(
        root, *options, "push", "--porcelain", "--recurse-submodules=no",
        export.project.remote, f"{export.commit}:refs/heads/main", env=env,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", choices=[*PROJECTS, "all"])
    parser.add_argument("--push", action="store_true", help="분리한 이력을 GitLab main에 반영")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        source = git(root, "rev-parse", "HEAD")
        keys = list(PROJECTS) if args.project == "all" else [args.project]
        exports = []
        for key in keys:
            project = PROJECTS[key]
            print(f"{project.name}: {project.prefix} → {project.remote}", flush=True)
            export = prepare_export(root, project, source)
            exports.append(export)
            print(f"  원본 {source[:12]} / 분리 {export.commit[:12]} / 파일 {export.files}개")
            if export.dirty:
                print("  미커밋 변경이 있습니다. 위 결과에는 커밋된 내용만 포함됩니다.")
        if not args.push:
            print("미리보기 완료. GitLab에 반영하려면 --push를 추가하세요.")
            return 0
        # Check every selected project before publishing any of them.
        if any(export.dirty for export in exports):
            raise SyncError("선택한 프로젝트의 미커밋 변경을 먼저 검토·커밋하세요.")
        with push_environment() as env:
            for export in exports:
                print(publish(root, export, env), flush=True)
        return 0
    except (SyncError, OSError) as error:
        print(f"동기화 중단: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
