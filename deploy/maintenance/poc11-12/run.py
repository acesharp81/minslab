"""One-time retirement, retried on 2026-10-21 after 23:00 Asia/Seoul.

--check validates the reviewed change without changing the running application.
--execute is restricted to the approved maintenance window.
"""
import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

JOB = Path(__file__).resolve().parent
ROOT = JOB.parents[2]
STATE = ROOT / "data/maintenance/poc11-12-20261021"
TARGETS = ("PoC/11-consultation-cases", "PoC/12-housing-board")
UNIT = Path("/etc/systemd/system/poc12.service")
KST = ZoneInfo("Asia/Seoul")
START = datetime(2026, 10, 21, 23, 5, tzinfo=KST)
END = datetime(2026, 10, 22, 0, 0, tzinfo=KST)
DOCUMENTATION = {"README.md", "PoC/README.md", "PoC/10-home/README.md"}
PATHS = ("/health", "/poc/home/", "/poc/national-assembly/",
         "/poc/mwomeokji/", "/poc/ai-common-platform-radar/")
REMOVED = ("/home2", "/counsel", "/poc/housing-board",
           "/poc/housing-board/map", "/poc/consultation-cases/",
           "/poc/consultation-cases/api/status")


def command(*args, check=True, timeout=180):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"Command failed: {args!r}\n{result.stdout}\n{result.stderr}")
    return result


def systemctl(*args, check=True):
    if args != ("daemon-reload",) and (not args or args[-1] not in {"myservice.service", "poc12.service"}):
        raise RuntimeError(f"Service operation outside the approved deletion scope: {args!r}")
    return command("sudo", "-n", "/usr/bin/systemctl", *args, check=check)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path, content):
    mode = path.stat().st_mode & 0o777
    fd, temporary = tempfile.mkstemp(prefix=".poc-retirement-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class PreparedChanges(dict):
    def __init__(self, candidates=None, originals=None):
        super().__init__(candidates or {})
        self.originals = originals or {}


def prepare_shared_edits(entries):
    candidates = PreparedChanges()
    for entry in entries:
        path = ROOT / entry["path"]
        source = path.read_bytes()
        if path.is_symlink() or (entry["path"] not in DOCUMENTATION and
                                hashlib.sha256(source).hexdigest() != entry["sha256"]):
            raise RuntimeError(f"Reviewed file changed; manual review required: {entry['path']}")
        content = source.decode("utf-8")
        for old, new in entry["replacements"]:
            if content.count(old) != 1:
                raise RuntimeError(f"Edit no longer matches: {entry['path']}")
            content = content.replace(old, new, 1)
        candidates[entry["path"]] = content.encode()
        candidates.originals[entry["path"]] = source
    return candidates


def reviewed_changes():
    review = json.loads((JOB / "review.json").read_text())
    allowed_shared_files = {"main.py", "README.md", "PoC/README.md", ".gitignore", ".env.example"}
    if any(entry["path"] not in allowed_shared_files for entry in review["edits"]):
        raise RuntimeError("Planned writes extend beyond the approved shared files")
    for relative, expected in review["configuration_hashes"].items():
        if digest(ROOT / relative) != expected:
            raise RuntimeError(f"Configuration changed; manual review required: {relative}")
    candidates = prepare_shared_edits(review["edits"])
    tracked = command("git", "ls-files", "--cached", "--others", "--exclude-standard",
                      "-z", "--", *TARGETS).stdout.split("\0")
    if set(filter(None, tracked)) != set(review["target_files"]):
        raise RuntimeError("Target source file list changed; manual review required")
    for relative, expected in review["target_files"].items():
        path = ROOT / relative
        if path.is_symlink() or digest(path) != expected:
            raise RuntimeError(f"Target source changed; manual review required: {relative}")
    for relative in TARGETS:
        path = ROOT / relative
        if path.is_symlink() or not path.is_dir():
            raise RuntimeError(f"Unsafe target directory: {relative}")
    if UNIT.is_symlink() or digest(UNIT) != review["unit_sha256"]:
        raise RuntimeError("Installed poc12 unit changed; manual review required")
    dependencies = command("systemctl", "show", "poc12.service", "-p", "RequiredBy",
                           "-p", "WantedBy", "-p", "BoundBy", "-p", "ConsistsOf").stdout
    if dependencies != review["reverse_dependencies"]:
        raise RuntimeError("New reverse service dependency; manual review required")
    refs = command("git", "grep", "--untracked", "--exclude-standard", "-I", "-l", "-i", "-E",
                   r"POC(11|12)(\b|_)|11-consultation-cases|12-housing-board|/home2\b|/counsel\b",
                   "--", ".", ":!PoC/11-consultation-cases/**", ":!PoC/12-housing-board/**",
                   ":!deploy/maintenance/poc11-12/**", check=False)
    if refs.returncode not in (0, 1):
        raise RuntimeError(refs.stderr)
    # Preserve the existing historical documentation link inside protected PoC 10.
    unexpected = set(refs.stdout.splitlines()) - set(candidates) - {"PoC/10-home/README.md"}
    if unexpected:
        raise RuntimeError(f"New references require review: {sorted(unexpected)}")
    compile(candidates["main.py"], str(ROOT / "main.py"), "exec")
    return candidates


def validate(candidates):
    with tempfile.TemporaryDirectory(prefix="poc-retirement-check-") as temporary:
        candidate = Path(temporary) / "main.py"
        candidate.write_bytes(candidates["main.py"])
        result = command(str(ROOT / ".venv/bin/python"), str(JOB / "validate.py"), str(candidate))
        print(result.stdout, end="", flush=True)
        print(result.stderr, end="", flush=True)


def status(path, timeout=10):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8000" + path, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (OSError, TimeoutError):
        return 0


def snapshot():
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(PATHS)) as pool:
        return dict(zip(PATHS, pool.map(status, PATHS)))


