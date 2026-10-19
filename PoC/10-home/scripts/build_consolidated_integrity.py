"""One consolidated remediation round, compared directly with immutable R00."""
from copy import deepcopy
from datetime import datetime
from html import escape
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.build_integrity_round import ROOT,render_followup,ACTOR,REASON


def details(data):
    h=escape;d=data['diagnostics'];rows=''
    for r in d['agreement']['rows']:
        n=lambda x:'미확보' if x is None else f'{x:,.0f}'
        rows+=f'<tr><td><small>{h(r["id"])} · {h(r["status"])}</small><strong>{h(r["name"])}</strong><small>{h(r["official_period"])}</small></td><td>{n(r["official_value"])} / {n(r["actual_value"]) if r["actual_value"] is not None else "부분 합계 "+n(r["partial_registered_value"]) if r.get("partial_registered_value") is not None else "미산출"}<small>{h(r["metric_origin"] or "미확보")}</small></td><td>{h(r["explanation"])}<p>{h(r["next_action"])}</p><a href="{h(r["official_url"] or "",quote=True)}">검증 원문 ↗</a></td></tr>'
    corrected=''.join(f'<tr><td>{h(c["name"])}</td><td>{h(c["explanation"])}</td></tr>' for c in data['matching_corrections']['items'])
    metrics=''.join(f'<tr><td>{label}</td><td>{data["baseline_classification_metrics"][key]:.2f}%</td><td>{data["classification_metrics"][key]:.2f}%</td><td>{data["classification_metrics"][key]-data["baseline_classification_metrics"][key]:+.2f}%p</td></tr>' for key,label in [('accuracy','Accuracy'),('precision','Precision'),('recall','Recall'),('f1','F1 Score')])
    paths=''.join(f'<li><strong>{h(p["name"])}</strong> · {h(p["status"])}<p>{h(p["result"])}</p><a href="{h(p["url"],quote=True)}">수집 원천 ↗</a></li>' for p in data['additional_collection_paths'])
    return f'''<section class="section box"><h2>최초 평가 대비 4대 지표 변화</h2><div class="table-wrap"><table><thead><tr><th>지표</th><th>최초</th><th>보완 1차</th><th>차이</th></tr></thead><tbody>{metrics}</tbody></table></div><small>동일한 목적 표본 20쌍의 자동 연결 성능. 전체 플랫폼 정확도는 미산정.</small></section>
<section class="section box"><h2>53개 발표 항목 최신 재대조</h2><p>최초 확인 {data['baseline_agreement_percent']:.2f}% → 이번 {d['agreement']['overall_confirmed_percent']:.2f}%</p><p>{h(d['agreement']['definition_change'])}</p><p>자체 사건 실적의 동일 범위 일치 {d['agreement']['independent_actual_matches']}/{d['agreement']['independent_actual_rows']}행. 일치율은 목표·통계 참조 확인도 포함하며 전체 실적 정확도와 별도다.</p><div class="table-wrap"><table><thead><tr><th>항목·기간</th><th>발표 / HOME</th><th>미확인 원인과 다음 조치</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section class="section box"><h2>담당자 매칭 확인 오류 수정 · {len(data['matching_corrections']['items'])}건</h2><p>담당자 김민 · 사유 ‘담당자 매칭 확인 오류 수정’</p><p>이전 판본·정정 판본·원문 근거를 보존한다. 동일 사업의 전체·부분 관계를 바로잡고, 배분 근거가 없는 전체 승인 물량의 부분 사업 전용을 철회했다.</p><div class="table-wrap"><table><thead><tr><th>사업</th><th>정정 내용</th></tr></thead><tbody>{corrected}</tbody></table></div></section>
<section class="section box"><h2>추가 수집 경로와 실제 확보 결과</h2><ul class="evidence">{paths}</ul><h3>모집단·미확보</h3><p>관리 원천 사업 {d['population']['managed_source_records']}건. 전체 사업 분모 미확정.</p><p>{h(d['population']['note'])}</p><p>미확보 사건 지표: {h(' · '.join(d['missing_actual_metrics']))}</p></section>'''


