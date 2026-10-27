from copy import deepcopy

import pytest

from app.services.structured_narrative import PROFILE, inputs, validate, apply, schema, valid_subset, pending_batches
from app.services.report_presentation import narrative_projection


def fixture():
    topics = [{'id': f't{i}', 'title': title, 'speaker_points': [
        {'id': f'p{i}', 'role': 'REQUEST', 'evidence_span': {
            'quote': quote, 'evidence_id': f'u{i}'}}]}
        for i, (title, quote) in enumerate([
            ('독립몰수제 협력', '독립몰수제 시행에 맞춰 관계기관 협력 방안을 마련해 주시기 바랍니다.'),
            ('서민 경제범죄 대응', '전세사기 피해자들을 보호하기 위해서 기관들이 함께 대응해야 하지 않겠습니까?')])]
    brief = {'topics': topics, 'topic_structure': {'revision_id': 'r'},
             'topic_groups': [{'id': 'g', 'title': '공소청 업무보고', 'topic_ids': ['t0', 't1']}],
             'tasks': [{'id': 'task', 'title': '협력 방안 마련', 'related_topic_ids': ['t0']}],
             'report_summary': {'topics': [{'id': 'old', 'title': '업무보고', 'summary': '기존 요약'}]}}
    rows = {
        't0': {'summary': '독립몰수제 운영을 위한 기관 간 협력 방안 마련이 요구됐다.',
               'points': [{'summary': '시행 준비 과정에서 관계기관 협력 체계를 정비해 달라는 요청이다.',
                           'source_point_ids': ['p0']}]},
        't1': {'summary': '전세사기 피해자를 보호하기 위한 기관 공동 대응 필요성이 제기됐다.',
               'points': [{'summary': '피해자 보호를 위해 유관기관이 함께 대응할 필요가 있다는 질의다.',
                           'source_point_ids': ['p1']}]}}
    return brief, inputs(brief), rows


def test_every_issue_and_source_retained_in_summary_hierarchy():
    brief, items, rows = fixture()
    original = deepcopy(brief)
    result = apply(brief, [(400000, {'profile': PROFILE, 'issues': items}, rows)])
    summary = narrative_projection(result)
    assert summary['coverage']['status'] == 'COMPLETE'
    assert len(summary['topics']) == 2
    assert len(summary['topic_groups'][0]['topic_ids']) == 2
    assert summary['topic_groups'][0]['title'] == '공소청 업무보고'
    assert summary['topics'][0]['task_ids'] == ['task']
    assert summary['topics'][1]['task_ids'] == []
    assert summary['topics'][0]['speaker_points'][0]['evidence_ids'] == ['u0']
    for field in ('topics', 'topic_groups', 'tasks'):
        assert result[field] == original[field]


def test_partial_or_stale_summaries_do_not_replace_previous_report():
    brief, items, rows = fixture()
    original = deepcopy(brief['report_summary'])
    history = [(400000, {'profile': PROFILE, 'issues': items[:1]}, {'t0': rows['t0']})]
    result = apply(brief, history)
    assert result['report_summary'] == original
    assert result['narrative_coverage']['summarized_issue_count'] == 1
    brief['topics'][0]['speaker_points'][0]['evidence_span']['quote'] += ' 추가 발언입니다.'
    assert apply(brief, history)['narrative_coverage']['summarized_issue_count'] == 0


def test_existing_task_without_issue_link_keeps_its_summary_and_source():
    brief, items, rows = fixture()
    brief['report_summary']['topics'][0].update(source_topic_id='source-old', evidence_ids=['u0'])
    brief['tasks'].append({'id': 'unlinked', 'title': '기존 요구', 'source_topic_id': 'source-old'})
    result = narrative_projection(apply(brief, [(400000, {'profile': PROFILE, 'issues': items}, rows)]))
    assert {i for t in result['topics'] for i in t['task_ids']} == {'task', 'unlinked'}
    retained = next(t for t in result['topics'] if t['id'] == 'old')
    assert retained['summary'] == '기존 요약'
    assert retained['evidence_ids'] == ['u0']
    assert result['topic_groups'][-1]['title'] == '추가 요구 과제'


@pytest.mark.parametrize('fault', ['missing_issue', 'missing_source', 'unknown_source', 'quote', 'title', 'foreign'])
def test_reject_incomplete_or_unsummarized_response(fault):
    brief, items, rows = fixture()
    if fault == 'missing_issue':
        rows.pop('t1')
    elif fault == 'missing_source':
        items[0]['points'].append({'id': 'p2', 'role': 'ANSWER', 'quote': '추가 답변', 'evidence_id': 'u2'})
    elif fault == 'unknown_source':
        rows['t0']['points'][0]['source_point_ids'] = ['unknown']
    elif fault == 'quote':
        rows['t0']['summary'] = items[0]['points'][0]['quote']
    elif fault == 'foreign':
        rows['t0']['summary'] += ' 国民들의 politics 문제가 있다.'
    else:
        rows['t0']['summary'] = items[0]['title']
    with pytest.raises(ValueError):
        validate(items, rows)


