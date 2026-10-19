"""Build baseline + R01 HTML/JSON with unchanged rubric and item-level comments.

Run on the host after applying repairs and saving the verification inputs.
Publish the resulting round via register_integrity_rounds.py in the HOME runtime.
"""
from copy import deepcopy
from datetime import datetime
from html import escape
import hashlib
import json
import re
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_collection_midterm import render as baseline_render

FOLDER=ROOT/'data/remediation/r01'
STEM='HOME_DATA_COLLECTION_MIDTERM_20261016'
ACTOR='김민';REASON='공식 발표 후 도출된 보완 사항 적용'

# Grade changes require measured data or exercised behavior, not roadmap prose.
# Items without such evidence retain their original grade and explain the gap.
CHANGES={
 'B1':(2,'정비 885건과 광교 허가 2건을 원천 판본에 연결한 검토 명부로 등록했다. 수도권 전체의 확정 분모는 여전히 미확정이다.'),
 'B2':(None,'GH·SH·LH 상세와 iH 경로를 실제 재수집했다. 성공한 원천과 미확보 원천을 실행 근거에 구분하며 지역 전수 확보 가점은 부여하지 않았다.'),
 'B3':(2,'중계본동·흑석11·신림2의 민간정비와 광교 A17을 원천 기반 관리 후보로 노출했다. 약정·매입·전세의 실제 사건 확보는 남아 있다.'),
 'B4':(None,'법정동별 checked_at과 7일 재방문 기준을 추가했다. 조회 완료와 모집단 완결은 계속 구분한다.'),
 'C1':(None,'참고 명부도 원천 ID·고정 판본·별칭으로 추적한다. 기존 확정·해제 매핑 197건의 상태와 판본을 전후 대조하여 보존했다.'),
 'C2':(3,'887개 참고 원천을 실사업 검토 앵커로 등록하고 대표 4개 사업 후보를 관리한다. 광교의 동일 명칭·주소·600호 허가 2개는 복수 사업으로 합산하지 않고 추가 후보를 보류했다.'),
 'C3':(None,'원천→관리 후보의 HPR 대응은 추가했지만 기존 PRO 조회 경로 전체를 단일 실사업 ID로 전환하지 않아 점수를 유지했다.'),
 'C4':(None,'실제 원천 20쌍에 정답 라벨을 고정해 자동 연결 전후를 측정했다. 의도 표본으로 전체 오류율을 대신하지 않는다.'),
 'E1':(None,'직접 사건 집계에서 원천 통계·외부 발표·추정 물량을 배제하고 승인 변경·입주개시·실입주를 분리했다. 모든 기존 조회의 공통 계약 전환은 남아 있다.'),
 'E2':(None,'마곡17의 381/577호처럼 원문이 직접 특정한 사건 범위를 자동 연결할 수 있다. 계양 309/463호의 기존 담당자 확정은 보존했다.'),
 'E3':(None,'추가모집을 신규 전체 모집으로 전파하지 않는 MAIN 회차 조건을 저장 공고 소비 경로에도 적용했다. 정정·취소 계보 전체 구축은 남아 있다.'),
 'E4':(3,'정책 집계도 지도와 같은 저장된 구획별 모집 근거를 소비하도록 연결했다. 대표 운영 사례의 수치와 근거 판본을 별도 검증 결과에 보존한다.'),
 'F1':(None,'정비 전 소스·API·DB 백업과 원천 입력 SHA-256을 보존했다. 원문 해시와 새 사건·성적표 해시가 함께 추적된다.'),
 'F2':(None,'고정 집계에 원천 Revision ID와 payload hash를 기록한다. 연결 레코드의 판본을 원문 판본으로 잘못 기록하지 않는 검증을 추가했다.'),
 'F3':(None,'기존 확정·해제 197건의 상태·판본·정책·프로그램을 보존했다. 새 후보와 보완 이력에는 담당자 김민과 지정 사유를 남겼다.'),
 'F4':(3,'시간대가 있는 known_at으로 같은 날의 후속 자료도 차단한다. 반복 가능한 읽기에서 사건·선택·제외·충돌을 동결하고 이후 수집과 분리하는 검증을 통과했다.'),
 'G1':(3,'원천별 DB 잠금과 최신 탐지/과거 수집 전용 작업자를 분리했다. 공고는 원천별 15~60분 주기로 예약한다. 목표 주기와 실제 장기 SLO 달성은 구분한다.'),
 'G2':(2,'허가·대장 완료 법정동도 7일 경과 시 재방문한다. 미수집 동 확장과 오래된 완료 동을 배치에 함께 배정하고 checked_at을 기록한다. 전 범위의 재방문 실증은 남아 있다.'),
 'G3':(3,'COLLECT→LINK→SNAPSHOT의 영속 작업을 추가했다. 중복 예약 방지·임대 복구·단계별 최대 5회 재시도를 구현하고 연결 실패 후 재수집 없이 재개하는 검증을 통과했다.'),
 'G4':(1,'배치 완료·작업 완료·집계 인지시각을 보존하여 처리 구간 계측을 시작했다. 원천 공개시각이 일 단위인 자료와 1주 이상 P95·발표 선행 포착률은 미측정이다.'),
 'H1':(None,'기존 전체 Python·JavaScript 검증과 신규 인지시각·판본·중복·부분 범위·큐 재시도·회차 보존 검증을 실행했다. 테스트 통과율을 데이터 정확도로 사용하지 않았다.'),
 'H2':(None,'수집 실패와 후속 연결 실패를 다른 작업 단계로 남기고 마지막 정상 자료를 유지한다. 외부 제공 실패는 실적 0으로 변환하지 않는다.'),
 'H3':(None,'이번 조치를 별도 보완 이력과 성적표 회차로 보존했다. 구현 적용·대표 검수와 남은 실제 원천/업무 검토를 구분해 APPLIED_REVIEW_PENDING으로 기록했다.'),
 'H4':(2,'PostgreSQL 백업을 별도 임시 DB에 복원하고 50개 테이블의 행 수·확장·원천 종류별 건수를 대조했다. DB 밖 원문 보관소까지의 동시 복구 훈련은 남아 있다.'),
 'I1':(None,'계약·실입주 사건은 확인된 원천이 없으면 null과 미확보 사유로 유지한다. 입주예정·입주개시·관리 재고를 실입주 물량으로 바꾸지 않았다.'),
 'I2':(None,'원천 사건 확보를 핵심으로 재정의했다. 기관의 완성된 성과표 수입이나 기관 발표 승인을 플랫폼 산출의 선행조건으로 두지 않는다. 신규 기관 제공 계약 실증은 없다.'),
 'I3':(None,'기관 배정 목표의 승인 원천이 새로 확보되지 않아 점수를 유지했다. 외부 발표의 목표값을 내부 승인값으로 복사하지 않았다.'),
 'I4':(None,'사실 근거가 있는 신규 병목 기록을 임의 생성하지 않았다. 원천 사건과 실제 담당 조치 자료 확보가 남아 있다.'),
 'J1':(3,'등록 사업의 직접 원천 사건으로 별도 독립 지표를 산출한다. 기관 총량 통계·외부 발표·추정을 입력에서 제외하고 부분 모집단과 미확보를 명시한다.'),
 'J2':(4,'집계 기준본에 포함 사건·원천 판본·해시·범위·검토 상태와 제외·충돌 사유를 고정했다. 숫자에서 원천까지 조회하는 API를 제공한다.'),
 'J3':(3,'같은 불변 기준본에서 JSON과 사건 CSV를 반출하고 회차별 HTML 성적표를 저장·다운로드한다. 별도 발표 서식의 자동 문안 생성은 남아 있다.'),
 'J4':(2,'정비 전후 집계 기준본과 처음/1차 성적표를 부모 회차·해시로 보존한다. 발행본 덮어쓰기를 거부하고 후속 보완을 새 회차로 등록한다. 공식 총량 발표 운영의 완결을 의미하지 않는다.'),
}


