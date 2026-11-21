import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

DEPLOY = Path(__file__).resolve().parents[1] / 'deploy'
sys.path.insert(0, str(DEPLOY))
import gitlab_sync_event as event_sync


class GitLabEventTests(unittest.TestCase):
    def setUp(self):
        self.env = dict(GITHUB_REPOSITORY='acesharp81/minslab', GITHUB_REF='refs/heads/main',
                        GITHUB_EVENT_NAME='push', GITHUB_SHA='b' * 40, GITLAB_SYNC_POLICY='project-auto-v1')
        self.event = dict(ref='refs/heads/main', before='a' * 40, after='b' * 40, deleted=False)

    def test_selects_changed_projects_including_deleted_and_moved_paths(self):
        self.assertEqual(event_sync.projects_for_paths([
            'PoC/08-AICommonPlatformRadar/app/removed.py', 'PoC/10-home/backend/renamed.py',
            'PoC/07-NationalAssembly/docs/evidence/large.json', 'README.md']), ['home', 'check'])
        self.assertEqual(event_sync.projects_for_paths(['PoC/13-handover/README.md']), ['baton'])
        self.assertEqual(event_sync.projects_for_paths(['PoC/07-NationalAssembly/backend/app/main.py']), ['kjon'])

    def test_ignores_evidence_and_unrelated_paths_but_keeps_runtime_fixtures(self):
        self.assertEqual(event_sync.projects_for_paths(['PoC/10-home/docs/evidence/a.json',
            'PoC/07-NationalAssembly/data/recovery/a.wav', 'PoC/01-other/app.py']), [])
        self.assertEqual(event_sync.projects_for_paths(['PoC/10-home/tests/fixtures/a.json']), ['home'])

    def test_sync_configuration_reconciles_all_projects(self):
        for path in (event_sync.WORKFLOW, 'deploy/gitlab_sync.py', 'deploy/gitlab_sync_event.py',
                     'deploy/gitlab-runner/job-guard.sh', 'deploy/gitlab-projects/README.md'):
            self.assertEqual(event_sync.projects_for_paths([path]), list(event_sync.sync.PROJECTS))

    def test_push_uses_full_git_diff_not_truncated_event_commit_list(self):
        with patch.object(event_sync.sync, 'git', side_effect=['', 'PoC/13-handover/app/a.py\0']) as git:
            self.assertEqual(event_sync.publication_request(DEPLOY, self.event, self.env), ('b' * 40, list(event_sync.sync.PROJECTS)))
            git.assert_called_with(DEPLOY, 'diff', '--no-renames', '--name-only', '-z', 'a' * 40, 'b' * 40)

    def test_irrelevant_push_does_not_publish(self):
        with patch.object(event_sync.sync, 'git', side_effect=['', 'README.md\0']):
            self.assertEqual(event_sync.publication_request(DEPLOY, self.event, self.env), ('b' * 40, []))

    def test_new_branch_and_unavailable_previous_commit_reconcile_all(self):
        source, projects = event_sync.publication_request(DEPLOY, dict(self.event, before='0' * 40), self.env)
        self.assertEqual(projects, list(event_sync.sync.PROJECTS))
        with patch.object(event_sync.sync, 'git', side_effect=event_sync.sync.SyncError('unavailable')):
            self.assertEqual(event_sync.publication_request(DEPLOY, self.event, self.env), (source, projects))

    def test_rejects_unpinned_or_untrusted_pushes(self):
        for changes in ({'after': 'c' * 40}, {'deleted': True}, {'ref': 'refs/heads/other'},
                        {'before': 'invalid'}, {'after': '0' * 40}):
            with self.assertRaises(event_sync.sync.SyncError):
                event_sync.publication_request(DEPLOY, dict(self.event, **changes), self.env)
        for changes in ({'GITHUB_EVENT_NAME': 'pull_request'}, {'GITHUB_REPOSITORY': 'fork/minslab'},
                        {'GITHUB_REF': 'refs/heads/feature'}, {'GITLAB_SYNC_POLICY': ''}):
            with self.assertRaises(event_sync.sync.SyncError):
                event_sync.publication_request(DEPLOY, self.event, dict(self.env, **changes))

    def test_manual_keeps_exact_approved_source_and_selection(self):
        env = dict(self.env, GITHUB_EVENT_NAME='workflow_dispatch')
        inputs = dict(source_sha='c' * 40, project='check', approved='true')
        self.assertEqual(event_sync.publication_request(DEPLOY, {'inputs': inputs}, env), ('c' * 40, ['check']))
        for changes in ({'approved': 'false'}, {'source_sha': 'main'}, {'project': 'unknown'}):
            with self.assertRaises(event_sync.sync.SyncError):
                event_sync.publication_request(DEPLOY, {'inputs': dict(inputs, **changes)}, env)

    def test_failure_in_one_project_still_attempts_remaining_projects(self):
        with tempfile.NamedTemporaryFile(mode='w') as event_file:
            json.dump({'inputs': dict(source_sha='c' * 40, project='all', approved='true')}, event_file)
            event_file.flush()
            with patch.dict(os.environ, dict(self.env, GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_EVENT_PATH=event_file.name)), \
                 patch.object(event_sync.sync, 'main', side_effect=[1, 0, 0, 0]) as publish:
                self.assertEqual(event_sync.main(), 1)
                self.assertEqual([call.args[0][0] for call in publish.call_args_list], list(event_sync.sync.PROJECTS))
                for call in publish.call_args_list:
                    self.assertEqual(call.args[0][1:5], ['--source', 'c' * 40, '--approve-source', 'c' * 40])


if __name__ == '__main__':
    unittest.main()
