"""Refresh the user-requested existing R02, preserving its predecessor and archive."""
import argparse
from copy import deepcopy
from datetime import date, datetime
from zoneinfo import ZoneInfo
from html import escape
import hashlib
import json
from pathlib import Path
from backend.db import engine_for
from backend.service import HomeService
from backend.data_integrity import get_round, amend_round, rounds
from backend.policy_delivery import build_delivery
from backend.independent_metrics import freeze
from scripts.build_continuation_review_20261020 import metrics
from scripts.complete_collection_review_20261020 import slim, IDS
from scripts.review_policy_readmission_20261019 import protected, digest

ID='HOME-INTEGRITY-R02-20261020'
REASON='사용자 요청: 현재 수집·공식자료 대조·전처리 설명을 반영해 기존 보완2 갱신'

def save(folder,name,data):
    (folder/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str)+'\n')

def capture(s,w):
    before=protected(s)
    model=build_delivery(s,date(2026,10,20),include_portfolio_comparisons=False)
    save(w,'model.json',model)
    snap=freeze(s,'담당자 대행',REASON)
    save(w,'independent.json',snap)
    ids=[pid for c in model['portfolio_cohorts'] for pid in c['source_ids']]
    assert len(ids)==len(set(ids)), '관리 묶음 내 중복 기여'
    after=protected(s);assert before==after, '평가 중 보호 원장 변경'
    save(w,'current-validation.json',dict(assessed_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        metrics=metrics(model),portfolio_cohorts=len(model['portfolio_cohorts']),
        contributing_source_ids=len(ids),unique_source_ids=len(set(ids)),
        scopes={sid:slim(s.latest_collection_stats(sid)) for sid in IDS},
        protected_records=len(before),protected_hash=digest(before),protected_unchanged=True,
        snapshot_id=snap['id'],independent_counts=snap['result']['counts']))
    print('Current source scope, cumulative quantities and immutable event snapshot captured.')

