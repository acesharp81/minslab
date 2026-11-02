#!/usr/bin/env python3
"""Publish selected MinsLab directories as independent GitLab repositories."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
from time import monotonic
from typing import Iterator


@dataclass(frozen=True)
class Project:
    name: str
    prefix: str
    remote: str
    token_env: str = ""


PROJECTS = {
    "kjon": Project(
        "국정ON", "PoC/07-NationalAssembly",
        "https://gitlab.aigov.go.kr/acesharp/kjon.git",
        "GITLAB_KJON_TOKEN",
    ),
    "home": Project(
        "the주택", "PoC/10-home",
        "https://gitlab.aigov.go.kr/acesharp/HOME.git",
        "GITLAB_HOME_TOKEN",
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


def token_for(project: Project | None, env: dict[str, str]) -> str | None:
    if project and project.token_env:
        if project.token_env in env or any(env.get(p.token_env) for p in PROJECTS.values()):
            token = env.get(project.token_env)
            if not token:
                raise SyncError(f"{project.name}용 {project.token_env}을 설정하세요.")
            return token
    return env.get("GITLAB_TOKEN")


@contextmanager
def push_environment(project: Project | None = None) -> Iterator[dict[str, str]]:
    """Read CI credentials through askpass, never through URLs or files."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    token = token_for(project, env)
    # Each Git process gets only its selected token, including in its environment.
    for configured in PROJECTS.values():
        env.pop(configured.token_env, None)
    if not token:
        yield env
        return
    env["GITLAB_TOKEN"] = token
    if not env.get("GITLAB_USERNAME"):
        env["GITLAB_USERNAME"] = "gitlab-sync"
    # Hardened runners may mount /tmp with noexec. RUNNER_TEMP is the runner's
    # executable job scratch directory, also cleaned when the job completes.
    with tempfile.TemporaryDirectory(prefix="minslab-gitlab-auth-", dir=env.get("RUNNER_TEMP") or None) as directory:
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


def trace_summary(trace: Path) -> list[str]:
    """Only emit transport timing/status; never emit headers, bodies or credentials."""
    events: list[str] = []
    if not trace.exists():
        return events
    for line in trace.read_text(encoding="utf-8", errors="replace").splitlines():
        stamp = re.match(r"(\d{2}:\d{2}:\d{2}\.\d+) ", line)
        if not stamp:
            continue
        message = None
        status = re.search(r"<= Recv header: HTTP/[\d.]+ (\d{3})(?: |$)", line)
        length = re.search(r"=> Send header: [Cc]ontent-[Ll]ength: (\d+)$", line)
        uploaded = re.search(r"== Info: (?:We are completely uploaded and fine|upload completely sent off: (\d+) bytes)$", line)
        if status:
            message = f"HTTP {status[1]}"
        elif length:
            message = f"request bytes={length[1]}"
        elif uploaded:
            message = "upload complete" + (f" bytes={uploaded[1]}" if uploaded[1] else "")
        if message:
            events.append(f"{stamp[1]} {message}")
    return events


def publish(root: Path, export: Export, env: dict[str, str], *, diagnose: bool = False) -> str:
    if export.dirty:
        raise SyncError(f"{export.project.prefix}에 미커밋 변경이 있습니다. 먼저 검토·커밋하세요.")
    # The GitLab front proxy requests retransmission during large initial
    # pushes. Buffer these requests so Git can rewind instead of failing on
    # a chunked upload with curl 65. Scoped to this push, not global Git config.
    options = ["-c", "push.followTags=false", "-c", "http.postBuffer=268435456",
               "-c", "http.version=HTTP/1.1"]
    if env.get("GITLAB_TOKEN"):
        # Do not let a credential helper save the CI token.
        options += ["-c", "credential.helper="]
    command = [*options, "push", "--porcelain", "--recurse-submodules=no",
               export.project.remote, f"{export.commit}:refs/heads/main"]
    if not diagnose:
        return git(root, *command, env=env)
    with tempfile.TemporaryDirectory(prefix="minslab-gitlab-trace-", dir=env.get("RUNNER_TEMP") or None) as directory:
        trace = Path(directory) / "transport.log"
        private_env = dict(env, GIT_TRACE_CURL=str(trace), GIT_TRACE_CURL_NO_DATA="1", GIT_TRACE_REDACT="1")
        started = monotonic()
        try:
            return git(root, *command, env=private_env)
        finally:
            for event in trace_summary(trace):
                print(f"  transport: {event}", flush=True)
            print(f"  push elapsed: {monotonic() - started:.1f}s", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", choices=[*PROJECTS, "all"])
    parser.add_argument("--push", action="store_true", help="분리한 이력을 GitLab main에 반영")
    parser.add_argument("--diagnose", action="store_true", help="전송 상태와 시간만 출력 (인증값·본문 제외)")
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
        for export in exports:
            token_for(export.project, dict(os.environ))
        for export in exports:
            with push_environment(export.project) as env:
                print(publish(root, export, env, diagnose=args.diagnose), flush=True)
        return 0
    except (SyncError, OSError) as error:
        print(f"동기화 중단: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
