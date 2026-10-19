"""User-requested update of existing R01; basic collection and link audit are separate."""
import argparse
from copy import deepcopy
from datetime import datetime
from html import escape
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
ROUND='HOME-INTEGRITY-R01-CONSOLIDATED-20261017'
FOLDER=ROOT/'data/remediation/general-api-score-update-20261017'
ACTOR='김민'
LINK_REASON='담당자 확인(자동연결)'


def write(name,value):
    FOLDER.mkdir(parents=True,exist_ok=True)
    (FOLDER/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def capture():
    from sqlalchemy import select
    from backend.db import engine_for,Revision,Audit,entity_id,upsert_revision,now
    from backend.service import HomeService,today
    from backend.data_integrity import get_round
    s=HomeService(engine_for())
    before=get_round(s,ROUND);write('before.json',before)
    activation=json.loads((ROOT/'data/remediation/zero-households-20261017/general-api-activation.json').read_text())
    with s.sessions.begin() as db:
        old=db.scalar(select(Revision).where(Revision.entity_id==entity_id('collection_repair','repair_log','general-building-permit-connector-20261017'),Revision.superseded_at.is_(None)))
        if old:
            old.superseded_at=now()
            db.add(Audit(entity_id=old.entity_id,action='COLLECTION_REPAIR_RECLASSIFIED',before=old.payload,
                after=dict(classification='BASE_COLLECTION',reason='사용자 정정: 누락 원천 수집은 기본 데이터 적재. 연결 확인만 담당자 이력으로 분리.')))
        payload=dict(source_id='building_general_permit',title='일반 건축인허가 API 연결 확인',
            actor=ACTOR,reason=LINK_REASON,status='CONNECTED',base_date=today().isoformat(),
            evidence_url='https://www.data.go.kr/data/15136267/openapi.do',
            evidence_batch_ids=[b['id'] for b in activation['batches']],
            scope='API 원천 연결 확인. 사업별 매칭·사건 확정을 뜻하지 않음.')
        record,outcome=upsert_revision(db,'source_connection','building_general_permit','api-connection',payload,'connection_confirmation')
        if outcome!='unchanged':db.add(Audit(entity_id=record.entity_id,action='SOURCE_CONNECTION_CONFIRMED',before={},after=payload))
        connection=dict(id=record.entity_id,revision_no=record.revision_no,**payload)
    write('connection.json',connection)
    # Keep initial evidence intact; the corrected classification is explicit here.
    activation=deepcopy(activation)
    for key in ('actor','reason','repair'):activation.pop(key,None)
    activation.update(record_scope='BASE_COLLECTION',connection_confirmation=connection)
    write('activation.json',activation)
    write('sources.json',s.sources(compact=True))
    print(json.dumps(dict(round_id=ROUND,connection=connection['id'],records=activation['records']),ensure_ascii=False))


def build():
    from scripts.build_integrity_round import render_followup
    from scripts.build_consolidated_integrity import details
    before=json.loads((FOLDER/'before.json').read_text());current=deepcopy(before['result'])
    sources=json.loads((FOLDER/'sources.json').read_text());activation=json.loads((FOLDER/'activation.json').read_text())
    source=next(s for s in sources if s['id']=='building_general_permit')
    assert source['status']=='SUCCESS' and source['record_count']==activation['records']
    old_items={i['id']:deepcopy(i) for c in current['categories'] for i in c['items']}
    success=sum(s['status']=='SUCCESS' for s in sources);automatic=sum(not s.get('manual_only') for s in sources)
    ratio_before_api=(automatic-1)/(len(sources)-1)
    comments={
        'A1':f"일반 건축인허가 API 누락 보완: 활용신청·인증 확인 후 {activation['records']:,}건 실제 적재. 최근 성공 원천 {success}/{len(sources)}로 재평가. API 추가에 따른 이 항목 상승 {3*(success/len(sources)-old_items['A1']['fraction']):+.6f}점. 원장 건수는 공급실적이 아니며 전체 지역 수집 완료 가점은 없음.",
        'A2':f"일반 건축인허가를 자동 수집에 연결하고 첫 자동 배치 성공 확인. 현재 자동 대상 {automatic}/{len(sources)}. 이번 API 추가만의 효과 {3*(automatic/len(sources)-ratio_before_api):+.6f}점이며, 기존 원천 자동 전환의 미반영분 {3*(ratio_before_api-old_items['A2']['fraction']):+.6f}점도 구분해 반영. 설정 비율이며 장기 정시 성공률이 아님.",
        'A3':'일반 건축인허가의 각 법정동 전체 페이지·총건수·관리키 중복 검증을 실제 실행했다. 다른 전체 원천의 전수 검증은 남아 있어 등급 유지.',
        'A4':'누락된 일반 건축인허가 API를 기본 수집에 추가했다. hhldCnt·hoCnt·fmlyCnt와 실제·예정 착공일을 구분해 저장하며 형식 정형화 등급은 유지.',
        'B2':f"일반 건축인허가 {activation['completed_dongs']}/{activation['total_dongs']}개 법정동 조회. 서울 일부만 실제 확보했으므로 수도권 전수 확보 가점 없음.",
        'B4':'일반 건축인허가 법정동별 예상/수신 건수·페이지·조회시각과 잔여 범위를 보존했다. 원천 전수 커버리지 미완료로 등급 유지.',
        'C2':'일반 건축인허가는 기본 원장에 적재했으며 검증된 신규 사업 연결은 아직 없어 사업 후보 승격 점수 유지.',
        'F3':'기본 수집은 배치·원문 로그로 보존하고 연결 확인만 김민 / 담당자 확인(자동연결)로 기록. 잘못 분류한 수집 보완 이력은 현재 목록에서 제외하고 정정 감사 보존.',
        'J1':'이번 API 확보만으로 공식 발표와 동일 범위의 일치를 확정하지 않음. 공식 발표 확인율과 목적 표본 4대 지표는 종전 검증 결과로 유지.',
        'J4':'사용자 요청으로 새 회차 없이 기존 보완1을 갱신. 수정 전 원본·해시와 변경 감사 보존, 최초 평가 대비 비교 유지.'}
    for category in current['categories']:
        for item in category['items']:
            key=item['id']
            if key in ('A1','A2'):
                count=success if key=='A1' else automatic
                item.update(numerator=count,denominator=len(sources),fraction=count/len(sources))
                item['score']=item['weight']*item['fraction']
            if key in comments:
                item['change_comment']+=' 이번 API 누락 보완 점검: '+comments[key]
                item['reason']=item['change_comment']
            item['score_delta']=item['score']-item['previous_score']
            item['amendment_previous_score']=old_items[key]['score']
            item['amendment_score_delta']=item['score']-old_items[key]['score']
        category['score']=sum(i['score'] for i in category['items'])
    current['total_score']=sum(c['score'] for c in current['categories']);current['display_score']=round(current['total_score'],1)
    for group in current['groups']:
        group['score']=sum(c['score'] for c in current['categories'] if c['group']==group['id']);group['percent']=group['score']/group['weight']*100
    current['assessed_at']=datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    current['title']='HOME 보완 1차 성적표 · 일반 건축인허가 API 누락 보완 반영'
    current['reason']='기존 보완1 갱신: 일반 건축인허가 API 누락 보완 및 항목별 점수·코멘트 반영'
    comment='일반 건축인허가 API 누락을 보완하여 기본 원장 수집을 시작했다. A1·A2의 관측 비율만 재계산했고 다른 등급·정확도·공식 발표 일치도는 추가 검증 없이 올리지 않았다.'
    current['api_collection_update']=dict(comment=comment,previous_total_score=before['result']['total_score'],
        previous_digest=before['digest'],records=activation['records'],completed_dongs=activation['completed_dongs'],total_dongs=activation['total_dongs'],
        source_evidence='data/remediation/general-api-score-update-20261017/activation.json',
        baseline_comparison_preserved=True,scope='SOURCE_COLLECTION_ONLY',
        retained_metric_assessed_at=before['result']['assessed_at'],connection_actor=ACTOR,connection_reason=LINK_REASON)
    for path in current['additional_collection_paths']:
        if path['name']=='건축HUB 일반 건축인허가':path.update(status='기본 수집 적용 · 전 지역 확대 중',result=f"{activation['records']:,}건 실제 적재, 법정동 {activation['completed_dongs']}/{activation['total_dongs']}개. 연결 확인 김민 / {LINK_REASON}. 신규 공급실적으로 자동 합산하지 않음.")
    import xml.etree.ElementTree as ET
    suite=ET.parse(FOLDER/'regression.xml').getroot().find('testsuite')
    assert int(suite.get('failures'))==int(suite.get('errors'))==0
    main_tests=len(ET.parse(FOLDER/'regression.xml').getroot().findall('.//testcase'))
    current['tests']=dict(main_tests=main_tests,subtests=int(suite.get('tests'))-main_tests,javascript_tests=65,status='PASS')
    html=render_followup(current)
    html=html.replace('담당자 김민 · 사유 공식 발표 후 도출된 보완 사항 적용','평가 담당 김민 · 누락 API 기본 수집 반영 / 연결 확인 사유 담당자 확인(자동연결)')
    html=html.replace('직전 ','최초 평가 ').replace('이전 점수와 개선 코멘트','최초 평가 대비 점수와 개선 코멘트')
    start=html.index('<section class="section box"><h2>공식 발표와의 전체 일치도')
    end=html.index('<section class="section box"><h2>독립 사건',start)
    a=current['agreement']
    html=html[:start]+f'<section class="section box"><h2>공식 발표와의 전체 확인율 · 별도 지표</h2><strong>{a["overall_confirmed_percent"]:.2f}%</strong><p>최초 {current["baseline_agreement_percent"]:.2f}% → 이번 {a["overall_confirmed_percent"]:.2f}% · {a["confirmed_matches"]}/{a["numeric_rows"]}행 확인 · 비교 대기 {a["pending"]}행</p><small>{escape(a["definition_change"])} 이번 API 수집으로는 변경하지 않음.</small></section>'+html[end:]
    table=''.join(f'<tr><td>{i["id"]} {escape(i["name"])}</td><td>{i["amendment_previous_score"]:.6f} → {i["score"]:.6f}</td><td>{i["amendment_score_delta"]:+.6f}</td><td>{escape(comments[i["id"]])}</td></tr>' for c in current['categories'] for i in c['items'] if i['id'] in ('A1','A2'))
    section=f'<section class="section box"><h2>기존 보완1 갱신 · API 누락 보완</h2><p>{escape(comment)}</p><p>갱신 전 {before["result"]["total_score"]:.6f} → 갱신 후 {current["total_score"]:.6f}점. 최초 평가 대비 기준은 유지.</p><p>기본 데이터 {activation["records"]:,}건 수집. 연결 확인: 김민 / {LINK_REASON}. 수집 자체를 담당자 보완 이력으로 기록하지 않음.</p><table><thead><tr><th>항목</th><th>갱신 전후 점수</th><th>차이</th><th>상승 사유</th></tr></thead><tbody>{table}</tbody></table><small>공식 발표 일치도와 4대 지표는 {escape(before["result"]["assessed_at"])} 검증 결과 유지. 이번 추가 원장의 연결 정확도는 미평가.</small></section>'
    html=html.replace('<section class="section" id="items">',section+details(current)+'<section class="section" id="items">')
    html=html.replace('후속 성적표는 새 회차로 발행한다.','이번 갱신은 사용자 요청에 따라 보완1 안에서 수정하고 이전 발행본을 보관했다.')
    write('round.json',current);(FOLDER/'round.html').write_text(html)
    print(json.dumps(dict(before=before['result']['total_score'],after=current['total_score'],display=current['display_score']),ensure_ascii=False))


def publish():
    from backend.db import engine_for
    from backend.service import HomeService
    from backend.data_integrity import amend_round
    before=json.loads((FOLDER/'before.json').read_text());current=json.loads((FOLDER/'round.json').read_text())
    identity=amend_round(HomeService(engine_for()),ROUND,before['digest'],current,(FOLDER/'round.html').read_text(),ACTOR,
        '기존 보완1 갱신: 일반 건축인허가 API 누락 보완 및 항목별 점수·코멘트 반영')
    print(identity)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['capture','build','publish']);args=parser.parse_args()
    globals()[args.action]()