def test_corrupt_saved_response_is_ignored_not_exposed_as_complete():
    brief, items, rows = fixture()
    rows['t0']['points'][0]['source_point_ids'] = ['unknown']
    result = apply(brief, [(400000, {'profile': PROFILE, 'issues': items}, rows)])
    assert result['narrative_coverage']['status'] == 'PENDING'
    assert result['report_summary']['topics'][0]['id'] == 'old'


def test_full_atom_context_is_included_and_changes_invalidate_summary():
    brief, _, rows = fixture()
    brief['topics'][0]['speaker_points'][0]['evidence_span']['atom_id'] = 'a'
    snapshot = {'atoms': [{'id': 'a', 'text': '업무 보고 앞부분. 뒤에서 독립몰수제 협력을 설명합니다.'}]}
    items = inputs(brief, snapshot)
    assert items[0]['contexts'][0]['text'] == snapshot['atoms'][0]['text']
    history = [(400000, {'profile': PROFILE, 'issues': items}, rows)]
    assert apply(deepcopy(brief), history, snapshot)['narrative_coverage']['status'] == 'COMPLETE'
    snapshot['atoms'][0]['text'] += ' 추가 조건.'
    assert apply(deepcopy(brief), history, snapshot)['narrative_coverage']['status'] == 'PENDING'


def test_constrained_point_map_requires_every_source_and_projects_to_cards():
    brief, items, rows = fixture()
    for row in rows.values():
        row['points'] = {p['source_point_ids'][0]: p['summary'] for p in row['points']}
    assert schema(items)['properties']['t0']['properties']['points']['required'] == ['p0']
    assert validate(items, rows)['t0']['points'][0]['source_point_ids'] == ['p0']
    result = apply(brief, [(400000, {'profile': PROFILE, 'issues': items}, rows)])
    assert result['report_summary']['topics'][0]['speaker_points'][0]['evidence_ids'] == ['u0']


@pytest.mark.parametrize('claim', ['2024년 10월 2일 출범했다.', '정원을 7000명 줄였다.'])
def test_reject_invented_years_and_numbers(claim):
    _, items, rows = fixture()
    items[0]['contexts'] = [{'atom_id': 'a', 'text': '10월 2일 출범했다. 정원을 700명 줄였다.'}]
    rows['t0']['summary'] += claim
    with pytest.raises(ValueError, match='NARRATIVE_UNSUPPORTED_NUMBER'):
        validate(items, rows)


def test_reject_recombined_date_even_if_individual_numbers_exist():
    _, items, rows = fixture()
    items[0]['contexts'] = [{'atom_id': 'a', 'text': '2025년 11월 출범 후 2026년 9월 실적을 보고했다.'}]
    rows['t0']['summary'] += '2025년 9월에 출범했다.'
    with pytest.raises(ValueError, match='NARRATIVE_UNSUPPORTED_DATE'):
        validate(items, rows)


def test_salvage_keeps_only_fully_valid_issues_and_failed_batch_is_split():
    _, items, rows = fixture()
    rows['t1']['points'][0]['source_point_ids'] = ['invented']
    assert valid_subset(items, rows) == items[:1]
    history = [{'status': 'FAILED', 'error': 'NARRATIVE_POINT_COVERAGE', 'attempt': 1,
                'request': {'profile': PROFILE, 'schema_revision': 2, 'validation_revision': 2, 'issues': items}}]
    batches, blocked = pending_batches(items[1:], history)
    assert not blocked and len(batches) == 1 and batches[0]['issues'] == items[1:]


def test_single_issue_corrective_round_is_bounded_without_blocking_other_issues():
    _, items, rows = fixture()
    request = {'profile': PROFILE, 'schema_revision': 2, 'validation_revision': 2, 'issues': items[:1]}
    history = [{'status': 'FAILED', 'error': 'NARRATIVE_UNSUPPORTED_NUMBER', 'attempt': i,
                'request': deepcopy(request)} for i in range(1,4)]
    batches, blocked = pending_batches(items, history)
    corrective = next(r for r in batches if r.get('repair_round'))
    assert corrective['issues'] == items[:1] and not blocked
    history.extend({'status': 'FAILED', 'error': 'NARRATIVE_UNSUPPORTED_NUMBER', 'attempt': i,
                    'request': deepcopy(corrective)} for i in range(1,4))
    batches, blocked = pending_batches(items, history)
    assert blocked == ['t0'] and len(batches) == 1 and batches[0]['issues'] == items[1:]


