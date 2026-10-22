import json
from copy import deepcopy
from unittest import TestCase
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch

from app.db.topic_report_repository import TopicReportRepository, PROMPT_VERSION as REPOSITORY_VERSION
from app.services.topic_report import OpenRouterTopicReportClient, TopicReportResponseError, PROMPT_VERSION, _schema
from app.services.topic_report_coverage import topic_report_coverage
from app.topic_report_api import _client_item, _with_scope_supplements


class TopicReportCompletenessTests(TestCase):
    def evidence(self):
        return [{'id':key,'topic_title':f'논의 {key}','summary':f'원래 논의 {key}의 조건과 요청 사항.',
                 'meeting_title':'회의','meeting_at':'2026-10-19','ministries':['행정안전부'],
                 'tasks':[{'title':f'자료 제출 요구 {i}','ministries':['행정안전부']} for i in range(11)]}
                for key in ['a','b']]

    def report(self):
        return {'title':'정책 보고서','executive_summary':'논의와 과제를 정리했다.',
                'policy_implications':[{'title':f'시사점 {i}','body':'정책 실행을 점검해야 한다.','evidence_ids':[key]}
                                       for i,key in enumerate(['a','b'])],
                'sections':[{'heading':f'세부 논의 {i}','body':'자료와 이행 계획을 제출하도록 요구했다.',
                             'ministries':['행정안전부'],'evidence_ids':[key]}
                            for i,key in enumerate(['a','b'])],
                'tasks':[],'timeline':[],'limitations':''}

    def generate(self, report, evidence):
        payload={'id':'response-test','choices':[{'finish_reason':'stop','message':{'content':json.dumps(report,ensure_ascii=False)}}]}
        response=Mock();response.json.return_value=payload
        with patch('app.services.topic_report.requests.post',return_value=response):
            return OpenRouterTopicReportClient('fake-key',model='test',base_url='https://example.test').generate(
                ministry='행정안전부',topic='',period_start='2026-10-01',period_end='2026-10-20',evidence=evidence)

    def test_missing_narrative_evidence_is_rejected_even_if_cited_in_implication(self):
        report=self.report()
        report['sections'][1]['evidence_ids']=['a']
        with self.assertRaisesRegex(TopicReportResponseError,'EVIDENCE_COVERAGE_INCOMPLETE'):
            self.generate(report,self.evidence())

    def test_oversized_input_fails_before_call_instead_of_dropping_sources(self):
        with patch('app.services.topic_report.MAX_EVIDENCE_CHARS',1), \
             patch('app.services.topic_report.requests.post') as request:
            with self.assertRaisesRegex(TopicReportResponseError,'EVIDENCE_INPUT_TOO_LARGE'):
                OpenRouterTopicReportClient('fake-key',model='test',base_url='https://example.test').generate(
                    ministry='',topic='',period_start='2026-10-01',period_end='2026-10-20',evidence=self.evidence())
            request.assert_not_called()

    def test_oversized_output_is_rejected_without_slicing(self):
        report=self.report();report['policy_implications'][0]['body']='가'*701
        with self.assertRaisesRegex(TopicReportResponseError,'OUTPUT_FIELD_TOO_LONG'):
            self.generate(report,self.evidence())

    def test_complete_report_keeps_audit_and_original_model_response(self):
        result=self.generate(self.report(),self.evidence())
        audit=result.usage_metadata['generation_audit']
        self.assertEqual((2,2,2),(audit['evidence_provided'],audit['evidence_sent'],audit['narrative_evidence_covered']))
        self.assertEqual(audit['response_snapshot']['id'],'response-test')
        self.assertEqual(PROMPT_VERSION,REPOSITORY_VERSION)
        public=_client_item({'status':'READY','report':result.report,'evidence':self.evidence(),'usage_metadata':result.usage_metadata})
        self.assertNotIn('usage_metadata',public)
        self.assertEqual(public['coverage']['source_task_count'],22)

    def test_inventory_is_complete_for_legacy_report_without_rewriting_it(self):
        report=self.report();evidence=self.evidence()
        report['sections'][1]['evidence_ids']=['a'];report['policy_implications'][1]['evidence_ids']=['a']
        original=deepcopy(report)
        coverage=topic_report_coverage(report,evidence)
        self.assertEqual(coverage['evidence_count'],2)
        self.assertEqual(coverage['report_uncited_ids'],['b'])
        self.assertFalse(coverage['semantic_completeness_verified'])
        self.assertEqual(report,original)
        markdown=TopicReportRepository.markdown({'report':report,'evidence':evidence,'period_start':'2026-10-01','period_end':'2026-10-20','provider':'openrouter','model':'test'})
        for source in evidence:
            self.assertIn(source['summary'],markdown)
            for task in source['tasks']:self.assertIn(task['title'],markdown)
        self.assertIn('### 2. 논의 b',markdown)

    def test_default_search_keeps_all_results_and_all_source_tasks(self):
        topics = [{'id':str(i),'title':f'논의 {i}','summary':'행안부에서 대책을 검토했다.'} for i in range(60)]
        tasks = [{'topic_id':'0','title':f'자료 요구 {i}','ministries':['행정안전부']} for i in range(11)]
        connection=Mock()
        connection.execute.return_value.fetchall.return_value=[('m','회의','LEGISLATURE','위원회',datetime(2026,10,19,tzinfo=timezone.utc),{'topics':topics,'tasks':tasks},{},'PENDING')]
        repository=TopicReportRepository(connection)
        all_rows=repository.search(ministry='행안부',topic='',period_start=date(2026,10,1),period_end=date(2026,10,20))
        self.assertEqual(all_rows['count'],60)
        self.assertFalse(all_rows['selection_limited'])
        self.assertEqual(len(next(s for s in all_rows['items'] if s['id']=='m:0')['tasks']),11)
        limited=repository.search(ministry='행안부',topic='',period_start=date(2026,10,1),period_end=date(2026,10,20),limit=40)
        self.assertEqual((limited['count'],limited['total_count']),(40,60))
        self.assertTrue(limited['selection_limited'])
        self.assertEqual(_schema(60)['properties']['sections']['items']['properties']['evidence_ids']['maxItems'],60)

    def test_legacy_scope_supplements_do_not_modify_saved_evidence_or_narrative(self):
        saved={'status':'READY','report':self.report(),'evidence':self.evidence()[:1],
               'period_start':date(2026,10,1),'period_end':date(2026,10,20),'ministry':'행안부','topic':''}
        original=deepcopy(saved)
        repository=Mock();repository.search.return_value={'items':self.evidence(),'count':2}
        with patch('app.topic_report_api._official_executive_items',return_value=[]):
            projected=_with_scope_supplements(saved,repository)
        self.assertEqual(projected['evidence'],original['evidence'])
        self.assertEqual(projected['report'],original['report'])
        self.assertEqual(projected['supplementary_evidence'],self.evidence()[1:])
        self.assertEqual(saved,original)
        self.assertEqual(_client_item(projected)['coverage']['evidence_count'],2)
