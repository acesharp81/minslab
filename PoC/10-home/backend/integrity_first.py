"""First assessment under the explicit 50/50 rubric; old rounds are retired."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from html import escape
from sqlalchemy import select, text
from .db import IntegrityRound, Audit
from .independent_metrics import digest
from .data_integrity import INTEGRITY_WRITE_LOCK

ID='HOME-INTEGRITY-FIRST-20261022'
OFFICIAL_IDS=('O1','O2','O3','O4','O5','O6')


def calculate(previous, requirements, sources, collection, official_items, assessed_at):
    categories=deepcopy(previous['categories'])
    metric_map={'D1':'F-03','D2':'F-02','D3':'F-05','D4':'F-06','I3':'F-08'}
    for c in categories:
        for i in c['items']:
            key=i['id'];i['evidence_as_of']=previous.get('assessed_at');i['assessment_mode']='근거 유지 · 동일 기준 재채점'
            if key in ('A1','A2'):
                count=sum(s['status']=='SUCCESS' for s in sources) if key=='A1' else sum(not s.get('manual_only') for s in sources)
                i.update(numerator=count,denominator=len(sources),fraction=count/len(sources) if sources else 0)
            elif key in metric_map:
                m=requirements['metrics'][metric_map[key]]['without_estimates'];i.update(numerator=m['count'],denominator=m['total'],fraction=m['count']/m['total'] if m['total'] else 0)
            if key in ('A1','A2') or key in metric_map:
                i['assessment_mode']='현재 저장 데이터 재산출';i['evidence_as_of']=assessed_at
                i['reason']=f"현재 동일 기준 {i['numerator']:,}/{i['denominator']:,}. "+i['reason']
            i['original_weight']=i['weight'];i['weight']/=2;i['score']=i['weight']*i['fraction']
        c['weight']=sum(i['weight'] for i in c['items']);c['score']=sum(i['score'] for i in c['items'])
    official=deepcopy([i for i in official_items if i['id'] in OFFICIAL_IDS])
    if {i['id'] for i in official}!=set(OFFICIAL_IDS):raise ValueError('공식 비교 6개 지표가 모두 필요합니다')
    total_weight=sum(i['weight'] for i in official)
    for i in official:
        if i['denominator']<=0 or not 0<=i['numerator']<=i['denominator']:raise ValueError('공식 지표 분자·분모 오류')
        i['original_weight']=i['weight'];i['weight']=50*i['weight']/total_weight
        i['fraction']=i['numerator']/i['denominator'];i['score']=i['weight']*i['fraction']
    self_score=sum(c['score'] for c in categories);official_score=sum(i['score'] for i in official)
    return dict(title='1차 채점 보고서',rubric_version='FIRST-50-50-20261022',as_of_date=assessed_at[:10],assessed_at=assessed_at,
        categories=categories,official_items=official,self_score=self_score,official_score=official_score,total_score=self_score+official_score,display_score=round(self_score+official_score,2),
        official_max=50,self_max=50,collection=collection,acquisition=requirements.get('acquisition'),project_count=requirements['project_count'],
        classification_metrics=deepcopy(previous['classification_metrics']),classification_scope=previous.get('classification_scope'),
        classification_note='기존 고정 정답 20건의 분류 검증 결과입니다. 이번 공식 총계 대사나 전체 데이터 정확도를 뜻하지 않으며 50:50 점수에 가산하지 않습니다.',
        classification_input_sha256=previous.get('classification_input_sha256'),classification_cases=deepcopy(previous.get('classification_cases',[])),
        classification_evidence_as_of=previous.get('assessed_at'),
        scoring_note='공식 매핑·대조 6개 항목의 기존 상대배점 16점을 50점으로 환산하고, 자체 40개 항목 100점을 50점으로 환산합니다. 종전 공식 척도의 누적 집계 검사·판정 기록 항목(O7·O8)은 공식 점수에서 제외합니다. 미검증은 완료 점수 0이며 실적 0호나 오류 판정이 아닙니다. 다른 항목의 반복 근거가 존재하므로 독립 통계표본의 정확도로 해석하지 않습니다.',
        status_note='공식 부합은 해당 지표의 동일 범위·사건·정밀도가 확인된 경우에만 인정합니다. 4분기 명세는 정확 계획호수이므로 임의 반올림으로 차이를 상쇄하지 않습니다. 자체 정성 항목은 새 완결 근거 없이 상향하지 않았습니다.')


def markdown(r):
    f=lambda v:f'{v:,.2f}'
    lines=['# 1차 채점 보고서','',f"- 평가 시각: {r['assessed_at']}",f"- 평가 기준: {r['rubric_version']}",'',f"**종합 {f(r['total_score'])} / 100점 = 공식자료 매핑·대조 {f(r['official_score'])} / 50점 + 자체 항목 {f(r['self_score'])} / 50점**",'',r['scoring_note'],'',r['status_note'],'','## 개요 · 수집실적','']
    col=r['collection'];lines += [f"- 등록 수집 경로 {col['registered_sources']}개 · 최근 성공 {col['successful_sources']}개 · 오류 {col['failed_sources']}개",f"- API {col['api_sources']}개 · 공식 웹 {col['official_web_sources']}개 · 비공식 웹 {col['unofficial_web_sources']}개",f"- 등록 9·7 사업 {r['project_count']}건",f"- 추출 데이터 {col['extracted_cells']:,}개(행 × 컬럼) · 연결 데이터 {col['linked_records']:,}건",'','## 4대 지표 · 고정 표본','',r['classification_note'],'',f"근거 평가 시각: {r['classification_evidence_as_of']}",'','| 지표 | 값 |','|---|---:|']
    m=r['classification_metrics'];lines += [f"| {label} | {m[key]}% |" for key,label in [('accuracy','정확도'),('precision','정밀도'),('recall','재현율'),('f1','F1')]]
    lines += ['',f"TP {m['tp']} / FP {m['fp']} / FN {m['fn']} / TN {m['tn']} · 표본 {m['sample_size']}건",'','## 공식자료 매핑·대조 · 50점','', '| 항목 | 확인 / 대상 | 점수 / 배점 | 판정 근거 | 증빙 |','|---|---:|---:|---|---|']
    for i in r['official_items']:lines.append(f"| {i['id']} {i['name']} | {i.get('evaluation_summary',str(i['numerator'])+'/'+str(i['denominator']))} | {f(i['score'])}/{f(i['weight'])} | {i['reason']} | {i['evidence']} |")
    if r.get('scoring_revision'):
        lines+=['','### 모집 후보 확보 부분점수 산식','', '| 유형 | 재합산 명세 | 발표 참고값 | 참고비율 | 후보 확보 점수 | 전량 대사 점수 |','|---|---:|---:|---:|---:|---:|']
        for c in next(i for i in r['official_items'] if i['id']=='O6')['partial_components']:
            lines.append(f"| {c['name']} | {c['units']:,}호 | {c['official_units']:,}호 | {c['quantity_reference_ratio']*100:.2f}% | {f(c['score'])} / {f(c['weight']*.5)} | 0 / {f(c['weight']*.5)} |")
        lines+=['','분양·임대 각각: 배점 × 50% × min(명세호수 ÷ 발표호수, 1). 나머지 50%는 동일범위 전량 대사 미완료로 유보. 이 비율은 공식 포함률·일치율이 아니다.','',r['scoring_revision']['note']]
    lines+=['','## 자체 항목 · 50점','','| 항목 | 점수 / 배점 | 재채점 방법 | 근거 |','|---|---:|---|---|']
    for c in r['categories']:
        for i in c['items']:lines.append(f"| {i['id']} {i['name']} | {f(i['score'])}/{f(i['weight'])} | {i['assessment_mode']} | {i['reason']} |")
    lines+=['','## 해석과 남은 과제','','- 연결 대응률, 원수량 부합률, 총계 재현율은 서로 다른 지표입니다.',('- 공공분양·공공임대는 명세 확보에 부분점수를 부여했으며, 같은 범위 전량 대사는 미완료입니다. 착공 5유형 항목은 채점에서 제외했습니다.' if r.get('scoring_revision') else '- 공공분양·공공임대 모집 총계와 착공 5개 공급유형은 동일 범위 원장 재현이 완료되지 않아 완료 점수를 부여하지 않았습니다.'),'- 기존 회차는 운영 보고서 목록에서 제거했습니다. 수정 전 근거는 비공개 감사 보관본으로 보존합니다.','- 이번 작업은 채점·표출 변경이며 정책 귀속·사업 실적·공급호수 값을 변경하지 않았습니다.']
    return '\n'.join(lines)+'\n'


def html(r):
    # Standalone shareable report with clear printable score table.
    rows=lambda items:''.join('<tr><td>'+escape(i['id']+' '+i['name'])+'</td><td>'+f"{i['score']:.2f} / {i['weight']:.2f}"+'</td><td>'+escape(i['reason'])+'</td></tr>' for i in items)
    m=r['classification_metrics'];col=r['collection']
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>1차 채점 보고서</title><style>body{font:15px/1.7 sans-serif;max-width:1100px;margin:40px auto;color:#18394b;padding:24px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #dce5eb;text-align:left}h1{font-size:28px}.score{font-size:28px;color:#246f62}@media print{body{margin:0}tr{break-inside:avoid}}</style><h1>1차 채점 보고서</h1><p>'+escape(r['assessed_at'])+'</p><p class="score">'+f"종합 {r['total_score']:.2f} / 100점"+'</p><p>'+f"공식자료 매핑·대조 {r['official_score']:.2f}/50 + 자체 항목 {r['self_score']:.2f}/50"+'</p><h2>개요 · 수집실적</h2><p>'+f"API {col['api_sources']} · 공식 웹 {col['official_web_sources']} · 비공식 웹 {col['unofficial_web_sources']} · 사업 {r['project_count']}건 · 추출 {col['extracted_cells']:,}개 · 연결 {col['linked_records']:,}건"+'</p><h2>4대 지표 · 고정 표본</h2><p>'+f"정확도 {m['accuracy']}% · 정밀도 {m['precision']}% · 재현율 {m['recall']}% · F1 {m['f1']}%"+'</p><p>'+escape(r['classification_note'])+'</p><h2>채점 기준</h2><p>'+escape(r['scoring_note'])+'</p><p>'+escape(r['status_note'])+'</p><h2>공식 비교 · 50점</h2><table><tr><th>항목</th><th>점수 / 배점</th><th>근거</th></tr>'+rows(r['official_items'])+'</table><h2>자체 항목 · 50점</h2><table><tr><th>항목</th><th>점수 / 배점</th><th>근거</th></tr>'+rows([i for c in r['categories'] for i in c['items']])+'</table></html>'


def publish(service,result,expected_digests):
    items=result['official_items']+[i for c in result['categories'] for i in c['items']]
    if abs(sum(i['weight'] for i in items)-100)>1e-6 or abs(sum(i['score'] for i in items)-result['total_score'])>1e-6 or any(not 0<=i['score']<=i['weight'] for i in items):raise ValueError('배점 또는 합계 오류')
    actor='담당자 대행';reason=result.get('publication_reason','사용자 요청: 공식 매핑 50% + 자체 항목 50%로 재채점하고 기존 보고서를 1차 보고서로 교체')
    result=dict(result,report_markdown=markdown(result));report=html(result)
    checksum=digest(dict(result=result,html=report,actor=actor,reason=reason,snapshot_id=None,parent_id=None))
    archive=service.data_dir/'remediation/retired-before-first-20261022';archive.mkdir(parents=True,exist_ok=True)
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':INTEGRITY_WRITE_LOCK})
        old=db.scalars(select(IntegrityRound).with_for_update()).all()
        if {r.id:r.digest for r in old}!=expected_digests:raise ValueError('채점 준비 후 기존 회차가 변경되었습니다')
        for r in old:
            saved={c.name:getattr(r,c.name) for c in IntegrityRound.__table__.columns}
            path=archive/(r.id+'-'+r.digest+'.json');body=json.dumps(saved,ensure_ascii=False,indent=2,default=str)
            if path.exists() and path.read_text()!=body:raise ValueError('감사 보관본 충돌')
            path.write_text(body);db.delete(r)
        db.flush()
        db.add(IntegrityRound(id=ID,sequence=1,parent_id=None,actor=actor,reason=reason,snapshot_id=None,score=str(result['display_score']),result=result,report_html=report,digest=checksum))
        db.add(Audit(entity_id=ID,action='INTEGRITY_RUBRIC_RESET',before={'retired':expected_digests},after={'digest':checksum,'rubric':result['rubric_version'],'score':result['display_score'],'actor':actor,'reason':reason}))
    return dict(id=ID,digest=checksum,score=result['display_score'],retired_count=len(expected_digests))


def revise_scoring(current, evidence, assessed_at):
    """Same first report, explicit progress credit; never relabel an unmatched total."""
    r=deepcopy(current)
    if len([i for c in r['categories'] for i in c['items']])!=40:raise ValueError('자체 40개 항목이 필요합니다')
    if {i['id'] for i in r['official_items']} not in (set(OFFICIAL_IDS),set(OFFICIAL_IDS)-{'O5'}):raise ValueError('공식 지표 구성 확인 필요')
    r['official_items']=[i for i in r['official_items'] if i['id']!='O5']
    components=[]
    for key,name,target in [('sale','공공분양',14800),('rental','공공임대',14700)]:
        facts=deepcopy(evidence[key]);units=facts['units']
        if not isinstance(units,int) or units<0 or not facts.get('evidence_file') or not facts.get('sha256'):raise ValueError('재합산한 명세와 해시가 필요합니다')
        ratio=min(units/target,1)
        components.append(dict(facts,key=key,name=name,official_units=target,
            quantity_reference_ratio=units/target,acquisition_fraction=ratio,
            acquisition_weight=.5,reconciliation_weight=.5,reconciliation_fraction=0,
            fraction=.5*ratio,match_status='UNVERIFIED',difference=target-units))
    o6=next(i for i in r['official_items'] if i['id']=='O6')
    o6.update(name='1~3분기 분양·임대 모집 후보 확보 및 총계 대사',
        numerator=sum(c['fraction'] for c in components),denominator=2,
        partial_components=components,verified_at=assessed_at,
        evaluation_summary='명세 재합산 확인 · 공식 동일범위 전량 대사 미완료',
        reason='분양 24건 14,451호/공식 참고 14,800호(97.64%), 임대 18개 모집범위 4,461호/14,700호(30.35%). 유형별 동일 배점에서 후보 확보 50% × min(명세 호수/발표 호수, 1), 동일범위 전량 대사 50%는 미완료로 0점. 후보 명세의 출처·ID·수량 재합산을 인정한 내부 진척 점수이며 공식 포함률·일치율이 아니다. 임대에는 정책 귀속 미확정 공고가 포함되고 일부 공표일은 미기재다. 산술 차이 349호·10,239호를 누락량으로 확정하지 않는다.',
        evidence='A01_public_sale_partial.csv · A01_cross_source_dedup.csv · rental_partial_notices_updated.csv')
    total=sum(i['original_weight'] for i in r['official_items'])
    for i in r['official_items']:
        i['weight']=50*i['original_weight']/total
        i['fraction']=i['numerator']/i['denominator'];i['score']=i['weight']*i['fraction']
    for c in components:c['weight']=o6['weight']/2;c['score']=c['weight']*c['fraction']
    r.update(rubric_version='FIRST-50-50-20261022-REV2',assessed_at=assessed_at,
        official_score=sum(i['score'] for i in r['official_items']),
        self_score=sum(c['score'] for c in r['categories']))
    r['total_score']=r['official_score']+r['self_score'];r['display_score']=round(r['total_score'],2)
    r['scoring_revision']=dict(previous_score=current['display_score'],previous_rubric=current['rubric_version'],
        excluded_ids=['O5'],exclusion_reason='사용자 지정 평가 범위: 착공 5개 공급유형의 전체 원장 재현은 기준 설정 항목으로 채점 분모·배점에서 제외',
        original_official_weight=total,source_evidence_as_of='2026-10-21',self_evidence_as_of=current.get('assessed_at'),
        note='점수 변화는 평가범위·부분점수 기준 변경에 따른 것이며 사업 물량 추가나 공식 일치 판정 변경이 아닙니다.')
    r['scoring_note']='공식 매핑·대조 5개 항목의 상대배점 14점을 50점으로 환산하고 자체 40개 항목은 기존 50점 배점·판정을 유지합니다. 착공 5개 공급유형 원장 재현(O5)은 기준 설정 항목으로 분모와 배점에서 제외했습니다. O7·O8도 종전처럼 제외합니다. O6은 분양·임대에 동등한 배점을 주고 후보 확보 진척 50%와 동일범위 전량 대사 50%로 나눕니다. 전량 대사 미완료 상태에서는 항목 배점의 절반을 넘길 수 없습니다. 후보 호수/발표 호수는 내부 진척 평가의 참고비율이며 공식 수집률·일치율이 아닙니다.'
    r['status_note']='공식 비교의 기존 O1~O4 판정은 유지합니다. O6의 출처·명세 확보에 부분점수를 부여하되 공식 총계 대사 판정은 UNVERIFIED로 유지합니다. 자체 40개 항목도 그대로 유지합니다. 이번 상향은 평가 기준 변경이며 데이터가 새로 정확해졌다는 뜻이 아닙니다.'
    r['publication_reason']='사용자 요청: 착공 5유형 기준 항목 제외, 분양·임대 명세 확보 부분점수 적용, 자체 40항목 유지·기본 펼침'
    return r
