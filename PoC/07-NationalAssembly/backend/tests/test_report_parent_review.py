from copy import deepcopy
import unittest
from unittest.mock import MagicMock, patch

from app.services.report_parent_review import (
    PROFILE, request_for, prompt, project, validate, apply, local_context,
)


def fixture():
    return {
        'topics': [{'id': 't1', 'evidence_ids': ['e1']}, {'id': 't2', 'evidence_ids': ['e2']}],
        'tasks': [{'id': 'task1', 'related_topic_ids': ['t1'], 'evidence_ids': ['e1']}],
        'topic_groups': [
            {'id': 'g1', 'title': 'AI 교육', 'topic_ids': ['t1'], 'evidence_ids': ['e1']},
            {'id': 'g2', 'title': '학교 AI 교육 지침', 'topic_ids': ['t2'], 'evidence_ids': ['e2']}],
        'narrative_coverage': {'status': 'COMPLETE'},
        'topic_structure': {'revision_id': 'sid', 'parent_count': 2},
        'topic_grouping': {'group_count': 2},
        'report_summary': {'topics': [
            {'id': 's1', 'source_structured_topic_id': 't1', 'title': '교육', 'summary': '교육 내용 논의.', 'evidence_ids': ['e1']},
            {'id': 's2', 'source_structured_topic_id': 't2', 'title': '지침', 'summary': '학교 지침 논의.', 'evidence_ids': ['e2']},
            {'id': 'extra', 'summary': '보존된 추가 과제.'}],
            'topic_groups': [{'id': 'sg1', 'title': '교육', 'topic_ids': ['s1']},
                             {'id': 'sg2', 'title': '지침', 'topic_ids': ['s2']},
                             {'id': 'sg3', 'title': '추가 요구 과제', 'topic_ids': ['extra']}]}}


def answer():
    return {'groups': [{'title': '학교 AI 교육', 'summary': '학교 교육 내용과 지침을 논의했다.',
                        'kind': 'POLICY', 'member_ids': ['G001', 'G002']}]}