def verify_retired_routes():
    # The existing application serves its home shell for every unknown URL.
    # Retired URLs must follow that fallback, with no redirect or PoC content.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://127.0.0.1:8000/", timeout=15) as response:
        home = response.read()
    title = re.search(rb"<title>.*?</title>", home, re.DOTALL)
    if title is None:
        raise RuntimeError("Home shell has no document title")
    for identifier in (b'"id": "consultation-cases"', b'"id": "housing-board"'):
        if identifier in home:
            raise RuntimeError("A retired PoC is still registered in the menu")
    for path in REMOVED:
        with opener.open("http://127.0.0.1:8000" + path, timeout=15) as response:
            body = response.read()
            if (response.status != 200 or response.geturl() != "http://127.0.0.1:8000" + path
                    or title.group() not in body
                    or any(identifier in body for identifier in
                           (b'"id": "consultation-cases"', b'"id": "housing-board"'))):
                raise RuntimeError(f"Retired route did not fall back to the home shell: {path}")


def record(value):
    value["updated_at"] = datetime.now(KST).isoformat()
    path = STATE / "result.json"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(value, ensure_ascii=False), flush=True)


def execute(immediate=False):
    if not immediate and not START <= datetime.now(KST) < END:
        raise RuntimeError(f"Outside the approved {START:%Y-%m-%d} 23:05-23:59 KST window")
    STATE.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(STATE, 0o700)
    with (STATE / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (STATE / "result.json").exists():
            raise RuntimeError("A previous execution is recorded; manual review required")
        report = {"status": "preflight", "scheduled_at": START.isoformat(),
                  "execution_mode": "user_approved_immediate" if immediate else "scheduled"}
        record(report)
        try:
            candidates = reviewed_changes()
            originals = candidates.originals
            validate(candidates)
            # Abort before any service change if the main application is unhealthy.
            systemctl("is-active", "myservice.service")
            systemctl("is-active", "poc12.service")
            baseline = snapshot()
            if baseline["/health"] != 200:
                raise RuntimeError("Main application is unhealthy before maintenance")
            report["before"] = baseline
            for relative, content in originals.items():
                if (ROOT / relative).read_bytes() != content:
                    raise RuntimeError(f"File changed during preflight: {relative}")
            backup = STATE / "shared-before"
            for relative, content in originals.items():
                path = backup / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            saved_unit = STATE / "poc12.service.before"
            saved_unit.write_bytes(UNIT.read_bytes())
            enabled = command("systemctl", "is-enabled", "poc12.service", check=False).stdout.strip()
        except Exception as error:
            report.update(status="aborted", error=str(error))
            record(report)
            raise

        moved = []
        changed = []
        finalized = False
        try:
            report["status"] = "applying"
            record(report)
            systemctl("stop", "poc12.service")
            systemctl("stop", "myservice.service")
            for relative, content in candidates.items():
                if (ROOT / relative).read_bytes() != originals[relative]:
                    raise RuntimeError(f"Concurrent file change; stopping deployment: {relative}")
                atomic_write(ROOT / relative, content)
                changed.append(relative)
            quarantine = STATE / "pending-delete"
            quarantine.mkdir(mode=0o700)
            for relative in TARGETS:
                destination = quarantine / Path(relative).name
                (ROOT / relative).rename(destination)
                moved.append((ROOT / relative, destination))
            systemctl("start", "myservice.service")
            deadline = time.monotonic() + 45
            while status("/health", timeout=2) != 200:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Main application did not recover after restart")
                time.sleep(1)
            after = snapshot()
            report["after"] = after
            for path, before in baseline.items():
                if before and before < 500 and after[path] != before:
                    raise RuntimeError(f"Existing endpoint changed: {path}: {before} -> {after[path]}")
            verify_retired_routes()
            with socket.socket() as connection:
                connection.settimeout(2)
                if connection.connect_ex(("127.0.0.1", 18120)) == 0:
                    raise RuntimeError("Retired listener 18120 is still active")
            systemctl("disable", "poc12.service")
            command("sudo", "-n", "/usr/bin/rm", "--", str(UNIT))
            systemctl("daemon-reload")
            finalized = True
            for _, destination in moved:
                shutil.rmtree(destination)
            quarantine.rmdir()
            report.update(status="completed", removed=list(TARGETS))
            record(report)
        except Exception as error:
            report["error"] = str(error)
            if finalized:
                report["status"] = "cleanup_failed"
            else:
                try:
                    systemctl("stop", "myservice.service")
                    for original, destination in reversed(moved):
                        destination.rename(original)
                    for relative in reversed(changed):
                        atomic_write(ROOT / relative, originals[relative])
                    if not UNIT.exists():
                        command("sudo", "-n", "/usr/bin/install", "-m", "0644", str(saved_unit), str(UNIT))
                    systemctl("daemon-reload")
                    if enabled == "enabled":
                        systemctl("enable", "poc12.service")
                    systemctl("start", "poc12.service")
                    systemctl("start", "myservice.service")
                    report["status"] = "rolled_back"
                except Exception as rollback_error:
                    report.update(status="rollback_failed", rollback_error=str(rollback_error))
            record(report)
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--execute-now", action="store_true",
                      help="Execute immediately after explicit user approval, retaining all data checks")
    args = parser.parse_args()
    if args.check:
        validate(reviewed_changes())
        print("Reviewed deletion is valid. No application files or services were changed.")
    else:
        execute(immediate=args.execute_now)