def build(s,w):
    read=lambda name:json.loads((w/name).read_text())
    old=read('round-before.json');r=deepcopy(old['result']);v=read('current-validation.json')
    q=read('requirements.json');sources=read('sources.json')['items']
    parent=get_round(s,old['parent_id'])['result'];prior={i['id']:i for c in parent['categories'] for i in c['items']}
    historical=s.data_dir/'presentation-final-20261020'
    comparison=json.loads((historical/'comparison.json').read_text())
    review=json.loads((historical/'policy-review-applied.json').read_text())
    model=read('model.json');cohorts={c['id']:c for c in model['portfolio_cohorts']}
    for row in comparison['rows']:
        if row['cohort_id']:
            assert cohorts[row['cohort_id']]['units']==row['project_units'], '공식 비교표 물량 재검토 필요'
    summary={k:value for k,value in comparison['summary'].items() if k!='cohort_source_ids'}
    summary['matched_weight_percent']=round(100*summary['matched_official_units']/summary['official_units'],2)
    summary['note']='10월 공식 첨부 32개 항목의 사업 대응 비중. 수량·일정 정확도나 전체 공개자료 수집률이 아님.'
    success=sum(x['status']=='SUCCESS' for x in sources);auto=sum(not x.get('manual_only',False) for x in sources)
    mapping={'D1':'F-03','D2':'F-02','D3':'F-05','D4':'F-06','I3':'F-08'}
    comments={
        'A3':'현행 API 조회 범위를 재확인. 일반 건축인허가 잔여 범위는 미조회로 유지하며 완료로 간주하지 않음.',
        'A4':'수집·전처리 설명을 실제 도구와 범위로 정리: PDF pypdf 문자 추출·자료별 파싱, API 응답 필드 추출. 문구 정비로 정형화 등급을 높이지 않음.',
        'B1':'공식 첨부 32개 항목과 전체 정책 사업 모집단을 구분. 전체 사업 전수 명부 미확보 상태 유지.',
        'B4':'현재 API 조회 완료·잔여 범위와 76개 원천의 수집 주기·자동/수동·신규/변경 탐색 범위를 설명. 화면 설명 개선만으로 조회 완료 점수를 올리지 않음.',
        'C1':'공식 비교표의 별칭 누락을 교정하고 현재 관리 묶음의 물량과 재대조. 기존 원천에 있던 평택고덕 3개 블록 2,122호를 비교 근거에 반영.',
        'C2':'공식 정책 근거 19개 사업 12,579호는 기존 연결 재확인으로 추가 집계 0호. 지구 계획 2건 3,655호는 개별 사업 중복범위 미확정으로 별도 근거 보관.',
        'C4':f"현재 관리 묶음 {v['portfolio_cohorts']}개, 기여 원천 ID {v['contributing_source_ids']}개 중 중복 {v['contributing_source_ids']-v['unique_source_ids']}개. 모든 실제 현장 동일성의 전수 검증을 의미하지 않음.",
        'E1':'평가 API에서 COMPLETION 근거를 건설 셀에 배치하고 준공 milestone을 보존하도록 수정. 입주 실적으로 바꾸지 않으며 추정 제외 지표를 다시 계산.',
        'E2':'검단 AA19 국민임대 991호와 영구임대 332호를 1,323호로 구분 합산한 근거 유지. 지구 단위 약수 발표와 블록 합계를 무조건 일치로 판단하지 않음.',
        'F3':'기존 보완2 수정 전 JSON·HTML·해시를 보관하고 같은 회차를 갱신. 프로젝트·정책 매핑·승인 일정 원장은 수정하지 않음.',
        'G1':'자동 수집 주기를 작업 큐 설정과 대조하고 지정 문서 재확인과 신규 목록 탐색을 구분해 표시. 장기 정시 성공률 실증과는 구분.',
        'H1':'준공 근거가 있어도 평가 API가 정상 작동하며 준공을 입주로 오인하지 않는 회귀검증 추가. 수집 메타데이터·사업별 수집·성적표 보존 관련 54개 테스트 및 하위검사 2개 통과.',
        'H3':'현재 입력과 재산정 근거를 고정. UI 표현 정비, API 오류 수정, 기존 공식자료 대조 결과를 구분해 기록.',
        'J1':f"누적 착공 {v['metrics']['CONSTRUCTION']['actual']:,}호, 연말 계획 {v['metrics']['CONSTRUCTION']['year_end']:,}호. 정부 연간 착공 총계와 동일 모집단으로 가정하지 않음.",
        'J3':'32개 공식 항목 비교 CSV·발표용 MD·원문 및 검증 근거 묶음을 확보. 수량·일정·사업 대응 여부를 나눠 설명.',
        'J4':'사용자 요청으로 새 회차 없이 보완2를 갱신하고 수정 전 발행본과 감사 기록 보존. 1차 대비 평가 기준·배점 유지.'}
    deltas=[]
    for c in r['categories']:
        for item in c['items']:
            key=item['id'];oldscore=item['score'];item['previous_score']=prior[key]['score'];item['previous_reason']=prior[key]['reason']
            comment=comments.get(key,'현재 점검 범위에서 등급 변경의 추가 근거가 없어 기존 평가 유지. '+item.get('next_step',''))
            if key in ('A1','A2'):
                count=success if key=='A1' else auto;total=len(sources)
                item.update(numerator=count,denominator=total,fraction=count/total)
                comment=f'현재 동일 기준 재산정: {count}/{total}. '+('최근 수집 시도 성공 상태 비율이며 장기 성공률이 아님.' if key=='A1' else '자동 순회 대상으로 설정된 비율이며 실제 정시 성공률이 아님. 업무 대상 등록·규칙 작성·정책 연결 판단은 이 지표의 수동 수집으로 세지 않음.')
            elif key in mapping:
                m=q['metrics'][mapping[key]]['without_estimates'];item.update(numerator=m['count'],denominator=m['total'],fraction=m['count']/m['total'] if m['total'] else 0)
                comment=f"추정 제외·같은 정의로 재산정: {m['count']}/{m['total']}. {m['note']} 준공 근거 조회 오류를 수정한 현재 입력 기준."
            item.update(score=item['weight']*item['fraction'],reason=comment,change_comment=comment)
            item.update(score_delta=item['score']-item['previous_score'],amendment_previous_score=oldscore,amendment_score_delta=item['score']-oldscore)
            if abs(item['score']-oldscore)>1e-9:deltas.append(dict(id=key,name=item['name'],before=oldscore,after=item['score'],delta=item['score']-oldscore))
        c['score']=sum(i['score'] for i in c['items'])
    total=sum(c['score'] for c in r['categories'])
    r.update(total_score=total,display_score=round(total,1),previous_total_score=parent['total_score'],assessed_at=v['assessed_at'],generated_at=v['assessed_at'],actor='담당자 대행',reason=REASON,
        snapshot_id=v['snapshot_id'],independent_snapshot_counts=v['independent_counts'],
        title='2차 보완 성적표 · 현재 수집·공식자료 대조 갱신',tests=dict(passed=54,subtests=2,note='현재 실행한 관련 회귀검증. 데이터 전체 정확도를 의미하지 않음.'))
    for g in r['groups']:
        g['score']=sum(c['score'] for c in r['categories'] if c['group']==g['id']);g['percent']=100*g['score']/g['weight']
    r['current_reassessment']=dict(v,previous_score=old['result']['display_score'],previous_total_score=old['result']['total_score'],previous_digest=old['digest'],source_count=len(sources),successful_sources=success,automatic_sources=auto,
        official=summary,policy_review={k:value for k,value in review.items() if k!='results'},score_changes=deltas,
        note='수집·전처리 설명 정비 자체에는 가점 없음. 4대 분류 지표와 이전 53개 주장 확인율은 기존 고정 표본 결과로 유지.')
    r['round_evidence'].update({name:dict(path=str((w/name).relative_to(s.data_dir)),sha256=hashlib.sha256((w/name).read_bytes()).hexdigest()) for name in ('sources.json','requirements.json','current-validation.json','independent.json')})
    text=['# HOME 2차 보완 성적표 · 현재 기준 갱신','',f"평가 시각: {v['assessed_at']}",'',f"**기존 보완2 {old['result']['display_score']:.1f} → {r['display_score']:.1f} / 100점**. 40개 항목·100점 배점과 1차 대비 비교 기준을 유지했습니다. 수정 전 원본·해시는 별도 보관합니다.",'','이 점수는 기술·데이터 구축 준비도입니다. 전체 데이터 정확도나 공식 발표 총량 일치율이 아닙니다.','','## 최신 확인 결과','',f"- 등록 출처 {len(sources)}개 · 최근 성공 상태 {success}개 · 자동 순회 대상 {auto}개.",f"- 누적 착공 {v['metrics']['CONSTRUCTION']['actual']:,}호 · 연말 계획 {v['metrics']['CONSTRUCTION']['year_end']:,}호.",f"- 관리 묶음 {v['portfolio_cohorts']}개 · 기여 원천 ID 중복 {v['contributing_source_ids']-v['unique_source_ids']}개.",f"- 공식 첨부 {summary['official_rows']}개·{summary['official_units']:,}호 중 사업 대응 {summary['matched_rows']}개·{summary['matched_official_units']:,}호({summary['matched_weight_percent']}%). {summary['note']}",f"- 동일 관리 물량 {summary['matched_quantity_rows']}개·{summary['matched_quantity_units']:,}호. 전체 사업 대응과 수량 일치를 구분합니다.",'- 명시적 정책 근거 19개·12,579호는 기존 연결을 재확인했으며 중복 가산하지 않았습니다.','- 정책 세부 귀속 유보 9개·6,296호는 기존 검토 결과를 유지합니다.','- 준공 근거 조회 오류를 수정했습니다. 수집·전처리 설명에서 업무 연결 판단을 분리했습니다. 관련 테스트 54개·하위검사 2개 통과.','','## API 조회 범위','', '| 원천 | 완료 / 전체 법정동 | 미조회 |','| --- | ---: | ---: |']
    text += [f"| {sid} | {x.get('scope_completed_dongs')} / {x.get('scope_total_dongs')} | {x.get('scope_remaining_dongs')} |" for sid,x in v['scopes'].items()]
    text += ['','조회 범위 완결과 전체 사업 확보는 구분합니다. 일반 건축인허가 미조회 범위는 자료 미공개로 치환하지 않습니다.','','## 항목별 재평가','', '| 항목 | 갱신 전 → 후 / 배점 | 근거 |','| --- | ---: | --- |']
    text += [f"| {i['id']} {i['name']} | {i['amendment_previous_score']:.3f} → {i['score']:.3f} / {i['weight']} | {i['change_comment']} |" for c in r['categories'] for i in c['items']]
    md='\n'.join(text)+'\n';r['report_markdown']=md
    rows=''.join(f"<tr><td>{escape(i['id']+' '+i['name'])}</td><td>{i['amendment_previous_score']:.3f} → {i['score']:.3f} / {i['weight']}</td><td>{escape(i['change_comment'])}</td></tr>" for c in r['categories'] for i in c['items'])
    html='<!doctype html><html lang="ko"><meta charset="utf-8"><title>2차 보완 갱신 성적표</title><style>body{font:15px/1.7 sans-serif;max-width:1100px;margin:32px auto;padding:16px}td,th{border:1px solid #ccd;padding:10px}table{border-collapse:collapse;width:100%}pre{white-space:pre-wrap}</style><h1>2차 보완 성적표 · 현재 기준 갱신</h1><pre>'+escape('\n'.join(text[:text.index('## 항목별 재평가')]))+'</pre><table><tr><th>항목</th><th>갱신 전 → 후 / 배점</th><th>근거</th></tr>'+rows+'</table></html>'
    save(w,'round.json',r);(w/'report.md').write_text(md);(w/'report.html').write_text(html)
    print(json.dumps(dict(before=old['result']['display_score'],after=r['display_score'],changes=deltas,metrics=v['metrics']),ensure_ascii=False))

def publish(s,w):
    old=json.loads((w/'round-before.json').read_text());r=json.loads((w/'round.json').read_text())
    original={x['id']:x['digest'] for x in rounds(s)['items']};before=protected(s)
    amend_round(s,ID,old['digest'],r,(w/'report.html').read_text(),'담당자 대행',REASON)
    after={x['id']:x['digest'] for x in rounds(s)['items']}
    assert original.keys()==after.keys() and all(after[k]==v for k,v in original.items() if k!=ID)
    assert protected(s)==before
    final=get_round(s,ID);save(w,'published.json',dict(id=ID,score=final['result']['display_score'],digest=final['digest'],round_count=len(after),other_rounds_unchanged=True,protected_unchanged=True))
    print((w/'published.json').read_text())

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['capture','build','publish']);a=p.parse_args()
    s=HomeService(engine_for());w=s.data_dir/'remediation/r02-current-20261020';w.mkdir(parents=True,exist_ok=True)
    globals()[a.action](s,w)
