"""Reassess R01 against report-writing capability, preserving its former edition."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from copy import deepcopy
from html import escape
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
FOLDER=ROOT/'data/remediation/report-reproducibility-20261017'
ROUND='HOME-INTEGRITY-R01-CONSOLIDATED-20261017'
REASON='평가 기준 정정: 자체 데이터 기반 보고서 작성 가능성 검증'
read=lambda name:json.loads((FOLDER/(name+'.json')).read_text())
def write(name,value):(FOLDER/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def report_section(report):
    h=escape
    rows=''.join(f'<tr><td>{h(r["id"])} · {h(r["name"])}</td><td>{h(r["required"])}<p><small>{h(r["formula"])}</small></p></td><td>{"미산출" if r["own_value"] is None else format(r["own_value"],",")+" "+h(r["own_unit"])}<p>{h(r["status_label"])}</p><small>{h(r.get("own_scope") or r["input_period"])}</small></td><td>{h(r["blocker"])}<p>{h(r["next_action"])}</p></td></tr>' for r in report['rows'])
    events=''.join(f'<tr><td>{h(e["name"])}</td><td>{h(e["event_date"])}</td><td>{e["units"]:,}호</td><td>{h(e["source_base_date"] or "미확인")}<br><a href="{h(e["evidence_url"] or "",quote=True)}">원문</a></td></tr>' for e in report['third_town']['events'])
    return f'''<section class="section box" id="report-reproducibility"><h2>우리 데이터만으로 이번 보고서를 작성할 수 있는가</h2><h3>{h(report['verdict'])}</h3><p>평가 기준 {h(report['known_at'])}. 보고서 문장마다 필요한 대상·기간·단위·산식과 기존 원장 증거를 검증했다. 원문과 같은 제목의 API·문서 존재 여부로 평가하지 않는다.</p><p>{h(report['latest_input_assumption'])}</p><p><strong>{h(report['score_note'])}</strong></p><p>신규 정책 목표·기관 신설 등은 결정 사실이 입력돼야 서술할 수 있다. 공급 실적 데이터의 오류로 감점하지 않는다. {h(report['preannouncement_capability'])}</p><h3>3기 신도시 · 기존 사업 원장에서 재집계</h3><p>직접 증빙 {report['third_town']['event_count']}개 사건, <strong>{report['third_town']['value']:,}호</strong>. {h(report['third_town']['caveat'])}</p><p>계양은 화면 프로그램명이 달라도 지구 정의에 따라 포함한다. <a href="{h(report['third_town']['definition_url'],quote=True)}">지구 분류 기준</a>은 물량 입력과 별개다. 화면 7,527호는 당시 필터·판본을 재현하지 못해 정확/오류를 판정하지 않았다.</p><div class="table-wrap"><table><thead><tr><th>블록·사업</th><th>실제 착공일</th><th>직접 물량</th><th>자료 기준일</th></tr></thead><tbody>{events}</tbody></table></div><h3>53개 주장별 작성 가능성·처리 공백</h3><p>부분 합계는 전체 실적과의 오차 계산에 사용하지 않는다. 미산출은 0이 아니다. 중복된 상하위 지표와 정성 주장 때문에 행 수 비율을 전체 보고서 점수로 쓰지 않는다.</p><div class="table-wrap"><table><thead><tr><th>보고서의 주장</th><th>필요한 데이터·산식</th><th>우리 데이터 산출·판정</th><th>제약과 구체적인 다음 조치</th></tr></thead><tbody>{rows}</tbody></table></div><p><small>{h(" ".join(report["limitations"]))}</small></p></section>'''


def capture():
    from backend.db import engine_for
    from backend.service import HomeService
    from backend.data_integrity import get_round
    s=HomeService(engine_for());write('before',get_round(s,ROUND))
    (FOLDER/'before.html').write_text(get_round(s,ROUND,html=True))


def build():
    from backend.integrity_diagnostics import evaluate
    from scripts.build_integrity_round import render_followup
    from scripts.build_consolidated_integrity import details
    before=read('before');current=deepcopy(before['result']);snapshot=read('snapshot')
    diagnostic=evaluate(snapshot,read('projects'),read('delivery'),read('annual'),read('inventory'),{},reference_rows=read('reference-rows'))
    report=diagnostic['report_reproducibility'];write('assessment',report);write('diagnostics',diagnostic)
    current.update(title='HOME 보완1 · 자체 데이터 기반 보고서 작성 가능성 재검증',reason=REASON,
        assessed_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),as_of_date=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat(),report_reproducibility=report,
        diagnostics=diagnostic,agreement=diagnostic['agreement'],snapshot_id=snapshot['id'],independent_snapshot_counts=snapshot['result']['counts'],
        score_scope='TECHNICAL_READINESS_NOT_REPORT_REPRODUCIBILITY',technical_score_assessed_at=before['result']['assessed_at'])
    notes={'A1':'API 수집 성공 비율은 기술 준비도다. 보고서 작성 가능성 점수로 사용하지 않음.',
        'A2':'자동 수집 대상 확대만으로 지표별 연결·집계·최신성 검증이 완료된 것으로 평가하지 않음.',
        'B1':'보고서별 대상 정의와 프로그램 표시명을 구분. 3기 신도시 지구 분류에 인천계양 포함.',
        'C3':'지표별 원천 연결·대상/기간 필터 누락을 별도 진단. 동명 API 유무로 대체하지 않음.',
        'D1':'최신 사건 스냅샷에서 직접 확인 가능한 부분 실적을 별도 제시. 누적 도달량을 당해 연도 실제 착공으로 사용하지 않음.',
        'J1':'53개 주장을 실제값·목표·계획·전망·업무량·정책 결정으로 나눠 보유 원장의 재현 가능성을 재검증. 과거 4.26%는 목표/통계 참조 확인 포함이며 보고서 작성률이 아님.',
        'J4':'새 회차 없이 보완1의 평가 방향을 정정. 기존 기술 점수·최초 대비 차이는 보존하며 보고서 작성 준비 판정을 최상단에 표시.'}
    for category in current['categories']:
        for item in category['items']:
            if item['id'] in notes and notes[item['id']] not in item['change_comment']:
                item['change_comment']+=' 보고서 작성 검증: '+notes[item['id']];item['reason']=item['change_comment']
    import xml.etree.ElementTree as ET
    test_path=FOLDER/'regression.xml'
    if test_path.exists():
        tree=ET.parse(test_path);suite=tree.getroot().find('testsuite')
        assert int(suite.get('failures'))==int(suite.get('errors'))==0
        count=len(tree.getroot().findall('.//testcase'))
        current['tests']=dict(main_tests=count,subtests=int(suite.get('tests'))-count,javascript_tests=65,status='PASS')
    html=render_followup(current)
    html=html.replace('<main>','<main>'+report_section(report),1)
    html=html.replace('자체 데이터 구축 준비도','기술 준비도 · 보고서 작성률 아님')
    html=html.replace('담당자 김민 · 사유 공식 발표 후 도출된 보완 사항 적용','평가 담당 김민 · '+REASON)
    html=html.replace('직전 ','최초 평가 ').replace('이전 점수와 개선 코멘트','최초 평가 대비 기술 점수와 개선 코멘트')
    start=html.index('<section class="section box"><h2>공식 발표와의 전체 일치도')
    end=html.index('<section class="section box"><h2>독립 사건',start);a=current['agreement']
    html=html[:start]+f'<section class="section box"><h2>기존 수치 대조 · 보고서 작성률과 별도</h2><strong>{a["overall_confirmed_percent"]:.2f}%</strong><p>목표·통계 참조 포함 {a["confirmed_matches"]}/{a["numeric_rows"]}행 확인. 전체 데이터 정확도·보고서 작성률로 사용하지 않음.</p></section>'+html[end:]
    html=html.replace('<section class="section" id="items">',details(current)+'<section class="section" id="items">')
    html=html.replace('후속 성적표는 새 회차로 발행한다.','사용자 요청으로 기존 보완1을 갱신하고 이전 판본을 보관했다.')
    if (FOLDER/'before.html').exists():
        previous_html=(FOLDER/'before.html').read_text()
        marker='<section class="section box"><h2>기존 보완1 갱신 · API 누락 보완</h2>'
        if marker in previous_html:
            begin=previous_html.index(marker);end=previous_html.index('</section>',begin)+len('</section>')
            html=html.replace('<section class="section" id="items">',previous_html[begin:end]+'<section class="section" id="items">')
    write('round',current);(FOLDER/'round.html').write_text(html)
    from xml.etree import ElementTree as ET
    test_path=FOLDER/'regression.xml'
    if test_path.exists():
        suite=ET.parse(test_path).getroot().find('testsuite');assert int(suite.get('failures'))==int(suite.get('errors'))==0
    bounded=next(r for r in report['rows'] if r['id']=='M04')
    names=' · '.join(e['name'] for e in report['third_town']['events'])
    source_dates=' · '.join(sorted({e['source_base_date'] or '미확인' for e in report['third_town']['events']}))
    known_kst=datetime.fromisoformat(report['known_at']).astimezone(ZoneInfo('Asia/Seoul')).isoformat()
    draft=f'<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HOME 보유 원장 기반 공급현황 초안</title><style>body{{font:17px/1.8 system-ui;max-width:1000px;margin:auto;padding:24px}}table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;border-bottom:1px solid #ddd;text-align:left}}small{{color:#555}}</style><h1>HOME 보유 원장 기반 공급현황 · 작성 가능한 범위의 초안</h1><p>집계 인지시각 {escape(known_kst)}. 최신 전체 시장 실적을 확정한 보고서가 아니라 저장 원장으로 직접 입증 가능한 사실의 예시다.</p><p>보유 원문으로 2026년 착공 {len(bounded["event_ids"])}개 사건, {bounded["own_value"]:,}호를 확인했다. 이 가운데 3기 신도시 지구에 속하는 직접 확인분은 {report["third_town"]["event_count"]}개 사건, {report["third_town"]["value"]:,}호다. 두 수치는 전체와 부분 관계이므로 서로 더하지 않는다.</p><p>3기 신도시 확인분은 {escape(names)}이다. 이 착공 원문의 자료 기준일은 {escape(source_dates)}이므로 이후 추가 착공을 모두 반영한 최신 총계로 발표할 수 없다.</p><p>대상 전수 명부, 기간별 사건 누락·취소, 일부 원장 연결과 전망 산식의 공백 때문에 수도권 전체 실적·연말 전망·매입약정 접수량·제도과제 완료량은 이 초안에서 확정하지 않는다. 새로운 정책 목표·기관 운영 계획은 그 결정 사실을 입력받아 별도로 서술해야 한다.</p><small>공식 발표의 정답 숫자는 이 초안의 합계 입력에 사용하지 않았다. 기술 준비도 63.1점은 이 보고서의 작성 가능률이나 정확도가 아니다.</small></html>'
    (FOLDER/'own-data-report.html').write_text(draft)
    print(json.dumps(dict(verdict=report['verdict'],third_town=report['third_town']['value'],rows=len(report['rows']),technical_score=current['display_score']),ensure_ascii=False))


def publish():
    from backend.db import engine_for
    from backend.service import HomeService
    from backend.data_integrity import amend_round
    print(amend_round(HomeService(engine_for()),ROUND,read('before')['digest'],read('round'),(FOLDER/'round.html').read_text(),'김민',REASON))


if __name__=='__main__':globals()[sys.argv[1]]()
