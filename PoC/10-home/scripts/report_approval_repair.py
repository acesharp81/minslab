"""Explain approval matching changes, source coverage and unresolved cases from audit snapshots."""
import json,argparse
from pathlib import Path
from html import escape
from collections import Counter

def render(first,last,notices,details):
 e=lambda v:escape(str(v if v is not None else '미확인'))
 before={(r['project_id'],r['stage']):r for r in first['before']['items']};after=last['after']['items']
 approvals=[r for r in after if r['stage']=='APPROVAL'];improved=[]
 for r in approvals:
  b=before[(r['project_id'],r['stage'])]
  if (r.get('selected') or {}).get('event_date') and not (b.get('selected') or {}).get('event_date'):improved.append(r)
 def table(head,rows):
  return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+e(x)+'</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+e(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'
 bc=Counter(r['status'] for r in first['before']['items'] if r['stage']=='APPROVAL');ac=Counter(r['status'] for r in approvals)
 event_count=sum(bool((r.get('selected') or {}).get('event_date')) for r in approvals)
 source_counts=notices['stats']['region_counts']
 juam_url='https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?panId=0000060939&ccrCnntSysDsCd=02&uppAisTpCd=39&aisTpCd=39&mi=1027'
 h='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>과천주암 C2 및 전체 인허가 연결 정비</title><link rel="stylesheet" href="/poc/home/assets/evidence-repair-report.css"><main><a href="/poc/home/#project-collection">← 사업별 수집·연계</a><h1>인허가가 있는데 왜 연결되지 않았나?</h1><p>과천주암 C2를 계기로 점검한 전체 사업 연결 · 2026-10-12 · 원천 수집과 DB 적용 기록</p>'''
 h+='<section><h2>과천주암 C2: 자료 미확보와 연결 누락은 다릅니다</h2><p>건축HUB 허가일 2020-12-29, 총 1,030호는 이미 수집돼 있었습니다. 1,030호 건설사업은 연결 검토 상태였지만, 별도 기록인 행복주택 344호는 인허가 미연결이었습니다.</p>'+table(['기록','정비 전','이번 반영'],[['C2 건설사업 1,030호','건축HUB 허가일 연결 검토','기존 연결·판본 보존, 날짜와 원천 범위 표시'],['C2 행복주택 344호','인허가 미연결','같은 블록의 1,030호 승인에 포함되는 부분 사업 후보로 DB 연결. 적용 344호 / 원천 1,030호'],['C1 건설사업 1,338호','착공에 따른 선행단계 추정','다른 C2 자료를 섞지 않고 C1 원천 허가일 2020-12-31 후보로 보강']])+'<p>이는 건축HUB 원천 허가일 기준입니다. 사용자께서 제시한 모집공고는 사업 구성과 공급 사실의 근거이며 승인 고시 자체를 대신하지 않습니다. 승인권자·고시번호·최초/변경승인 관계를 확정하려면 국토부·관보 원문 추가 대조가 필요합니다.</p><p><a href="https://www.data.go.kr/data/15136560/openapi.do">건축HUB 주택인허가 원천</a> · <a href="'+e(juam_url)+'">LH 과천주암 C2 공식 모집공고</a></p></section>'
 h+='<section><h2>공통 원인과 적용한 수정</h2>'+table(['원인','기존 동작','전체 적용한 보완'],[
 ['명칭 부가표기','과천주암(뉴스테이), 닫히지 않은 괄호가 후보 검색어에 포함','지역·지구·단일 블록을 공통 식별자로 정규화. 검색에도 정규화한 지구명 사용. 다른 블록과 동명 다른 지역은 제외'],
 ['사업 범위 차이','전체 단지와 일부 임대 유형을 구분하지 못함','사업량/승인 원천량을 별도 저장. 부분 사업은 전체 승인에 포함되는 후보, 일부 승인만 있으면 그 물량만 적용'],
 ['고시 경로의 단절','고시 수집은 고정 시범 2건 중심; 별도 보관 문서가 단계 후보에 들어가지 않음','이미 보관한 공식 문서 중 실제 승인 날짜가 확인된 사건을 단계 후보에 포함. 지구계획·초안·모집공고를 허가일로 변환하지 않음'],
 ['약한 기존 연결 고정','착공 선행 추정이 먼저 저장되면 새 허가일이 생겨도 표시가 그대로','담당자가 미검토한 선행 추정만 동일 지구·블록의 공식 사건일 후보로 보강. 최종 상태는 REVIEW; 검토·확정·해제와 기존 실제 사건 링크는 보존'],
 ['공고 유형 누락','LH 목록 API에서 05 분양·06 임대만 조회','39 신혼희망타운 추가. 서울·경기와 함께 인천 28 추가. 유형·지역별 페이지 수와 총건수 검증'],
 ['목록 최신성','공고 목록 갱신이 수동','목록은 자동 수집 루프에서 최근 성공 후 1일 간격 조회. 목록 갱신 후 상세 수집 연계. 주기별 성공·실패 기록'],
 ['화면 의미 불명확','실제 허가일 근거도 단순 상태 자료로 표현','공식 사건일/선행 추정 구분. 적용 사업 호수와 원천 승인 호수 표시. 담당자 검토 입력에 범위·공식 문서 유형 보존']])+'</section>'
 h+='<section><h2>공식 근거에서 화면까지</h2><p>건축HUB 허가 기록 / 날짜가 검증된 공식 승인 문서 → 지역·지구·블록 대조 → 동일 범위 / 전체 승인에 포함된 부분 사업 / 일부 승인만 확보 구분 → DB에 원천 판본·날짜·적용 호수·검토 상태 저장 → 사업×단계 표 및 정책–프로그램–사업 연결 검토 화면</p><p>LH 공고 목록 → 상세의 단지 총호수·금회 모집호수·입주월 분리 → 공급·입주 예정 근거. 이 경로는 인허가 사건과 분리합니다. 1,030=686 공공분양+344 행복주택을 확인했지만 공공분양 예정월을 임대 344호의 확정 일정으로 확대 적용하지 않습니다.</p></section>'
 h+='<section><h2>전체 적용 결과</h2><p>292개 사업 기록의 인허가 연결을 점검했습니다. 인허가 미연결 '+str(bc['UNMATCHED'])+' → '+str(ac['UNMATCHED'])+'개, 검토 후보 '+str(ac['REVIEW'])+'개입니다. 원천 사건일을 가진 선택 연결은 '+str(event_count)+'개이고, 나머지 선택 연결은 날짜 없는 상태·선행 추정 등으로 구분해야 합니다.</p><p>이번에 새로 날짜 근거를 연결하거나 추정을 보강한 사업 기록은 '+str(len(improved))+'개입니다. 모든 후보가 담당자 확정된 것은 아닙니다. 남은 '+str(ac['UNMATCHED'])+'개를 인허가 미취득으로 해석하지 않습니다.</p>'+table(['사업 기록','새 원천 사건일','적용 호수','승인 원천 호수','근거'],[[r['name'],r['selected']['event_date'],r['selected'].get('units'),r['selected'].get('source_units',r['selected'].get('units')),r['selected']['basis']] for r in improved])+'</section>'
 h+='<section><h2>공고 수집 사각지대 보완</h2><p>기존 3,050개 공고에서 신규 968건을 추가해 4,018건을 저장했습니다. 신혼희망타운 374건(서울31·경기325·인천18)이 포함됩니다. 이는 공고 기록 수이며 공급 호수가 아닙니다. 지역 혼합 2건과 어린이집 239건은 원문을 보관하되 주택사업으로 임의 배분하지 않았습니다.</p>'+table(['지역·유형','API 전체 응답','페이지 수','주택공고 저장'],[[k,v['fetched'],v['pages'],v['collected']] for k,v in source_counts.items()])+'<p>현재 사업과 제목의 지구·단일 블록이 대응되는 상세 '+str(details['stats']['detail_acquired'])+'건을 확보했습니다. 이전 53건 대비 62건 추가입니다. 상세 실패 '+str(details['stats']['failed_details'])+'건. 여기에 기반한 공급·입주 근거 연결 67건을 27개 사업 기록에 추가했습니다. 인허가 연결 개선 7개 기록과는 별도 집계입니다.</p></section>'
 h+='<section><h2>담당자 확인 방법</h2><p>데이터 현황 → 정책–프로그램–사업 연결 → 단계 근거 연결에서 사업명을 검색합니다. 과천주암(뉴스테이) C2의 인허가를 선택하면 원천 허가일, 사업 344호 / 승인 원천 1,030호, 원문과 후보 사유를 확인할 수 있습니다. 최종 관계를 확인한 뒤 확정하거나 다른 후보 선택·해제할 수 있습니다.</p><p>사업별 수집·연계에서도 인허가 칸에 같은 근거가 표시됩니다. 원천 API에 고시 전문이 없다는 사실은 별도 수집 과제이며, 이미 확보한 허가 기록을 숨기지 않습니다.</p></section>'
 h+='<section><h2>남은 보완 과제</h2>'+table(['우선순위','과제','완료 판단 기준'],[
 ['1','미연결 147개 원인별 분류','필지/주소 미정규화, 원천 사업명 공란, 복수 블록 계약, 승인 문서 미수집을 분리. 누락을 0호·허가 미취득으로 처리하지 않음'],
 ['1','국토부·지자체·관보 고시 탐색 확장','현재 고정 시범 자료·직접 검증 문서에서 정기 검색/원문 수집으로 확장. 고시번호·본문 날짜·사업 범위 대조. 최초 승인과 변경승인을 구분'],
 ['1','부분 승인 관계의 담당자 확정','686/344/1030 같은 수량 보존식과 주택유형을 확인. 같은 블록이라도 차수·기간·용도가 다르면 해제'],
 ['2','정정·취소와 판본 변경 알림','공고 이력 계보와 원천 새 판본을 검토함으로 전달. 현재 원문 판본은 보존하며 자동 덮어쓰기하지 않음'],
 ['2','첨부 PDF/HWP·복수단지 상세 분해','HTML에 없는 사건·유형·일정, 지구명 없는 브랜드명을 주소·필지로 교차 검증'],
 ['상시','정책 귀속·집계 범위 검증','승인일 확보와 9·7 정책 귀속 확정은 별개. 같은 단지 전체/일부 사업을 중복 합산하지 않도록 담당자 확인. 정책 목표 135만호를 새 공고 수로 대체하지 않음']])+'<p>이번 정비는 실제 저장된 전체 사업에 공통 규칙을 적용한 것입니다. 전국 모든 사업과 모든 고시를 확보했다는 의미는 아닙니다. 추가 API 키 없이 기존 키와 공개 자료로 수행했습니다.</p></section></main></html>'
 return h
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--first',required=True);p.add_argument('--last',required=True);p.add_argument('--notices',required=True);p.add_argument('--details',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 Path(a.output).write_text(render(*(json.loads(Path(getattr(a,k)).read_text()) for k in ('first','last','notices','details'))))
