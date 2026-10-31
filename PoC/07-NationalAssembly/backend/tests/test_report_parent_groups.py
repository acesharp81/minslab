from copy import deepcopy

import pytest

from app.services.report_parent_groups import compact_report_parents
from app.services.report_presentation import narrative_projection
from app.services.structured_narrative import inputs


def fixture():
    titles = ['미래대응기금 재원 배분과 경기대응 여력', '미래 대응 기금의 국회 재정통제와 차입수권',
              '미래대응기금과 예산총계주의', '반도체 호황 초과세수 활용과 미래기금 재정운용 논란',
              '반도체 경기 변동과 재정 대응', '반도체 호황기 재정운용과 국가채무 관리',
              '국가채무 수준 전망', '장기재정전망에 따른 재정준칙', '지방소멸대응기금 운용',
              '미래투자기금 여유자금', '청주 반도체 공장 인허가']
    topics = [{'id': f't{i}', 'title': title, 'summary': f'쟁점 요약 {i}',
               'evidence_ids': [f'e{i}'], 'speaker_points': [{'id': f'p{i}', 'summary': f'발언 요약 {i}',
                   'role': 'QUESTION', 'evidence_ids': [f'e{i}'],
                   'evidence_span': {'evidence_id': f'e{i}', 'start': 0, 'end': 7, 'quote': f'근거 발언 {i}'}}]}
              for i, title in enumerate(titles)]
    return {'topics': topics, 'topic_groups': [
        {'id': f'g{i}', 'title': title, 'topic_ids': [f't{i}'], 'evidence_ids': [f'e{i}']}
        for i, title in enumerate(titles)], 'tasks': [
        {'id': 'task', 'summary': '기금 배분 기준 제출', 'topic_id': 't0', 'evidence_ids': ['e0']}],
        'topic_structure': {'parent_count': len(titles), 'issue_count': len(titles)}}


def test_same_policy_parents_merge_without_losing_issues_tasks_evidence_or_cached_summaries():
    brief = fixture()
    before = deepcopy(brief)
    fingerprints = inputs(brief)
    result = compact_report_parents(brief)
    assert brief == before
    assert result['topics'] == before['topics']
    assert result['tasks'] == before['tasks']
    assert inputs(result) == fingerprints
    assert sorted(t for g in result['topic_groups'] for t in g['topic_ids']) == sorted(t['id'] for t in brief['topics'])
    fund = next(g for g in result['topic_groups'] if g['title'] == '미래대응기금')
    assert fund['topic_ids'] == ['t0', 't1', 't2', 't3']
    assert fund['evidence_ids'] == ['e0', 'e1', 'e2', 'e3']
    assert fund['source_groups'] == before['topic_groups'][:4]
    assert result['topic_structure']['parent_count'] == 6
    assert compact_report_parents(result) == result


@pytest.mark.parametrize('title', ['지방소멸대응기금', '미래투자기금', '기후대응기금과 미래대응기금',
                                 '미래대응기금과 기후대응기금', '미래기금', '기금 운용'])
def test_distinct_or_ambiguous_funds_are_not_assumed_to_be_the_same_policy(title):
    brief = {'topic_groups': [{'id': 'a', 'title': title, 'topic_ids': ['a']},
                             {'id': 'b', 'title': '미래대응기금과 예산총계주의', 'topic_ids': ['b']} ]}
    # A shorthand alone is accepted only in a report naming the full fund.
    if title == '미래기금':
        brief['topic_groups'][1]['title'] = '미래투자기금 운용'
    assert compact_report_parents(brief) == brief


def test_incidental_mentions_in_quotes_do_not_move_another_topic():
    brief = fixture()
    brief['topics'][-1]['speaker_points'][0]['summary'] = '미래대응기금도 언급했다.'
    result = compact_report_parents(brief)
    assert next(g for g in result['topic_groups'] if g['title'] == '청주 반도체 공장 인허가')['topic_ids'] == ['t10']


def test_narrative_and_print_projection_keep_all_summaries_and_task_links():
    brief = fixture()
    narrative = {k: deepcopy(brief[k]) for k in ('topics', 'topic_groups')}
    for topic in narrative['topics']:
        topic['source_structured_topic_id'] = topic['id']
    brief['report_summary'] = narrative
    projected = narrative_projection(brief)
    assert len(projected['topic_groups']) == 6
    assert [(t['id'], t['summary'], t['speaker_points'][0]['summary']) for t in projected['topics']] == [
        (t['id'], t['summary'], t['speaker_points'][0]['summary']) for t in narrative['topics']]
    assert projected['topics'][0]['task_ids'] == ['task']
    assert brief['report_summary'] == narrative