def metric_html(data):
    h=escape;m=data['classification_metrics'];num=lambda v:'산정 불가' if v is None else f'{v:.2f}%'
    cards=''.join(f'<article class="kpi"><span class="label">{ko} · {en}</span><strong>{num(m[key])}</strong><p>100점 환산: {m[key]:.2f}점<br>{formula}</p></article>' for ko,en,key,formula in [
        ('정확도','Accuracy','accuracy','(TP+TN)/(TP+FP+FN+TN)'),('정밀도','Precision','precision','TP/(TP+FP)'),
        ('재현율','Recall','recall','TP/(TP+FN)'),('F1 스코어','F1 Score','f1','2TP/(2TP+FP+FN)')])
    rows=''.join(f'<tr><td>{h(c["id"])}</td><td>{h(c["name"])}<small>{h(c["source_name"])}</small></td><td>{"가능" if c["label"] else "불가"}</td><td>{"가능" if c["prediction"] else "불가"}</td><td>{h(c["label_basis"])}<small><a href="{h(c["evidence_url"],quote=True)}" target="_blank" rel="noopener">원천 ↗</a></small></td></tr>' for c in data['classification_cases'])
    return f'''<section class="section" id="classification"><span class="eyebrow">CLASSIFICATION · FIXED SOURCE SAMPLE</span><h2>정확도·정밀도·재현율·F1</h2><p>{h(data['classification_scope'])}</p><div class="kpis">{cards}</div><div class="formula"><b>정답 표본 {m['sample_size']}건</b> · TP {m['tp']} / FP {m['fp']} / FN {m['fn']} / TN {m['tn']}<p>{h(data['classification_note'])}</p><p><b>전체 플랫폼의 4대 지표: 산정 불가.</b> 대표 정답 모집단이 아직 구축되지 않았다. 위 값은 자동 연결 규칙의 목적 표본 성능이며 공식 발표 일치도와 별도다.</p><small>정답: 실제 원문 20쌍의 구획·물량·사건 의미를 대조한 개발 평가 · 담당자 독립 재검토 대기. 입력 SHA-256 {h(data['classification_input_sha256'])}</small></div><details><summary>20개 정답·예측·판정 근거 보기</summary><div class="table-wrap"><table><thead><tr><th>ID</th><th>사업 / 원천</th><th>정답</th><th>예측</th><th>라벨 근거</th></tr></thead><tbody>{rows}</tbody></table></div></details></section>'''


