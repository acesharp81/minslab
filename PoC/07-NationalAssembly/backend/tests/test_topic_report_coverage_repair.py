import json
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch

from app.services.topic_report import OpenRouterTopicReportClient, TopicReportResponseError
from app.services.topic_report_coverage import topic_report_coverage
from app.db.topic_report_repository import TopicReportRepository
from app.ingestion.topic_report_worker import record_topic_report_usage


def response(content, request_id):
    value = Mock()
    value.json.return_value = {
        'id': request_id, 'model': 'test', 'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30},
        'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(content, ensure_ascii=False)}}],
    }
    return value


class CoverageRepairTests(TestCase):
    def evidence(self):
        return [{'id': key, 'topic_title': title, 'summary': text, 'ministries': ['행정안전부'], 'tasks': []}
                for key, title, text in [('a', '재난 대응', '재난 대응 체계를 점검했다.'),
                                         ('b', '승강기 안전', '승강기 점검 주기 30일을 검토하고 자료 제출을 요구했다.'),
                                         ('c', '개인정보 유출', '개인정보 유출 통지 기한 72시간의 준수 여부를 점검했다.')]]

    def draft(self):
        return {'title': '재난 대응', 'executive_summary': '재난 대응을 점검했다.',
                'policy_implications': [{'title': '대응 개선', 'body': '대응 역량을 높여야 한다.', 'evidence_ids': ['a']},
                                        {'title': '점검 강화', 'body': '점검 계획을 수립해야 한다.', 'evidence_ids': ['a']}],
                'sections': [{'heading': '재난 대응', 'body': '재난 대응을 점검했다.', 'ministries': ['행정안전부'], 'evidence_ids': ['a']},
                             {'heading': '안전 정책', 'body': '안전 정책을 검토했다.', 'ministries': ['행정안전부'], 'evidence_ids': ['a']}],
                'tasks': [], 'timeline': [], 'limitations': ''}

    def repair(self):
        return {'E001': {'section_heading': '안전 정책', 'heading': '승강기 안전 점검',
                         'body': '승강기 점검 주기 30일을 검토하고 관련 자료 제출을 요구했다.'},
                'E002': {'section_heading': '정보 보호', 'heading': '개인정보 유출 통지',
                         'body': '개인정보 유출 통지 기한 72시간의 준수 여부를 점검했다.'}}

    def call(self, responses, reserve=None):
        client = OpenRouterTopicReportClient('fake', model='test', base_url='https://example.test',
                                             before_additional_request=reserve)
        with patch('app.services.topic_report.requests.post', side_effect=responses) as post:
            result = client.generate(ministry='행정안전부', topic='', period_start='2026-10-01',
                                     period_end='2026-10-20', evidence=self.evidence())
        return result, post

    def test_missing_sources_get_independent_ai_summaries_and_grounded_ids(self):
        draft = self.draft(); reserve = Mock(); summary = deepcopy(draft)
        summary['title'] = '안전 정책과 정보 보호 종합 점검'
        result, post = self.call([response(draft, 'main'), response(self.repair(), 'repair'), response(summary, 'summary')], reserve)
        self.assertEqual(2, reserve.call_count)
        self.assertEqual('안전 정책과 정보 보호 종합 점검', result.report['title'])
        self.assertEqual(draft['sections'][0]['body'], result.report['sections'][0]['body'])
        children = [d for s in result.report['sections'] for d in s.get('discussions', [])]
        self.assertEqual([['b'], ['c']], [d['evidence_ids'] for d in children])
        self.assertIn('30일', children[0]['body']); self.assertIn('자료 제출', children[0]['body'])
        self.assertIn('72시간', children[1]['body'])
        self.assertEqual('정보 보호', result.report['sections'][-1]['heading'])
        self.assertFalse(topic_report_coverage(result.report, self.evidence())['narrative_uncited_ids'])
        schema = post.call_args_list[1].kwargs['json']['response_format']['json_schema']['schema']
        self.assertEqual(['E001', 'E002'], schema['required'])
        self.assertEqual(3, len(result.usage_metadata['generation_audit']['response_snapshots']))
        self.assertEqual(90, result.usage_metadata['usage']['total_tokens'])
        md = TopicReportRepository.markdown({'report': result.report, 'evidence': self.evidence(),
                                             'period_start': '2026-10-01', 'period_end': '2026-10-20', 'provider': 'test', 'model': 'test'})
        for child in children: self.assertIn(child['body'], md)

    def test_partial_repair_retries_only_the_source_still_missing(self):
        repair = self.repair()
        result, post = self.call([response(self.draft(), 'main'), response({'E001': repair['E001']}, 'partial'),
                                  response({'E001': repair['E002']}, 'rest'), response(self.draft(), 'summary')])
        repair_prompt = post.call_args_list[2].kwargs['json']['messages'][1]['content']
        data = json.loads(repair_prompt.split('\n', 1)[1])
        self.assertEqual(['c'], [s['id'] for s in data['evidence_by_key'].values()])
        self.assertEqual(2, result.usage_metadata['generation_audit']['coverage_repair']['repaired_count'])

    def test_blank_or_unknown_keys_do_not_count_as_completed_coverage(self):
        with self.assertRaisesRegex(TopicReportResponseError, 'EVIDENCE_COVERAGE_INCOMPLETE') as caught:
            self.call([response(self.draft(), 'main'), response({'unknown': self.repair()['E001']}, 'bad1'),
                       response({'E001': {'section_heading': '', 'heading': '', 'body': ''}}, 'bad2')])
        audit = caught.exception.usage_metadata['generation_audit']
        self.assertEqual(3, len(audit['response_snapshots']))
        self.assertEqual(['b', 'c'], audit['coverage_repair']['remaining_ids'])

    def test_limit_prevents_an_additional_provider_call_and_retains_first_response(self):
        reserve = Mock(side_effect=TopicReportResponseError('OPENROUTER_DAILY_LIMIT'))
        with self.assertRaisesRegex(TopicReportResponseError, 'OPENROUTER_DAILY_LIMIT') as caught:
            self.call([response(self.draft(), 'main')], reserve)
        self.assertEqual(1, len(caught.exception.usage_metadata['generation_audit']['response_snapshots']))

    def test_usage_is_recorded_per_actual_response_id_for_idempotent_deduplication(self):
        usage = Mock()
        snapshots = [response({}, 'first').json(), response({}, 'second').json()]
        record_topic_report_usage(usage, 'test', {'generation_audit': {'response_snapshots': snapshots}})
        self.assertEqual(['first', 'second'], [c.args[2]['request_id'] for c in usage.record_monthly_token_usage.call_args_list])
        self.assertEqual([30, 30], [c.args[2]['usage']['total_tokens'] for c in usage.record_monthly_token_usage.call_args_list])