class ParentReviewTests(unittest.TestCase):
    def test_partition_and_exact_payload_preservation(self):
        b = fixture(); original = deepcopy(b)
        r = project(b, request_for(b, {}), answer())
        self.assertEqual(b, original)
        for field in ['topics', 'tasks', 'narrative_coverage']:
            self.assertEqual(r[field], b[field])
        self.assertEqual(r['report_summary']['topics'], b['report_summary']['topics'])
        self.assertEqual(r['topic_groups'][0]['topic_ids'], ['t1', 't2'])
        self.assertEqual(r['topic_groups'][0]['source_groups'], b['topic_groups'])
        self.assertEqual(r['report_summary']['topic_groups'][-1]['topic_ids'], ['extra'])
        self.assertEqual(r['topic_structure']['parent_count'], 1)

    def test_procedural_last_preserves_content_and_places_retained_tasks_before_procedure(self):
        b = fixture(); original = deepcopy(b)
        response = {'groups': [
            {'title': '회의 진행', 'summary': '개회와 발언 시간 안내.', 'kind': 'PROCEDURAL', 'member_ids': ['G001']},
            {'title': '교육 정책', 'summary': '학교 지침 논의.', 'kind': 'POLICY', 'member_ids': ['G002']}]}
        result = project(b, request_for(b, {}), response)
        self.assertEqual(result['topic_groups'][-1]['topic_ids'], ['t1'])
        self.assertEqual(result['report_summary']['topic_groups'][-1]['topic_ids'], ['s1'])
        self.assertEqual(result['report_summary']['topic_groups'][1]['topic_ids'], ['extra'])
        self.assertEqual(b, original)
        self.assertEqual(result['topics'], b['topics'])
        self.assertEqual(result['tasks'], b['tasks'])
        self.assertEqual(result['report_summary']['topics'], b['report_summary']['topics'])

    def test_legacy_procedure_sort_is_conservative_stable_and_idempotent(self):
        from app.services.report_parent_review import order_procedural_last, procedural_group
        for title in ['회의 진행 및 개회·정회·산회', '회의 운영', '발언 순서 안내']:
            self.assertTrue(procedural_group({'title': title}), title)
        for title in ['의사진행 제도 개선', '자료 제출 요구', '예산안 심사 및 의결', '증인 채택 및 수사 독립성']:
            self.assertFalse(procedural_group({'title': title}), title)
        b = fixture(); b['topic_groups'][0]['title'] = '회의 진행'
        result = order_procedural_last(b)
        self.assertEqual(result['topic_groups'][-1]['id'], 'g1')
        self.assertEqual(result['report_summary']['topic_groups'][-1]['topic_ids'], ['s1'])
        self.assertEqual(order_procedural_last(result), result)

    def test_reject_missing_duplicate_and_unknown_ids(self):
        req = request_for(fixture(), {})
        for ids in [[], ['G001'], ['G001', 'G001', 'G002'], ['G001', 'G999']]:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                value = answer(); value['groups'][0]['member_ids'] = ids
                validate(req, value)

    def test_stale_fingerprint_never_applies_and_changed_summary_invalidates(self):
        b = fixture(); req = request_for(b, {})
        rows = [(900000, req, answer())]
        self.assertEqual(apply(b, rows, {})['parent_review']['status'], 'READY')
        b['report_summary']['topics'][0]['summary'] += ' 수정 내용.'
        self.assertNotIn('parent_review', apply(b, rows, {}))

    def test_no_raw_source_in_prompt(self):
        b = fixture()
        source = {'atoms': [{'evidence_id': 'e1', 'sequence': 1, 'text': '외부로 전달하면 안 되는 원문 전문'}]}
        self.assertNotIn('외부로 전달', prompt(request_for(b, source)))
        self.assertNotIn('evidence_ids', prompt(request_for(b, source)))

    def test_media_boundaries_and_ambiguous_ai_context(self):
        texts = ['짧은 영상을 준비했습니다. 영상을 시청하시겠습니다.', '신데렐라는 꿈에도 몰랐어요.',
                 '이거 짝퉁인 거 아세요?', '잘 만들었는데요. 박수 한번 주세요.',
                 '구제역 백신과 돼지열병 방역을 논의합니다.', '다른 AI.', '조류도감.']
        snapshot = {'atoms': [{'text': t, 'sequence': i, 'evidence_id': str(i)} for i, t in enumerate(texts)]}
        hints = local_context(snapshot)
        self.assertIn('영상', hints['1'][0]); self.assertIn('영상', hints['2'][0])
        self.assertNotIn('0', hints); self.assertNotIn('3', hints)
        self.assertIn('가축', hints['5'][0]); self.assertIn('가축', hints['6'][0])
        snapshot['atoms'] = snapshot['atoms'][:3]
        self.assertEqual(local_context(snapshot), {})  # No end cue: do not invent an interval.

    def test_reviewed_order_survives_deterministic_compaction(self):
        from app.services.report_parent_groups import compact_report_parents
        b = fixture(); req = request_for(b, {})
        out = {'groups': [
            {'title': '학교 지침', 'summary': '지침 논의.', 'kind': 'POLICY', 'member_ids': ['G002']},
            {'title': '교육 내용', 'summary': '교육 내용 논의.', 'kind': 'POLICY', 'member_ids': ['G001']}]}
        r = project(b, req, out)
        self.assertEqual(compact_report_parents(r), r)
        self.assertEqual(r['topic_groups'][0]['topic_ids'], ['t2'])

    def test_invalid_saved_answer_keeps_original(self):
        b = fixture(); req = request_for(b, {})
        self.assertEqual(apply(b, [(900000, req, {'groups': []})], {}), b)

    def test_retained_result_is_cached_without_fabricating_groups(self):
        b = fixture(); req = request_for(b, {})
        r = apply(b, [(900000, req, {'status': 'RETAINED', 'reason': 'RETRY_LIMIT'})], {})
        self.assertEqual(r['topic_groups'], b['topic_groups'])
        self.assertEqual(r['parent_review']['status'], 'RETAINED')


