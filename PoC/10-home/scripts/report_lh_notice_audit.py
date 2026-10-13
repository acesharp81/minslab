"""Render the shareable diagnosis from an applied audit, with explicit remaining scope."""
import argparse,json
from collections import Counter
from pathlib import Path
from html import escape


def render(a,b):
 e=lambda v:escape(str(v if v is not None else '미확인'))
 docs=a['details'];links=a['new_links'];before={p['id']:p for p in b['items']}
 fresh=[p for p in a['matrix']['items'] if any(t.get('date') for t in p['cells']['MOVE_IN']['targets']) and not any(t.get('date') for t in before[p['id']]['cells']['MOVE_IN']['targets'])]
 def table(headers,rows):
  return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+e(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'
 def url(r,label='공식 원문'):return '<a href="'+e(r['evidence_url'])+'" target="_blank" rel="noopener">'+e(label)+'</a>'
 groups={}
 for d in docs:
  key=(d['district'],d['block'],d['tenure']);groups.setdefault(key,[]).append(d)
 examples=[]
 for key,rows in sorted(groups.items()):
  d=max(rows,key=lambda r:r['source_date'] or '')
  examples.append([e(key[0]+' '+key[1]),e(key[2]),e(d['planned_units']),e(d['offered_units']),e(d['move_in_month']),str(len(rows)),url(d)])
 reasons=[
 ('① 값은 이미 있었음','국민임대 공급계획 438호에는 2027-01이 저장돼 있었습니다. 건설사업 633호 화면에서 보이지 않은 문제입니다.'),
 ('② 목록에서 멈춘 수집','DB에 LH 공고 3,050건이 있지만 기존 수집기는 제목·공고일·링크만 받았습니다. 상세 공급정보의 입주일·유형별 총호수·금회 모집호수는 추출하지 않았습니다.'),
 ('③ 연결 대상에서 빠짐','기존 수집·연계 자동 연결은 청약홈 notice와 LH 연간 입주계획 위주였습니다. LH lh_notice의 상세 사실이 연결 입력에 없었습니다.'),
 ('④ 전체와 일부를 구분 못함','633호 건설 계약과 438호 국민임대의 호수 불일치를 단순 보류했습니다. 219호는 금회 모집량이며 438호나 633호와 바꿔 쓸 수 없습니다.'),
 ('⑤ 복합 계약 경고','성남금토 건설기록은 국토지리정보원 복합시설과 함께 기재되어 MULTI_SITE_CONTRACT로 제외됐습니다. 별도 고시의 국민 438+영구 195 구성으로 주택 범위를 대조해야 연결할 수 있습니다.'),
 ('⑥ 표시 의미의 혼동','입주 예정 자료 확보와 실제 입주 시작일 확보는 별개입니다. 실제 입주 수집방안 미확인 문구가 있어도 예정월 자체가 없는 것은 아닙니다.')]
 actions=[
 ('완료','LH 공고 상세 수집','분양의 입주예정일·임대의 입주예정월을 모두 추출. 총세대수와 금회 공급호수를 분리. 원문·URL·SHA256·공고 판본 보관.'),
 ('완료','부분 범위 연결','일치하는 지구·단일 블록의 공식 상세는 일부 유형 후보로 저장. 전체 사업 목표·실적에 합산하지 않고 438/633 등 적용 범위 표시.'),
 ('완료','복합 계약 예외의 근거','공식 승인 자료에서 주택 세대수 구성이 별도로 확인된 계약만 검토 후보 허용. 복합 계약 경고를 일괄 해제하지 않음.'),
 ('완료','DB 검토 보존','확정·해제·고정 원천 판본 유지. 조회 때 재매칭하지 않음. 신규 상세만 후보 추가. 원공고·정정공고 각각 보존하되 호수 합산 금지.'),
 ('완료','수집 경로 연결','기존 자동 수집 루프에서 상세 원천은 최근 성공 후 7일 간격 재점검. LH 공고 목록을 수동 갱신한 뒤에도 상세 수집 연쇄 실행.'),
 ('다음 1순위','공고 목록 최신성·지역 범위','목록 API는 현재 수동 갱신이며 서울·경기 범위. 인천 쿼리·정기 목록 갱신·신규 사업 발견 경로를 확장해야 함. 기존 목록 재조회만으로 새 공고 전수를 보장하지 않음.'),
 ('다음 1순위','사업–주택유형–모집차수 구조','단지 633 / 국민438 / 영구195 / 금회219를 별도 객체로 관리하고 유형별 날짜를 연결. 담당자 승인한 동일 사업·부분 범위와 수량 보존식 검증을 표준화.'),
 ('다음 1순위','정정·취소·일정 충돌 검토함','현재 각 판본과 미반영 새 판본은 보존. 취소가 기존 연결에 미치는 영향, 변경 일정 차이, 최신 유효 공고 선택을 담당자 검토함과 알림으로 관리해야 함.'),
 ('다음 2순위','첨부파일·별칭·복수단지','지구/블록이 없는 브랜드명 공고, 복수단지 공고, PDF/HWP에만 있는 일정은 별도 추출·주소/필지 대조·담당자 검토 필요. 제목 후보 밖 2,997건을 모두 누락 또는 비관련으로 단정할 수 없음.'),
 ('다음 2순위','정책 그래프 반영 규칙','공식 공고 확보와 9·7 정책 귀속 확정은 별개. 검토한 사업·유형 범위 및 최신 목표 채택 규칙을 거쳐 그래프에 반영. 이번 보완은 수집·연계 근거이며 정책 총량·기존 목표를 덮어쓰지 않음.'),
 ('다음 2순위','실제 입주 확인','모집공고는 예정일만 증명. LH 입주안내·입주지정기간·기관 확인을 별도로 연결. 실제 미확인은 0호나 지연 확정으로 계산하지 않음.'),
 ('상시','누락 감시 지표','목록/상세/추출/매칭/검토/화면의 각 분모, 최종 성공시각, 실패·보류 사유를 점검. 상세 실패와 미정·미제공·관계 미확인을 분리하고 재시도 큐를 운영.')]
 html='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>성남금토 입주 일정 누락 진단과 전체 보완 대책</title><link rel="stylesheet" href="/poc/home/assets/evidence-repair-report.css"><main><a href="/poc/home/#project-collection">← 사업별 수집·연계</a><h1>공개 자료는 있는데, 왜 사업 화면에 안 보였을까?</h1><p>성남금토 A-2BL 및 유사 사례 점검 · 2026-10-12 · 운영 DB와 공식 원문 기준</p><section><h2>결론: 미수집·미연결·부분 범위를 구분해야 합니다</h2><p>성남금토 국민임대의 2027년 1월 예정은 이미 공급계획 DB에 있었습니다. 그러나 상세 공고 수집과 전체 건설사업 연결이 빠져 있었습니다. 이전 정비는 동일 물량의 연결 중심이어서 이 문제를 해결하지 못했습니다.</p><p>공개 원천이 0이거나 없는 사례가 아닙니다. 홈페이지에서 찾을 수 있는 자료라도 목록 수집 → 상세 추출 → 사업 범위 대조 → 저장 연결 → 화면 표시를 모두 거쳐야 보입니다.</p></section>'''
 html+='<section><h2>이번에 확인한 범위</h2><p>사업 기록 292개 · 저장 LH 공고 3,050건 → 지구·단일 블록 일치 후보 53건 → 상세 53건 및 입주 예정월 53건 확보. 고유 블록 28개, 주택유형별 묶음 30개입니다. 원공고·정정공고를 포함한 문서 수이며 공급 호수가 아닙니다.</p><p>추가 연결 '+str(len(links))+'건 / 영향 사업 기록 '+str(len({r['project_id'] for r in links}))+'개 / 기존에 날짜가 없던 입주 칸 '+str(len(fresh))+'개에 예정일 근거 추가. 동일 범위 '+str(sum(r['relation_type']=='SAME_SCOPE' for r in links))+'건, 일부 범위 '+str(sum(r['relation_type']=='PARTIAL_SCOPE' for r in links))+'건. 모든 신규 연결은 담당자 검토 후보입니다.</p><p>53건 요청·파싱 실패 0건. 유형별 원공고·정정공고 사이 입주월 차이 0건. 영구임대 2개 판본의 금회 공급호수는 표에서 확인되지 않아 미확인으로 보존했습니다. 제목 후보 밖 2,997건 및 전국 전체 공고까지 검증했다는 의미는 아닙니다.</p></section>'
 html+='<section><h2>성남금토의 숫자를 읽는 방법</h2>'+table(['구분','호수','의미','입주 예정'],[[e('건설사업의 주택 부분'),'633',e('국민+영구 전체. 복합시설 공사 범위와 구분'),e('유형별 근거를 함께 표시')],[e('국민임대'),'438',e('국민임대 유형 전체. 2026-07-08 원공고 및 07-09 정정 게시'),e('2027-01')],[e('금회 국민임대 모집'),'219',e('공고 표의 금회 공급세대수 합계. 438/633과 중복 합산 금지'),e('국민임대 예정월 참조')],[e('영구임대'),'195',e('별도 영구임대 원공고·정정공고'),e('2027-01')]])+'<p>국토부 제2023-583호(2023-10-23) 변경승인 본문에서 438+195=633을 확인했습니다. 본문 최초 승인일 2021-12-31과 변경승인일을 구분합니다. 상단 관보 날짜 서식은 자리표시자여서 사건 날짜로 사용하지 않았습니다. 이후 추가 변경 여부는 별도 확인 대상입니다. '+url(a['approval_document'])+'</p></section>'
 html+='<section><h2>누락 원인</h2>'+table(['원인','확인 결과'],[[e(k),e(v)] for k,v in reasons])+'</section>'
 html+='<section><h2>보완된 연결 경로</h2><p>LH 목록 API → 공식 상세 HTML(원공고·정정공고) → 유형별 총세대수 / 금회 모집량 / 입주 예정월 분리 → 지역·지구·블록·주택유형·범위 대조 → 원문 판본을 고정한 DB 연결(REVIEW) → 사업×단계 표 → 담당자 확정·해제</p><p>복합 계약은 별도 공식 승인 문서의 주택 구성으로 대조합니다. 일부 주택유형은 “국민임대 438호 / 전체 633호”처럼 표시하며 전체 실적·목표로 바꾸지 않습니다. 준공일을 입주일로 변환하지 않습니다.</p></section>'
 html+='<section><h2>유사 사례 전체: 28개 블록 · 30개 유형 묶음</h2><p>모든 값은 공식 상세에서 확인한 예정값입니다. 기존에 이미 확보한 일정의 근거 보강도 포함합니다. 사업명·브랜드만 비슷한 공고는 무리하게 연결하지 않았습니다.</p>'+table(['지구·블록','유형','유형 총호수','금회 공급','입주 예정월','공고 판본 수','근거'],examples)+'</section>'
 html+='<section><h2>앞으로의 전체 보완 대책</h2>'+table(['진행','과제','적용 원칙·완료 조건'],[[e(c) for c in row] for row in actions])+'</section>'
 html+='<section><h2>추가 연결 '+str(len(links))+'건</h2>'+table(['사업 기록','추가 원천','관계','사유'],[[e(r['name']),url(r,r['source_name']),e('일부 범위' if r['relation_type']=='PARTIAL_SCOPE' else '동일 범위 후보'),e(r['basis'])] for r in links])+'</section>'
 html+='<section><h2>검토 방법과 남은 한계</h2><p>데이터 현황 → 사업별 수집·연계 → 성남금토 검색 → 입주/인허가 칸 선택. 적용 범위·공식 원문·고정 판본·연결 사유를 확인하고 관리자가 확정 또는 해제합니다. 확정은 연결 확인이며 예정값을 실제 입주로 바꾸지 않습니다.</p><p>이번에는 API 키 추가 없이 이미 확보한 공고 목록과 공개 상세를 이용했습니다. 정기 공고 목록 확대, 첨부문서 전수 추출, 검토한 범위의 정책 그래프 적용은 남은 과제입니다. 수집한 자료의 양과 정책 목표 135만호의 입증 범위를 동일시하면 안 됩니다.</p></section></main></html>'
 return html

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--audit',required=True);p.add_argument('--before',required=True);p.add_argument('--output',required=True);args=p.parse_args()
 Path(args.output).write_text(render(json.loads(Path(args.audit).read_text()),json.loads(Path(args.before).read_text())))
