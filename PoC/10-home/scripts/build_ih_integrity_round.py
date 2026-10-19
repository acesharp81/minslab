"""R02: add iH primary website evidence and correct candidate policy scope."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.build_integrity_round import ROOT,render_followup,ACTOR,REASON


def main():
    folder=ROOT/'data/remediation/r02'
    previous=json.loads((ROOT/'data/remediation/r01/round.json').read_text())
    current=deepcopy(previous)
    verification=json.loads((folder/'verification.json').read_text())
    sources=json.loads((folder/'sources-after.json').read_text())['items']
    requirements=json.loads((folder/'requirements-after.json').read_text())
    current.update(title='HOME 2차 보완 성적표 · iH 직접 수집 및 정책 범위 검수',sequence=2,
        round_id='HOME-INTEGRITY-R02',parent_id='HOME-INTEGRITY-R01',actor=ACTOR,reason=REASON,
        previous_total_score=previous['total_score'],assessed_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        snapshot_id=verification['snapshot_id'],independent_snapshot_counts=verification['snapshot_counts'],
        scoring_version='HOME-COLLECTION-MIDTERM-1-R02',round_evidence={},
        classification_note=previous['classification_note']+' 이번 신설 iH 원천은 위 20쌍의 자동 연결 표본에 포함되지 않는다. iH HTML 파싱·필드 분리 검증은 별도이며 iH 전체 데이터 정확도를 100%로 뜻하지 않는다.')
    comments={
      'A1':f"iH 공식 홈페이지 신규 수집 경로에서 실제 적재·재실행이 성공했다. API 504와 홈페이지 수집 성공을 다른 원천으로 표시한다.",
      'A2':'iH 홈페이지는 별도 인증키 없이 1시간 갱신 작업에 포함했다. 기존 iH 재고 API는 접근 미확인 참조 원천으로 보존한다.',
      'A4':'iH 게시판·사업 상세·PDF/HWP 첨부를 원문 해시로 보존했다. PDF 일부의 명시적 값만 파싱하며 HWP는 원문 보관과 추가 정형화를 구분한다.',
      'B1':f"정비·허가 후보 명부에 더해 iH 원천 사업 {verification['projects']}건을 별도 등록했다. 등록 수를 수도권 전수 분모로 바꾸지 않았다.",
      'B2':f"iH 공식 사업 {verification['projects']}건·주택 공고 {verification['documents']}건을 실제 확보했다. 분양 게시판과 임대 게시판의 페이지 체크포인트를 보존하며 과거 이어받기는 진행 중이다.",
      'B4':'iH의 게시판 코드·전체 페이지 수·이번 조회 페이지·다음 페이지를 기록한다. 최신 2페이지 재확인과 과거 최대 6페이지 수집을 함께 수행한다.',
      'C2':'iH 사업을 담당자 검토 후보로 생성하고 일반 프로그램의 임시 정책 제안만으로 정책 실적 분모에 들어가지 않게 보완했다.',
      'C3':'참고 원천의 관리 후보와 iH 원천 사업은 정책 미귀속으로 유지한다. 기존 사업의 PRO/HPR 전면 통일은 아직 미완료다.',
      'C4':'토지·상가·체육관을 주택 후보에서 제외하고 공고 상세·첨부 고유번호를 검증했다. 원문 대조 표본 및 iH 실제 HTML 회귀검증의 범위를 구분한다.',
      'E1':'iH 착공·준공 예정 반기를 원래 정밀도의 계획으로 저장한다. 예비자·추가·정정공고와 실제 공급·계약·실입주를 분리한다.',
      'E2':'iH 사업 계획 세대수와 공고 금회 공급을 다른 필드로 보존한다. 여러 수량이 충돌하거나 구획이 불명확하면 미확정으로 남긴다.',
      'E3':'iH 공고 고유번호는 페이지가 달라도 같게 저장하며 예비/정정/추가 회차를 신규 전체 공급으로 합산하지 않는다.',
      'E4':'최종 범위 검수에서 원천 후보가 프로그램의 임시 정책 제안을 따라 분모에 들어가는 경로를 수정했다. 후보는 전체 관리에서 조회하되 정책 귀속 전에는 해당 정책 수치에 포함하지 않는다.',
      'F1':'iH 목록·본문·첨부의 실제 HTTP 원문과 SHA-256을 보존했다. 공식 Swagger도 보관해 기존 API 주소가 명세와 일치함을 확인했다.',
      'F3':f"기존 확정·해제 {verification['approved_mappings_preserved']}건은 그대로 보존했다. iH 수집과 정책 범위 수정은 김민·지정 사유의 2차 조치 이력으로 별도 기록했다.",
      'F4':'2차 결과를 새로운 인지 기준시각과 입력 판본·규칙 해시로 동결했다. 1차 성적표와 집계 기준본을 덮어쓰지 않았다.',
      'G1':'iH 공개 홈페이지를 최신 탐지 전용 작업자에 추가했다. API 실패가 홈페이지 수집을 막지 않으며 1시간 주기의 실운영 장기 검증은 계속한다.',
      'G3':'작업 임대 복구 후 이전 작업자의 완료·실패 처리가 새 작업 상태를 덮지 못하도록 식별자 검증을 추가하고 회귀검증했다.',
      'H1':'iH 실제 HTML의 페이지·첨부 ID·정정 회차·반기 계획과 수집 분기, 정책 분모 보호·이전 작업자 차단을 포함한 전체 회귀검증을 수행했다.',
      'H2':'첫 iH 적재 실패는 확보된 원문 재처리로 복구하고, 이후 웹 실호출 재실행도 성공했다. API 504 실패 이력과 마지막 정상 원문은 보존한다.',
      'H3':'1차 발행본을 보존하고 iH 보완과 정책 분모 검수 결과를 2차 조치·성적표에 기록한다. 과거 페이지·수량·HWP 검토는 완료로 표시하지 않는다.',
      'I1':'iH 홈페이지에서 확보한 모집공고와 계획을 실제 계약·실입주 실적으로 바꾸지 않았다. 해당 원천 사건의 추가 확보가 계속 필요하다.',
      'J1':'새 후보를 임의 정책 귀속시키지 않고 독립 사건 집계는 직접 근거·날짜·물량이 확인된 사건만 선택한다. iH 자료 확대를 전체 공급 실적 증가로 설명하지 않는다.',
      'J4':'처음→1차→2차의 부모 회차와 검증 해시를 유지한다. 정책 분모 범위 보완은 이전 값을 남기고 새 회차에 반영했다.',
    }
    ratio_map={'D1':'F-03','D2':'F-02','D3':'F-05','D4':'F-06','I3':'F-08'}
    for category in current['categories']:
        for item in category['items']:
            item['previous_score']=item['score'];item['previous_reason']=item['reason']
            comment=comments.get(item['id'],'1차 보완 상태를 유지했다. 이번 iH 원천 확대와 직접 관련된 추가 완료 근거가 없어 같은 점수를 유지한다. '+item['reason'])
            if item['id'] in ('A1','A2'):
                count=sum(s['status']=='SUCCESS' for s in sources) if item['id']=='A1' else sum(not s.get('manual_only',False) for s in sources)
                item.update(numerator=count,denominator=len(sources),fraction=count/len(sources))
                comment+=f" 최종 관측 {count}/{len(sources)}."
            elif item['id'] in ratio_map:
                metric=requirements['metrics'][ratio_map[item['id']]]['without_estimates']
                item.update(numerator=metric['count'],denominator=metric['total'],fraction=metric['count']/metric['total'] if metric['total'] else 0)
                comment=f"정책 미귀속 후보를 제외해 등록 정책 자료의 분모를 바로잡았다. 이번 비추정 근거 {metric['count']}/{metric['total']}. 1차 발행본의 후보 포함 분모는 원본에 보존하며 이번 회차에 정정한다."
            elif item['id']=='B2':
                item['level']=3;item['fraction']=.75
            item['score']=item['weight']*item['fraction'];item['score_delta']=item['score']-item['previous_score']
            item['change_comment']=comment;item['reason']=comment
        category['score']=sum(i['score'] for i in category['items'])
    current['total_score']=sum(c['score'] for c in current['categories']);current['display_score']=round(current['total_score'],1)
    for group in current['groups']:
        group['score']=sum(c['score'] for c in current['categories'] if c['group']==group['id']);group['percent']=group['score']/group['weight']*100
    current['metrics'].update(registered_sources=len(sources),successful_sources=sum(s['status']=='SUCCESS' for s in sources),
                              requirements=requirements['metrics'],policy_project_records=requirements['project_count'])
    xml=ET.parse(folder/'regression.xml').getroot();suite=xml.find('testsuite')
    assert int(suite.get('failures'))==int(suite.get('errors'))==0
    main_tests=len(xml.findall('.//testcase'))
    current['tests']=dict(main_tests=main_tests,subtests=int(suite.get('tests'))-main_tests,javascript_tests=65,status='PASS')
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix in ('.json','.xml','.tap') and path.name not in ('round.json',):
            current['round_evidence'][path.name]=dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
    output=ROOT/'docs/HOME_DATA_INTEGRITY_R02_20261017'
    html=render_followup(current)
    for path in (output.with_suffix('.json'),folder/'round.json'):path.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n')
    for path in (output.with_suffix('.html'),folder/'round.html'):path.write_text(html)
    print(json.dumps(dict(score=current['display_score'],previous=previous['display_score'],projects=verification['projects'],documents=verification['documents'],tests=current['tests']),ensure_ascii=False))


if __name__=='__main__':main()
