"""Deployment safety checks use fake executables, never production Docker mutations."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('runtime_checks', ROOT / 'scripts/check_runtime.py')
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def db(state='running', policy='unless-stopped'):
    return {'name': '/' + runtime.DATABASE, 'state': state, 'restart': policy,
            'networks': {runtime.NETWORK: {'Aliases': ['db']}},
            'mounts': [{'Type': 'volume', 'Name': runtime.VOLUME,
                        'Destination': '/var/lib/postgresql/data', 'RW': True}]}


class RuntimeChecks(unittest.TestCase):
    def test_original_outage_is_detected_without_mutation(self):
        for row in [db(policy='no'), db(state='exited')]:
            calls = []
            result = runtime.container_checks([row], [runtime.DATABASE], run=lambda args: calls.append(args))
            self.assertFalse(all(c['ok'] for c in result))
            self.assertEqual(calls, [])

    def test_running_policy_drift_is_repaired_and_rechecked(self):
        calls = []
        def run(args):
            calls.append(args)
            return json.dumps(db()) if args[1] == 'container' else ''
        result = runtime.container_checks([db(policy='no')], [runtime.DATABASE], repair_policy=True, run=run)
        self.assertTrue(all(c['ok'] for c in result))
        self.assertTrue(result[0]['policy_repaired'])
        self.assertEqual(calls[0], ['docker', 'update', '--restart', 'unless-stopped', runtime.DATABASE])
        self.assertEqual(calls[1][1:3], ['container', 'inspect'])

    def test_policy_update_must_be_verified(self):
        def run(args):
            return json.dumps(db(policy='no')) if args[1] == 'container' else ''
        result = runtime.container_checks([db(policy='no')], [runtime.DATABASE], repair_policy=True, run=run)
        self.assertFalse(result[0]['ok'])
        self.assertFalse(result[0]['policy_repaired'])

    def test_manual_stop_is_not_started_or_modified(self):
        calls = []
        result = runtime.container_checks([db(state='exited', policy='no')], [runtime.DATABASE],
                                          repair_policy=True, run=lambda args: calls.append(args))
        self.assertFalse(result[0]['ok'])
        self.assertEqual(calls, [])

    def test_wrong_alias_or_volume_is_detected(self):
        row = db();row['networks'][runtime.NETWORK]['Aliases'] = ['other']
        row['mounts'][0]['Name'] = 'empty-new-volume'
        checks = {c['check']: c for c in runtime.container_checks([row], [runtime.DATABASE])}
        self.assertFalse(checks['db_network_alias']['ok'])
        self.assertFalse(checks['db_persistent_volume']['ok'])

    def test_rollback_containers_are_not_repaired(self):
        backup = db(policy='no');backup['name'] += '-rollback-old'
        calls = []
        result = runtime.container_checks([db(), backup], [runtime.DATABASE],
                                          repair_policy=True, run=lambda args: calls.append(args))
        self.assertTrue(all(c['ok'] for c in result))
        self.assertEqual(calls, [])

    def test_http_502_and_wrong_health_body_fail(self):
        with patch.object(runtime.urllib.request, 'urlopen', side_effect=OSError('connection refused')):
            self.assertFalse(runtime.check_url('https://example.test/')['ok'])
        class Response(io.BytesIO):
            status = 502
        with patch.object(runtime.urllib.request, 'urlopen', return_value=Response(b'Bad Gateway')):
            self.assertFalse(runtime.check_url('https://example.test/')['ok'])
        class HealthyHTTP(io.BytesIO):
            status = 200
        with patch.object(runtime.urllib.request, 'urlopen', return_value=HealthyHTTP(b'{"status":"failed"}')):
            self.assertFalse(runtime.check_url('https://example.test/api/health')['ok'])

    @unittest.skipUnless(os.geteuid() == 0, 'deployment scripts require root; fake tools prevent all Docker access')
    def test_failed_preflight_never_stops_existing_services(self):
        with tempfile.TemporaryDirectory(prefix='poc07-deploy-guard-') as tmp:
            bin_dir = Path(tmp)
            (bin_dir / 'python3').write_text('#!/bin/sh\nexit 23\n')
            # A deployment reaching docker is an error, even for read-only inspect.
            marker = bin_dir / 'docker-was-called'
            (bin_dir / 'docker').write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 99\n')
            for executable in bin_dir.iterdir():executable.chmod(0o755)
            env = {**os.environ, 'PATH': str(bin_dir) + ':/usr/bin:/bin'}
            for script in ['deploy_api.sh', 'deploy_secure_workers.sh', 'deploy_live_capture_workers.sh']:
                result = subprocess.run(['/bin/bash', str(ROOT / 'scripts' / script)], env=env,
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 23, script)
            self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