def render_followup(data):
    h=escape;number=lambda v:f'{v:.2f}'.rstrip('0').rstrip('.')
    categories=''
    for cat in data['categories']:
        rows=''
        for i in cat['items']:
            delta=i['score']-i['previous_score'];search=h(' '.join([i['id'],i['name'],i['change_comment']]),quote=True)
            rows+=f'''<tr data-search="{search}"><td><small>{i['id']}</small><strong>{h(i['name'])}</strong><small>배점 {i['weight']} · {h(i['method'])}</small></td><td>{number(i['previous_score'])} → <b>{number(i['score'])}</b><small>{delta:+.2f}점</small></td><td><p>{h(i['change_comment'])}</p><details><summary>현재 근거와 남은 과제</summary><p>{h(i['reason'])}</p><p>{h(i['next_step'])}</p></details></td></tr>'''
        categories+=f'<section class="section category-detail"><div class="section-title"><h3>{cat["id"]} · {h(cat["name"])}</h3><strong>{number(cat["score"])} / {cat["weight"]}</strong></div><div class="table-wrap"><table><thead><tr><th>평가 항목</th><th>이전 → 이번</th><th>항목별 개선 코멘트</th></tr></thead><tbody>{rows}</tbody></table></div></section>'
    agreement=data['agreement'];counts=data['independent_snapshot_counts']
    payload=json.dumps(data,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    evidence=''.join(f'<li><strong>{h(k)}</strong><small>{h(v["path"])}<br>SHA-256 {v["sha256"]}</small></li>' for k,v in data['round_evidence'].items())
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HOME · {data.get("sequence",1)}차 보완 성적표</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f5ef;color:#18343b;font:15px/1.8 system-ui,sans-serif;overflow-wrap:anywhere}}main{{max-width:1240px;margin:auto;padding:35px 25px 80px}}a,summary{{color:#14705e}}button,input,select{{font:inherit}}button{{padding:8px 16px;background:white;border:1px solid #ccd8d1;border-radius:6px;cursor:pointer}}.eyebrow{{font-size:12px;letter-spacing:.1em;color:#14705e;font-weight:700}}h1{{font-size:40px;line-height:1.4;margin:12px 0}}h2{{font-size:25px}}h3{{font-size:19px;margin:0}}p{{margin:8px 0 14px}}small{{display:block;font-size:12px;color:#60777c}}.hero{{display:grid;grid-template-columns:1fr 310px;gap:35px;align-items:center}}.score{{padding:30px;background:#173d43;border-radius:12px;color:white}}.score>strong{{display:block;font-size:75px;line-height:1.3}}.score small{{color:#b9d2d3}}.actions{{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}}.section{{margin-top:35px}}.kpis{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:20px 0}}.kpi,.formula,.box{{padding:22px;border:1px solid #dbe4dc;background:white;border-radius:9px}}.kpi .label{{font-size:12px;color:#60777c}}.kpi strong{{display:block;font-size:32px;color:#14705e;margin:8px 0}}.kpi p{{font-size:11px;margin:0}}.formula>p{{font-size:13px;margin-top:14px}}.box strong{{font-size:27px}}.category-detail{{background:white;border:1px solid #dbe4dc;border-radius:9px;overflow:hidden}}.section-title{{display:flex;justify-content:space-between;padding:20px;background:#fafbf8;gap:15px}}.section-title>strong{{font-size:23px;white-space:nowrap}}.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:13px;text-align:left}}th{{font-size:12px;color:#60777c;background:#fafbf8;padding:12px 18px}}td{{padding:18px;vertical-align:top;border-top:1px solid #e6ece5}}td:first-child{{min-width:185px;width:25%}}td:nth-child(2){{min-width:110px}}td strong{{display:block}}td p{{margin:0 0 10px}}summary{{cursor:pointer;font-size:13px}}.toolbar{{padding:17px;background:#e8efe8;border-radius:8px}}input{{padding:10px;border:1px solid #cbd8d0;border-radius:6px;width:min(100%,430px)}}.notice{{padding:18px 22px;background:#fff1d9;border-left:4px solid #b98134;border-radius:5px}}.evidence{{list-style:none;margin:0;padding:0}}.evidence li{{border-bottom:1px solid #e6ece5;padding:16px 0}}[hidden]{{display:none!important}}@media(max-width:850px){{.hero{{grid-template-columns:1fr}}.score>strong{{font-size:60px}}.kpis{{grid-template-columns:repeat(2,minmax(0,1fr))}}h1{{font-size:30px}}main{{padding:22px 16px}}.category-detail table{{min-width:700px}}.kpi{{padding:16px}}.kpi strong{{font-size:27px}}}}@media print{{button,.toolbar{{display:none}}.table-wrap{{overflow:visible}}main{{padding:0}}.section{{break-inside:avoid}}}}
</style></head><body><main><div class="hero"><div><span class="eyebrow">HOME · REMEDIATION ROUND {data.get("sequence",1):02}</span><h1>{h(data['title'])}</h1><p>자체 수집·검증한 데이터가 공식 발표의 근거가 되는 실시간 플랫폼을 평가한다.</p><small>평가 {h(data['assessed_at'])}<br>담당자 {ACTOR} · 사유 {REASON}<br>같은 40개 항목 · 100점 배점 유지</small></div><div class="score"><small>자체 데이터 구축 준비도</small><strong>{data['display_score']:.1f}</strong><span>/ 100점</span><p>직전 {data['previous_total_score']:.1f} → 이번 {data['display_score']:.1f}<br>{data['total_score']-data['previous_total_score']:+.2f}점</p></div></div><div class="actions"><button id="download-data">평가 JSON 저장</button><button id="print-report">인쇄 / PDF</button><a href="#items">40개 개선 코멘트 ↓</a></div><p class="notice">구현·대표 검증으로 개선된 준비도다. 수도권 전체 사건과 실제 계약·실입주 원천의 완결성은 아직 미확정이며, 발표 선행 포착률과 장기 지연 P95는 미측정이다.</p>
{metric_html(data)}
<section class="section box"><h2>공식 발표와의 전체 일치도 · 별도 지표</h2><strong>{agreement['overall_confirmed_percent']:.2f}%</strong><p>처음 대조와 같은 {agreement['confirmed_matches']}/{agreement['numeric_rows']}행의 일치 확인. 비교 대기 {agreement['pending']}행 · 수치 제외 {agreement['excluded']}행.</p><small>외부 발표 수치를 복사하거나 범위가 다른 사업 후보를 일치로 승격하지 않았다. 이번에는 원천 기반 산출 경로를 보완했으며 같은 기간·범위의 추가 확인이 없어 대조 점수는 유지했다.</small></section>
<section class="section box"><h2>독립 사건 집계의 현재 범위</h2><p>후보 사건 {counts['candidate_events']}개 · 선택 {counts['selected_events']}개 · 제외 {counts['exclusions']}개 · 충돌 {counts['conflicts']}개</p><small>집계 기준본 {h(data['snapshot_id'])}. 원천 통계·외부 발표·모델 추정을 넣지 않고 선택된 직접 사건만 합산한다. 부분 등록 모집단이므로 수도권 전수 실적으로 표시하지 않는다. 세부 사건과 판본은 관리 화면에서 JSON·CSV로 확인할 수 있다.</small></section>
<section class="section" id="items"><h2>40개 항목의 이전 점수와 개선 코멘트</h2><div class="toolbar"><input id="search" type="search" placeholder="평가 항목·개선 내용 검색" aria-label="평가 항목 검색"></div>{categories}</section>
<section class="section box"><h2>검증과 보존 근거</h2><p>Python 테스트 {data['tests']['main_tests']}개와 하위검사 {data['tests']['subtests']}개 통과 · JavaScript 테스트 {data['tests']['javascript_tests']}개 통과.</p><small>단위·회귀 테스트 통과율과 운영 데이터 정확도는 서로 다른 지표다. 원천 재수집 결과·기존 판단 보존·운영 화면 검수는 별도 근거 파일에 보존한다.</small><ul class="evidence">{evidence}</ul></section><footer class="section"><small>HOME · {h(data['round_id'])} · 이전 {h(data['parent_id'])}<br>처음 성적표의 원본은 보존하고 4대 지표를 소급 추가했다. 후속 성적표는 새 회차로 발행한다.</small></footer></main><script type="application/json" id="report-data">{payload}</script><script>document.getElementById('print-report').onclick=()=>window.print();document.getElementById('search').oninput=e=>{{const q=e.target.value.toLowerCase();document.querySelectorAll('[data-search]').forEach(r=>r.hidden=!r.dataset.search.toLowerCase().includes(q));}};document.getElementById('download-data').onclick=()=>{{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([document.getElementById('report-data').textContent],{{type:'application/json'}}));a.download='{data['round_id']}.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};</script></body></html>'''


def main():
    for suffix in ('json','html'):
        source=ROOT/'docs'/f'{STEM}.{suffix}';saved=FOLDER/f'baseline.original.{suffix}'
        if not saved.exists():saved.write_bytes(source.read_bytes())
    baseline=json.loads((FOLDER/'baseline.original.json').read_text())
    evaluation=json.loads((FOLDER/'matching-evaluation.json').read_text())
    for data,version in [(baseline,'before')]:
        data.update(classification_metrics=evaluation[version],classification_scope=evaluation['scope'],classification_note=evaluation['note'],
                    classification_input_sha256=evaluation['source_input_sha256'],classification_cases=[dict(c,prediction=c[version+'_prediction']) for c in evaluation['cases']],
                    round_id='HOME-INTEGRITY-R00',parent_id=None,assessment_addendum='4대 지표를 변경 전 코드의 같은 입력 소급 실행으로 추가 · 원래 준비도 점수 및 대조 판정은 보존')
    first_html=baseline_render(baseline).replace('<section class="section" id="agreement">',metric_html(baseline)+'<section class="section" id="agreement">')
    (ROOT/'docs'/f'{STEM}.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'docs'/f'{STEM}.html').write_text(first_html)
    after=deepcopy(baseline);remediation=json.loads((FOLDER/'remediation-result.json').read_text())
    requirements=json.loads((FOLDER/'requirements-after.json').read_text())
    sources=json.loads((FOLDER/'sources-after.json').read_text())['items']
    after.update(title='HOME 1차 보완 성적표',round_id='HOME-INTEGRITY-R01',parent_id='HOME-INTEGRITY-R00',
                 previous_total_score=baseline['total_score'],assessed_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
                 actor=ACTOR,reason=REASON,snapshot_id=remediation['after_snapshot_id'],independent_snapshot_counts=remediation['after_counts'],
                 classification_metrics=evaluation['after'],classification_cases=[dict(c,prediction=c['after_prediction']) for c in evaluation['cases']],
                 scoring_version='HOME-COLLECTION-MIDTERM-1-R01',round_evidence={})
    ratio_map={'D1':'F-03','D2':'F-02','D3':'F-05','D4':'F-06','I3':'F-08'}
    for cat in after['categories']:
        for i in cat['items']:
            i['previous_score']=i['score'];i['previous_reason']=i['reason']
            level,comment=CHANGES.get(i['id'],(None,'기존 수집·정형화 기반을 유지했다. 이 항목의 범위를 넓히는 추가 확보·운영 증거가 없어 같은 기준으로 점수를 유지했다.'))
            if i['id'] in ('A1','A2'):
                count=sum(s['status']=='SUCCESS' for s in sources) if i['id']=='A1' else sum(not s.get('manual_only',False) for s in sources)
                i.update(numerator=count,denominator=len(sources));i['fraction']=count/len(sources)
                comment=f'최종 원천 상태를 재계산했다: {count}/{len(sources)}. 최근 단일 상태 또는 자동 순회 대상 비율이며 장기 성공률·전수 확보율은 아니다.'
            elif i['id'] in ratio_map:
                metric=requirements['metrics'][ratio_map[i['id']]]['without_estimates']
                i.update(numerator=metric['count'],denominator=metric['total'])
                i['fraction']=metric['count']/metric['total'] if metric['total'] else 0
                comment=f"정비 후 비추정 근거를 같은 기준으로 재계산했다: {metric['count']}/{metric['total']}. " + (comment if i['id'] in CHANGES else '원천 확보 비율을 코드 구현 가점으로 대체하지 않았다.')
            elif level is not None:
                i['level']=level;i['fraction']=level/4
            i['score']=i['weight']*i['fraction'];i['score_delta']=i['score']-i['previous_score']
            i['change_comment']=comment;i['reason']=comment
            i['next_step']=i['next_step']+' 코드 적용과 실제 원천 전수 확보는 별도 완료 조건으로 점검한다.'
        cat['score']=sum(i['score'] for i in cat['items'])
    after['total_score']=sum(c['score'] for c in after['categories']);after['display_score']=round(after['total_score'],1)
    for group in after['groups']:
        group['score']=sum(c['score'] for c in after['categories'] if c['group']==group['id']);group['percent']=group['score']/group['weight']*100
    suites=ET.parse(FOLDER/'regression.xml').getroot();tests=sum(int(s.get('tests',0)) for s in suites.findall('testsuite'))
    assert not any(int(s.get('failures',0)) or int(s.get('errors',0)) for s in suites.findall('testsuite'))
    main_tests=len(suites.findall('.//testcase'))
    tap=(FOLDER/'javascript-tests.tap').read_text()
    js_tests=int(re.search(r'^# tests (\d+)$',tap,re.M)[1]);js_failures=int(re.search(r'^# fail (\d+)$',tap,re.M)[1])
    assert js_failures==0
    after['tests']=dict(main_tests=main_tests,subtests=tests-main_tests,javascript_tests=js_tests,status='PASS',note='전체 Python 테스트 및 JS 회귀검증')
    files=['baseline.original.json','baseline.original.html','matching-evaluation.json','matching-input-before.json','remediation-result.json','requirements-after.json','quality-after.json','snapshot-after.json','sources-after.json','regression.xml','javascript-tests.tap','live-collection.json','operational-verification.json']
    for name in files:
        path=FOLDER/name
        if not path.exists():raise ValueError('회차 발행 전 검증 근거 필요: '+name)
        after['round_evidence'][name]=dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
    output=ROOT/'docs/HOME_DATA_INTEGRITY_R01_20261017'
    output.with_suffix('.json').write_text(json.dumps(after,ensure_ascii=False,indent=2)+'\n')
    output.with_suffix('.html').write_text(render_followup(after))
    for name,content in [('baseline.json',json.dumps(baseline,ensure_ascii=False)),('baseline.html',first_html),('round.json',json.dumps(after,ensure_ascii=False)),('round.html',render_followup(after))]:
        (FOLDER/name).write_text(content)
    print(json.dumps(dict(before=baseline['display_score'],after=after['display_score'],delta=after['total_score']-baseline['total_score'],output=str(output.with_suffix('.html'))),ensure_ascii=False))


if __name__=='__main__':main()