class ParentWorkerTests(unittest.TestCase):
    def test_quality_handoff_is_once_and_does_not_override_budget_or_paid_cooldown(self):
        from app.ingestion.report_parent_review_worker import immediate_quality_escalation
        prior = {'error': 'PARENT_REVIEW_PARTITION', 'usage': {'billing_route': 'DAILY_FREE'}}
        self.assertTrue(immediate_quality_escalation(prior, True))
        self.assertFalse(immediate_quality_escalation(prior, False))
        self.assertFalse(immediate_quality_escalation({**prior, 'error': 'DAILY_TOKEN_LIMIT'}, True))
        self.assertFalse(immediate_quality_escalation({**prior, 'usage': {'billing_route': 'MONTHLY_CREDIT'}}, True))

    def run_worker(self, brief=None, history=None, error=None, monthly=False):
        from app.ingestion import report_parent_review_worker as worker
        from contextlib import ExitStack
        with ExitStack() as stack:
            connection = stack.enter_context(patch.object(worker, 'connect'))
            c = connection.return_value.__enter__.return_value
            c.execute.return_value.fetchone.side_effect = [(True,), ('ENDED',)]
            repo = stack.enter_context(patch.object(worker, 'TopicStructureRepository')).return_value
            repo.ready_current.return_value = brief or fixture()
            repo.snapshot.return_value = {}
            repo.batches.return_value = history or []
            stack.enter_context(patch.object(worker, 'MeetingBriefRepository')).return_value.latest.return_value = {'brief_id': 'b'}
            settings = stack.enter_context(patch.object(worker, 'get_settings')).return_value
            settings.openai_api_key = 'test'
            settings.openai_monthly_credit_fallback_enabled=monthly
            settings.openai_advanced_model='gpt-6.1-terra'
            stack.enter_context(patch.object(worker,'credit_active',return_value=monthly))
            factory = stack.enter_context(patch.object(worker, 'quota_client'))
            client = factory.return_value
            client.provider = 'openai'; client.model = 'gpt-5.4'
            client._post.return_value = (answer(), {'usage': {'total_tokens': 123}})
            if error:
                client._post.side_effect = error
            result = worker.process_one('broadcast')
            return result, repo, factory

    def test_only_main_budget_and_single_call(self):
        result, repo, factory = self.run_worker()
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(factory.call_args.args[1], 'main')
        factory.return_value._post.assert_called_once()
        self.assertEqual(repo.record.call_args.args[-1], None)

    def test_cached_review_never_calls_model(self):
        b = fixture(); b['parent_review'] = {'profile': PROFILE, 'status': 'READY'}
        result, repo, factory = self.run_worker(brief=b)
        self.assertEqual(result['status'], 'CACHED')
        factory.assert_not_called(); repo.record.assert_not_called()

    def test_budget_exhaustion_defers_and_does_not_fallback(self):
        from app.db.openai_daily_budget import DailyTokenLimitReached
        result, repo, factory = self.run_worker(error=DailyTokenLimitReached('limit'))
        self.assertEqual(result['status'], 'DEFERRED')
        self.assertIn('T00:00:00', result['retry_after'])
        factory.assert_called_once()
        self.assertEqual(repo.record.call_args.args[-1], 'DAILY_TOKEN_LIMIT')

    def test_bounded_failures_retain_original_without_more_calls(self):
        req = request_for(fixture(), {})
        history = [{'request': req, 'index': 900000, 'attempt': i, 'error': 'PARENT_REVIEW_PARTITION', 'usage': {}}
                   for i in range(1, 4)]
        result, repo, factory = self.run_worker(history=history)
        self.assertEqual(result['status'], 'RETAINED'); factory.assert_not_called()

    def test_daily_exhaustion_uses_verified_terra_monthly_credit(self):
        from app.db.openai_daily_budget import DailyTokenLimitReached
        from app.ingestion import report_parent_review_worker as worker
        # Build both clients with the real factory contract, no network requests.
        from contextlib import ExitStack
        with ExitStack() as stack:
            connection=stack.enter_context(patch.object(worker,'connect'))
            c=connection.return_value.__enter__.return_value
            c.execute.return_value.fetchone.side_effect=[(True,),('ENDED',)]
            repo=stack.enter_context(patch.object(worker,'TopicStructureRepository')).return_value
            repo.ready_current.return_value=fixture();repo.snapshot.return_value={}
            from datetime import datetime,timedelta,timezone
            req=request_for(fixture(),{})
            repo.batches.return_value=[{'request':req,'index':900000,'attempt':1,'error':'DAILY_TOKEN_LIMIT',
                'usage':{'retry_after':(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()}}]
            stack.enter_context(patch.object(worker,'MeetingBriefRepository')).return_value.latest.return_value={'brief_id':'b'}
            settings=stack.enter_context(patch.object(worker,'get_settings')).return_value
            settings.openai_api_key='fixture';settings.openai_monthly_credit_fallback_enabled=True
            settings.openai_advanced_model='gpt-6.1-terra'
            stack.enter_context(patch.object(worker,'credit_active',return_value=True))
            main=MagicMock(provider='openai',model='gpt-5.4');main._post.side_effect=DailyTokenLimitReached('daily')
            paid=MagicMock(provider='openai',model='gpt-6.1-terra');paid._post.return_value=(answer(),{'usage':{'total_tokens':100}})
            factory=stack.enter_context(patch.object(worker,'quota_client',side_effect=[main,paid]))
            result=worker.process_one('b')
            self.assertEqual(result['status'],'READY');self.assertEqual(result['usage']['billing_route'],'MONTHLY_CREDIT')
            self.assertEqual([x.args[1] for x in factory.call_args_list],['main','paid'])
            paid._post.assert_called_once();self.assertEqual(repo.record.call_args.args[-1],None)

    def test_monthly_mode_does_not_bypass_provider_cooldown(self):
        from app.db.openai_daily_budget import DailyTokenLimitReached
        result,repo,factory=self.run_worker(error=DailyTokenLimitReached('PROVIDER_COOLDOWN'),monthly=True)
        self.assertEqual(result['status'],'DEFERRED');factory.assert_called_once()

    def test_quality_failure_uses_verified_paid_model_on_next_attempt(self):
        req=request_for(fixture(),{})
        result,repo,factory=self.run_worker(monthly=True,history=[{'request':req,'index':900000,'attempt':1,
            'error':'PARENT_REVIEW_PARTITION','usage':{}}])
        self.assertEqual(result['status'],'READY');self.assertEqual(factory.call_args.args[1],'paid')

    def test_incomplete_narrative_does_not_call_model(self):
        b=fixture();b['narrative_coverage']['status']='PENDING'
        result,repo,factory=self.run_worker(brief=b)
        self.assertEqual(result['status'],'NARRATIVE_PENDING')
        factory.assert_not_called();repo.record.assert_not_called()

    def test_large_complete_report_is_not_truncated_or_silently_retained(self):
        from app.db.openai_daily_budget import DailyTokenLimitReached
        from app.services.report_parent_review import MAX_INPUT_BYTES
        b=fixture();b['topic_groups']=[];b['report_summary']['topics']=[]
        for i in range(520):
            b['topic_groups'].append({'id':f'g{i}','title':f'정책 분야 {i}','topic_ids':[f't{i}']})
            b['report_summary']['topics'].append({'id':f's{i}','source_structured_topic_id':f't{i}',
                'title':f'세부 쟁점 {i}','summary':('관계기관 간 정책 추진 현황과 개선 방안을 논의했다. '*5)+f'마지막번호{i}'})
        result,repo,factory=self.run_worker(brief=b,error=DailyTokenLimitReached('limit'))
        self.assertEqual(result['status'],'DEFERRED')
        instruction=factory.return_value._post.call_args.args[0]
        self.assertGreater(len(instruction.encode()),180_000)
        self.assertLess(len(instruction.encode()),MAX_INPUT_BYTES)
        self.assertIn('마지막번호519',instruction)
        factory.return_value._post.assert_called_once()
        b['report_summary']['topics'][0]['summary']='x'*MAX_INPUT_BYTES
        result,repo,factory=self.run_worker(brief=b)
        self.assertEqual(result['status'],'RETAINED');self.assertEqual(result['reason'],'INPUT_LIMIT')
        factory.assert_not_called()

    def test_finalization_waits_for_parent_pass(self):
        from app.ingestion.report_finalization import finish_parent_review
        with patch('app.ingestion.report_parent_review_worker.process_one', return_value={'status': 'DEFERRED'}):
            self.assertEqual(finish_parent_review('b', {'status': 'COMPLETED'})['phase'], 'FINALIZING')
        with patch('app.ingestion.report_parent_review_worker.process_one', return_value={'status': 'READY'}):
            self.assertEqual(finish_parent_review('b', {'status': 'COMPLETED'})['status'], 'COMPLETED')
        for outcome in [{'status':'RETAINED','reason':'INPUT_LIMIT'},{'status':'CACHED','reason':'RETRY_LIMIT'}]:
            with patch('app.ingestion.report_parent_review_worker.process_one',return_value=outcome):
                self.assertEqual(finish_parent_review('b',{'status':'COMPLETED'})['status'],'DEFERRED')


class ParentRequestBudgetTests(unittest.TestCase):
    def test_known_insufficient_daily_headroom_skips_input_count_endpoint(self):
        from app.services.meeting_brief import OpenAIMeetingBriefClient
        from app.db.openai_daily_budget import DailyTokenLimitReached
        error=DailyTokenLimitReached('daily');error.remaining_tokens=14000
        with patch('app.services.meeting_brief.requests.post') as post:
            client=OpenAIMeetingBriefClient('fixture',model='gpt-5.4',base_url='https://fixture.invalid',
                reserve_tokens=MagicMock(side_effect=error),settle_tokens=MagicMock())
            with self.assertRaises(DailyTokenLimitReached):client._post('대주제 및 요약',{},'meeting_parent_review')
            post.assert_not_called()

    def test_editorial_output_allowance_is_reserved_and_normal_summary_is_unchanged(self):
        from app.services.meeting_brief import OpenAIMeetingBriefClient
        import json
        for name,output,timeout in [('meeting_parent_review',20000,300.0),('assembly_summaries',8000,120.0)]:
            with self.subTest(name=name),patch('app.services.meeting_brief.requests.post') as post:
                post.return_value.status_code=200
                post.return_value.json.return_value={'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}],
                    'usage':{'prompt_tokens':10,'completion_tokens':10}}
                reserve=MagicMock(return_value='day');settle=MagicMock()
                client=OpenAIMeetingBriefClient('fixture',model='gpt-5.4',base_url='https://fixture.invalid',
                    reserve_tokens=reserve,settle_tokens=settle)
                client._post('회의 요약',{},name)
                body=post.call_args.kwargs['json'];self.assertEqual(body['max_completion_tokens'],output)
                self.assertEqual(post.call_args.kwargs['timeout'],timeout)
                estimate=len(json.dumps(body,ensure_ascii=False).encode())+output+2048
                reserve.assert_called_once_with(estimate)
                self.assertEqual(settle.call_args.args[1],estimate)


if __name__ == '__main__':
    unittest.main()