def test_capacity_error_cannot_hide_semantic_failure_and_delay_correction():
    _, items, _ = fixture()
    request = {'profile':PROFILE,'schema_revision':2,'validation_revision':2,'issues':items[:1]}
    history = [{'status':'FAILED','error':error,'attempt':i+1,'request':deepcopy(request)}
               for i,error in enumerate(['NARRATIVE_UNSUPPORTED_NUMBER','AUXILIARY_DAILY_LIMIT','AUXILIARY_INPUT_TOO_LARGE'])]
    batches, blocked = pending_batches(items[:1],history)
    assert not blocked and batches[0]['repair_round'] == 1


def test_cooling_request_does_not_block_later_runnable_issue():
    from datetime import datetime, timezone
    _, items, _ = fixture()
    request = {'profile':PROFILE,'schema_revision':2,'validation_revision':2,'issues':items[:1]}
    history = [{'status':'FAILED','error':'ReadTimeout','attempt':i+1,
                'created_at':datetime.now(timezone.utc),'request':deepcopy(request)} for i in range(3)]
    batches, blocked = pending_batches(items,history)
    assert batches[0]['issues']==items[1:] and not blocked


def test_corrective_feedback_keeps_full_context_and_original_number_format():
    from app.services.structured_narrative import corrective_prompt
    _,items,_=fixture()
    items[0]['contexts']=[{'atom_id':'a','text':'25년 예산 2000만 원, 스물다섯 번, 금요일까지 자료 제출'}]
    text=corrective_prompt(items[:1])
    assert items[0]['contexts'][0]['text'] in text
    assert '"2000"' in text and '"25"' in text
    assert '수량·기한·약속을 임의로 없애지 않는다' in text


def test_rejected_numeric_answer_gets_one_stable_diagnostic_round():
    from app.services.structured_narrative import corrective_prompt
    _, items, _ = fixture()
    item = items[0]
    item['contexts'] = [{'atom_id': 'a', 'text': '스물여덟 가지 평가항목과 55.78점의 평가 결과'}]
    request = {'profile': PROFILE, 'schema_revision': 2, 'validation_revision': 2, 'issues': [item]}
    bad = {item['id']: {'summary': '28가지 항목에 대해 55점대로 평가했다고 설명했다.', 'points': {}}}
    history = []
    for repair in (0, 1):
        req = deepcopy(request)
        if repair:
            req['repair_round'] = repair
        history.extend({'status': 'FAILED', 'error': 'NARRATIVE_UNSUPPORTED_NUMBER', 'attempt': n,
                        'request': deepcopy(req), 'response': deepcopy(bad)} for n in range(1, 4))
    batches, blocked = pending_batches([item], history)
    assert not blocked and len(batches) == 1
    diagnostic = batches[0]
    assert diagnostic['repair_round'] == 2
    feedback = diagnostic['validation_feedback']
    assert feedback[item['id']]['unsupported_numbers'] == ['28', '55']
    text = corrective_prompt([item], feedback)
    assert '스물여덟 가지' in text and '55.78점' in text and '거절된 응답은 사실 근거가 아니며' in text
    assert item['contexts'][0]['text'] in text
    history.append({'status': 'FAILED', 'error': 'NARRATIVE_UNSUPPORTED_NUMBER', 'attempt': 1,
                    'index': 400002, 'request': deepcopy(diagnostic), 'response': deepcopy(bad)})
    assert pending_batches([item], history)[0] == [diagnostic]
    history.extend({'status': 'FAILED', 'error': 'NARRATIVE_UNSUPPORTED_NUMBER', 'attempt': n,
                    'index': 400002, 'request': deepcopy(diagnostic), 'response': deepcopy(bad)} for n in (2, 3))
    field_batches, blocked = pending_batches([item], history)
    assert not blocked and field_batches[0]['repair_round'] == 3
    assert field_batches[0]['field_repair']['fields'] == ['__summary__']
    history.extend({'status': 'FAILED', 'error': 'NARRATIVE_UNSUPPORTED_NUMBER', 'attempt': n,
                    'index': 400003, 'request': deepcopy(field_batches[0]), 'response': deepcopy(bad)} for n in (1, 2, 3))
    assert pending_batches([item], history) == ([], [item['id']])


def test_field_repair_keeps_unaffected_summaries_and_requires_exact_fields():
    from app.services.structured_narrative import merge_field_repair
    plan = {'issue_id': 'issue', 'fields': ['bad'],
            'base': {'summary': '원래 쟁점 요약', 'points': {'good': '보존할 요약', 'bad': '55점대'}}}
    result = merge_field_repair(plan, {'bad': '평가 결과가 55.78점이라고 설명했다.'})
    assert result['issue']['summary'] == '원래 쟁점 요약'
    assert result['issue']['points']['good'] == '보존할 요약'
    assert plan['base']['points']['bad'] == '55점대'
    with pytest.raises(ValueError, match='FIELD_REPAIR_COVERAGE'):
        merge_field_repair(plan, {'good': '다른 요약'})