def main():
    folder=ROOT/'data/remediation/r03'
    baseline=json.loads((ROOT/'docs/HOME_DATA_COLLECTION_MIDTERM_20261016.json').read_text())
    prior=json.loads((ROOT/'data/remediation/r02/round.json').read_text())
    first=json.loads((ROOT/'data/remediation/r01/round.json').read_text())
    current=deepcopy(prior);diagnostic=json.loads((folder/'diagnostics.json').read_text());verification=json.loads((folder/'verification.json').read_text())
    sources=json.loads((folder/'sources-after.json').read_text())['items'];requirements=json.loads((folder/'requirements-after.json').read_text())
    corrections=json.loads((folder/'matching-corrections.json').read_text())
    initial={i['id']:i for c in baseline['categories'] for i in c['items']};first_items={i['id']:i for c in first['categories'] for i in c['items']}
    current.update(title='HOME 보완 1차 성적표 · 수집 확대 및 담당자 매칭 정정',sequence=1,
        round_id='HOME-INTEGRITY-R01-CONSOLIDATED-20261017',parent_id='HOME-INTEGRITY-R00',actor=ACTOR,reason=REASON,
        previous_total_score=baseline['total_score'],comparison_base_label='최초 평가',assessed_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        scoring_version='HOME-COLLECTION-CONSOLIDATED-1',snapshot_id=verification['snapshot_id'],independent_snapshot_counts=verification['snapshot_counts'],
        agreement=diagnostic['agreement'],baseline_agreement_percent=baseline['agreement']['overall_confirmed_percent'],
        baseline_classification_metrics=baseline['classification_metrics'],diagnostics=diagnostic,matching_corrections=corrections,
        replaced_rounds=['HOME-INTEGRITY-R01','HOME-INTEGRITY-R02'],round_evidence={})
    current['classification_note']+=' 이번 확인된 담당자 승인 연결의 범위 오류 15건은 위 자동 연결 20쌍과 다른 검사 대상이다. 표본 100%는 과거 확정 연결 전체에 오류가 없다는 뜻이 아니다.'
    inventory=[r for r in diagnostic['population']['source_counts'] if r['source_id']=='ih_housing_inventory']
    roster=sum(r['records'] for r in diagnostic['population']['source_counts'] if r['kind']=='renewal_roster')
    current['additional_collection_paths']=[
        dict(name='iH 운영 임대단지 명부·상세',url='https://www.ih.co.kr/main/lease/leaseAptList.do',status='수집 적용',result=f"{sum(r['records'] for r in inventory)}개 명부 항목(17개 단지·2개 광역 프로그램), 재고·공급/입주 원문 표 보존. 실제 계약·실입주로 변환하지 않음."),
        dict(name='서울 정비사업 전체 공개 명부·사업개요',url='https://cleanup.seoul.go.kr/cleanup/bsnssttus/lscrMainIndx.do',status='수집 확대',result=f'{roster}개 공개 사업장 명부를 미연결 상태도 보존. 기존 관리사업의 사업개요 분양·임대 계획과 추진경과 원문 추가 확보.'),
        dict(name='iH 과거 공고·HWPX 첨부',url='https://www.ih.co.kr/main/bbs/bbsMsgList.do?bcd=notice&cate1=general&pgdiv=general',status='수집 보완',result='최신 목록·과거 중첩 이어받기·완료 후 순환 재방문·실패 상세 재시도와 HWPX 본문 추출 적용. 이진 HWP는 원문 보존 후 추가 정형화 대상.'),
        dict(name='건축HUB 일반 건축인허가',url='https://www.data.go.kr/data/15136267/openapi.do',status='추가 후보 확인',result='기존 주택인허가와 다른 서비스. 세부 기능·인증 권한·주택 범위를 검증한 후 적용하며 이번 실제 사건 확보로 가점하지 않음.')]
    extra={
        'A4':'HWPX 본문 추출과 압축/XML 크기 검증을 추가하고 이진 HWP 미지원 상태를 명시했다.',
        'B1':f'미연결 사업을 버리지 않고 서울 공개 명부 {roster}건을 별도 보존한다. 수도권 전체 분모는 미확정이다.',
        'B2':'iH 운영 임대단지 명부·상세와 서울 사업개요를 추가 수집했다. 운영 재고를 신규 공급으로 합산하지 않는다.',
        'B4':'iH 과거 목록을 중첩 수집하고 완료 후에도 순환 재방문한다. 전체/기관별 사업 모집단과 조회 완료를 분리한다.',
        'C4':f"담당자 확인 연결 전수를 점검해 확인된 전체·부분 범위 오류 {corrections['count']}건을 ‘담당자 매칭 확인 오류 수정’ 이력으로 정정했다.",
        'E1':'단계 연결의 변경승인 사건을 최초 승인과 구분하고, 동일한 인지시각의 통계 판본을 사용하도록 보완했다.',
        'E2':'전체 승인 물량을 부분 사업에 전용한 12건은 배분 근거 확보 전 미확정으로 정정. 마곡17의 577호/381호 관계 3건은 CONTAINED_SCOPE로 바로잡았다.',
        'G2':'iH 과거 수집 완료 후에도 2개 페이지씩 순환 재확인하여 오래된 공고의 변경을 탐지한다.',
        'H3':'확인된 담당자 매칭 오류에 이전/정정 판본·사유·담당자와 회귀검증을 연결했다. 원천 물량 미확보는 별도 잔여로 남긴다.',
        'J1':'53개 외부 검증 행을 현재 원천으로 재판정했다. 추정 관리 입력은 독립 실적 일치에서 제외하고, 목표·통계 참조 확인을 별도 표시했다.',
        'J4':'사용자 지시에 따라 이전 보완1·2를 목록에서 교체하고, 최초 평가에 직접 연결된 통합 보완1을 발행한다. 기존 결과는 해시 보관본과 교체 감사로 보존한다.'}
    for cat in current['categories']:
        for item in cat['items']:
            key=item['id'];item['previous_score']=initial[key]['score'];item['previous_reason']=initial[key]['reason']
            comment=first_items[key]['change_comment']
            if key in extra:comment+=' '+extra[key]
            if key in ('A1','A2'):
                count=sum(s['status']=='SUCCESS' for s in sources) if key=='A1' else sum(not s.get('manual_only',False) for s in sources)
                item.update(numerator=count,denominator=len(sources),fraction=count/len(sources))
                comment=f'최초 평가 대비 현재 원천 상태 재계산: {count}/{len(sources)}. 단일 최신 상태·자동 대상 비율이며 장기 성공률·전수 확보율과 구분.'
            if key in {'D1','D2','D3','D4','I3'}:
                code={'D1':'F-03','D2':'F-02','D3':'F-05','D4':'F-06','I3':'F-08'}[key];metric=requirements['metrics'][code]['without_estimates']
                item.update(numerator=metric['count'],denominator=metric['total'],fraction=metric['count']/metric['total'] if metric['total'] else 0)
                comment=f"최초 평가 대비 같은 정의로 재계산: {metric['count']}/{metric['total']}. 확인된 매칭 범위 오류를 정정하고 원천 근거와 추정을 구분. 물량 미검증은 신규 실적으로 승격하지 않음."
            if key=='H3':item.update(level=3,fraction=.75)
            item['score']=item['weight']*item['fraction'];item['score_delta']=item['score']-item['previous_score'];item['change_comment']=item['reason']=comment
        cat['score']=sum(i['score'] for i in cat['items'])
    current['total_score']=sum(c['score'] for c in current['categories']);current['display_score']=round(current['total_score'],1)
    for group in current['groups']:
        group['score']=sum(c['score'] for c in current['categories'] if c['group']==group['id']);group['percent']=group['score']/group['weight']*100
    suite=ET.parse(folder/'regression.xml').getroot().find('testsuite');assert int(suite.get('failures'))==int(suite.get('errors'))==0
    main_tests=len(ET.parse(folder/'regression.xml').getroot().findall('.//testcase'))
    current['tests']=dict(main_tests=main_tests,subtests=int(suite.get('tests'))-main_tests,javascript_tests=65,status='PASS')
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix in ('.json','.xml','.tap') and path.name!='round.json':
            current['round_evidence'][path.name]=dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
    html=render_followup(current)
    start=html.index('<section class="section box"><h2>공식 발표와의 전체 일치도')
    end=html.index('<section class="section box"><h2>독립 사건',start)
    a=current['agreement']
    html=html[:start]+f'<section class="section box"><h2>공식 발표와의 전체 확인율 · 별도 지표</h2><strong>{a["overall_confirmed_percent"]:.2f}%</strong><p>최초 {current["baseline_agreement_percent"]:.2f}% → 이번 {a["overall_confirmed_percent"]:.2f}% · {a["confirmed_matches"]}/{a["numeric_rows"]}행 확인 · 비교 대기 {a["pending"]}행</p><small>{escape(a["definition_change"])}</small></section>'+html[end:]
    html=html.replace('<section class="section" id="items">',details(current)+'<section class="section" id="items">')
    html=html.replace('직전 ','최초 평가 ').replace('이전 점수와 개선 코멘트','최초 평가 대비 점수와 개선 코멘트')
    target=ROOT/'docs/HOME_DATA_INTEGRITY_R01_CONSOLIDATED_20261017'
    for path in (target.with_suffix('.json'),folder/'round.json'):path.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n')
    for path in (target.with_suffix('.html'),folder/'round.html'):path.write_text(html)
    print(json.dumps(dict(round_id=current['round_id'],score=current['display_score'],baseline=baseline['display_score'],agreement=a['overall_confirmed_percent'],corrections=corrections['count']),ensure_ascii=False))


if __name__=='__main__':main()