def test_materialize_applies_parent_projection_without_rekeying_children():
    from app.services.topic_structure import build_snapshot, validate_response, materialize, digest
    titles = ['미래대응기금의 재원 배분', '미래대응기금의 국회 통제']
    brief = {'topics': [{'id': f't{i}', 'title': title, 'evidence_ids': [f'u{i}']}
                        for i, title in enumerate(titles)], 'tasks': []}
    item = {'brief_id': 'b', 'transcript_hash': 'hash', 'brief': brief}
    snapshot = build_snapshot(item, [{'utterance_id': f'u{i}', 'text': title + '에 관하여 질의합니다.',
        'content_hash': f'h{i}', 'revision_ids': [f'r{i}'], 'segment_ids': [f's{i}']}
        for i, title in enumerate(titles)])
    data = {'assignments': [{'atom_id': atom['id'], 'facets': [
        {'parent': titles[i], 'issue': titles[i], 'role': 'QUESTION', 'span_index': 0}]}
        for i, atom in enumerate(snapshot['atoms'])]}
    result = materialize(brief, snapshot, validate_response(data, snapshot['atoms']), [], 'revision')
    assert len(result['topic_groups']) == 1
    assert result['topic_groups'][0]['id'].startswith('structured-')
    assert result['topic_groups'][0]['title'] == '미래대응기금'
    assert [t['id'] for t in result['topics']] == ['structured-topic-' + digest([title, title])[:16] for title in titles]
    assert [t['speaker_points'][0]['evidence_span']['parent'] for t in result['topics']] == titles


def test_real_compact_and_partition_requests_share_one_parent_vocabulary():
    import json
    from app.services import compact_consolidation as compact, partitioned_consolidation as partitioned
    from app.services.report_parent_groups import policy_parent_catalogue
    from app.services.topic_structure import consolidation_input, apply_consolidation
    facets = [{'parent': title, 'issue': issue, 'role': 'QUESTION', 'quote': issue}
              for title, issue in [
                  ('미래대응기금의 국회 통제', '국회의 사전 의결권 보장'),
                  ('미래대응기금의 재원 배분', '초과세수 적립 한도와 배분 원칙'),
                  ('지방소멸대응기금의 지역 배분', '지역별 인구감소 지원')]]
    items = consolidation_input(facets)
    titles = policy_parent_catalogue(items)
    assert titles == ['미래대응기금', '지방소멸대응기금의 지역 배분']
    compact_enum = compact.schema(items)['properties']['groups']['items']['properties']['parent']['enum']
    assert compact_enum == titles
    assignments = {}
    for indices in ([0], [1, 2]):
        contract = partitioned.schema(items, indices)
        assert contract['$defs']['policy_parent']['enum'] == titles
        for n in indices:
            assert contract['properties']['assignments']['properties'][str(n)]['properties']['parent'] == {'$ref': '#/$defs/policy_parent'}
        assert json.dumps(titles, ensure_ascii=False, separators=(',', ':')) in partitioned.prompt(items, indices)
        raw = {'assignments': {str(n): {'parent': titles[0] if n < 2 else titles[1], 'canonical': n} for n in indices}}
        assignments.update(partitioned.normalize(items, indices, raw)['assignments'])
    result = apply_consolidation(facets, {'assignments': assignments})
    assert len({f['parent'] for f in result}) == 2
    assert [f['issue'] for f in result] == [f['issue'] for f in facets]
    assert [f['quote'] for f in result] == [f['quote'] for f in facets]
    assert compact.normalize(items, {'groups': [{'parent': titles[0], 'issue_groups': [[0], [1]]},
        {'parent': titles[1], 'issue_groups': [[2]]}]})['assignments'] == assignments


def test_serious_crime_agency_aliases_share_parent_not_unrelated_cases():
    source={'topic_groups':[{'id':str(i),'title':t,'topic_ids':[str(i)]} for i,t in enumerate([
        '중대범죄수사청 조직·인력·장비 자료 제출 요구','중수청 수사 독립성과 정치적 중립성',
        '중대범죄수사청장 인사 및 기관증인 출석','공소청 보완수사','부천 화재 지휘체계',
        '부천 화재 재발 방지','대전 화재 대응','중수청과 공소청의 수사·기소 분리'])]}
    result=compact_report_parents(source)
    group=next(g for g in result['topic_groups'] if g['title']=='중대범죄수사청(중수청)')
    assert group['topic_ids']==['0','1','2']
    assert len(result['topic_groups'])==5
    assert sorted(t for g in result['topic_groups'] for t in g['topic_ids'])==[str(i) for i in range(8)]
