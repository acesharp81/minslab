#!/usr/bin/env python3
"""Check the deployed PoC7 stack without reading credentials or restarting services."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

PREFIX = 'poc07-national-assembly-'
DATABASE = PREFIX + 'db'
NETWORK = 'poc07-national-assembly'
VOLUME = 'poc07_national_assembly_pgdata'
CONTAINERS = [DATABASE, PREFIX + 'api', 'poc07-openrouter-gateway', *[
    PREFIX + name for name in (
        'live-monitor', 'caption-worker', 'executive-caption-worker', 'schedule-worker',
        'summary-worker', 'meeting-brief-worker', 'official-minutes-worker',
        'official-integration-worker', 'watch-worker', 'watch-summary-worker',
        'notification-worker', 'topic-report-worker', 'review-worker')]]
URLS = [
    'http://127.0.0.1:18070/api/health',
    'http://127.0.0.1:18070/api/live/broadcasts?limit=1',
    'https://kjon.aigov.go.kr/', 'https://kjon.aigov.go.kr/api/health',
    'https://www.minslab.kr/poc/national-assembly/',
    'https://www.minslab.kr/poc/national-assembly/api/health',
]
FORMAT = ('{"name":{{json .Name}},"state":{{json .State.Status}},'
          '"restart":{{json .HostConfig.RestartPolicy.Name}},'
          '"networks":{{json .NetworkSettings.Networks}},"mounts":{{json .Mounts}}}')


def command(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    if result.returncode:
        # Docker stderr can contain operator-supplied strings; report only the operation.
        raise RuntimeError('command_failed:' + args[0] + ':' + args[1] + ':' + str(result.returncode))
    return result.stdout


def inspect_runtime(names: list[str], run: Callable[[list[str]], str] = command) -> list[dict[str, Any]]:
    # Formatted inspect deliberately excludes Config.Env and all credentials.
    return [json.loads(line) for line in run(
        ['docker', 'container', 'inspect', '--format', FORMAT, *names]).splitlines() if line.strip()]


def container_checks(rows: list[dict[str, Any]], names: list[str], *, repair_policy: bool = False,
                     run: Callable[[list[str]], str] = command) -> list[dict[str, Any]]:
    indexed = {r['name'].lstrip('/'): r for r in rows}
    checks: list[dict[str, Any]] = []
    for name in names:
        row = indexed.get(name)
        if not row:
            checks.append({'check': name, 'ok': False, 'reason': 'container_missing'})
            continue
        state, policy = row['state'], row['restart']
        repaired = False
        # A deliberate stop is respected. Repair only restart-policy drift on a running service.
        if repair_policy and state == 'running' and policy != 'unless-stopped':
            run(['docker', 'update', '--restart', 'unless-stopped', name])
            fresh = inspect_runtime([name], run)[0]
            state, policy = fresh['state'], fresh['restart']
            repaired = policy == 'unless-stopped'
        checks.append({'check': name, 'ok': state == 'running' and policy == 'unless-stopped',
                       'state': state, 'restart': policy, 'policy_repaired': repaired})
        if name == DATABASE:
            network = row.get('networks', {}).get(NETWORK, {})
            checks.append({'check': 'db_network_alias', 'ok': 'db' in (network.get('Aliases') or [])})
            checks.append({'check': 'db_persistent_volume', 'ok': any(
                m.get('Type') == 'volume' and m.get('Name') == VOLUME
                and m.get('Destination') == '/var/lib/postgresql/data' and m.get('RW')
                for m in row.get('mounts', []))})
    return checks


def check_url(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=6) as response:
            payload = response.read(100000)
            healthy = response.status == 200
            if url.endswith('/api/health'):
                healthy = healthy and json.loads(payload).get('status') == 'ok'
            if '/api/live/broadcasts?' in url:
                healthy = healthy and isinstance(json.loads(payload).get('items'), list)
            return {'check': url, 'ok': bool(healthy), 'http_status': response.status}
    except Exception as exc:
        return {'check': url, 'ok': False, 'error': type(exc).__name__}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=['database', 'all'], default='all')
    parser.add_argument('--repair-restart-policy', action='store_true',
                        help='Correct restart policy only for running production containers.')
    args = parser.parse_args()
    names = [DATABASE] if args.scope == 'database' else CONTAINERS
    checks: list[dict[str, Any]] = []
    try:
        checks.extend(container_checks(inspect_runtime(names), names, repair_policy=args.repair_restart_policy))
        command(['docker', 'exec', DATABASE, 'pg_isready', '-U', 'national_assembly', '-d', 'national_assembly'])
        checks.append({'check': 'postgres_ready', 'ok': True})
    except Exception as exc:
        checks.append({'check': 'docker_or_postgres', 'ok': False, 'error': str(exc)})
    if args.scope == 'all':
        with ThreadPoolExecutor(max_workers=5) as pool:
            checks.extend(pool.map(check_url, URLS))
    ok = bool(checks) and all(check['ok'] for check in checks)
    print(json.dumps({'status': 'ok' if ok else 'failed', 'scope': args.scope, 'checks': checks}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
