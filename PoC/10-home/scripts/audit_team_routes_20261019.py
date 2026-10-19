"""Compare the supplied 152-row research catalogue with HOME collector routes.

Research status is retained verbatim, never treated as this deployment's status.
This is a route audit; it does not certify every field listed by another team.
"""
import csv,json,re
from pathlib import Path
from collections import Counter
from backend.sources import SOURCES

ROOT=Path(__file__).resolve().parents[1];IN=ROOT/'docs/analysis/evidence/20261019-team-research';OUT=ROOT/'docs/analysis'
# Explicitly checked route correspondence. A common host alone is not a match.
M={
1:('policy_907,policy_907_plan','원문·정책 계획 보유','발표 원문 및 연도별 목표. 주기적 정책 게시판 전수 탐색은 별도'),
2:('policy_813','원문·후보 보유','개별 정책 원문 수집; 정례 개정·후속 발표 전수와 구분'),
3:('','개별 후속 원문 확인 필요','정책 후속조치 전용 수집기 없음'),
4:('lh_department_plans','정례 원문 수집','12개 문서·925개 표. 사업별 일정·호수 구조화는 미완료'),
5:('lh_construction,lh_completion_plan,lh_progress','부분 경로 운영','포털 전체가 아니라 등록된 특정 게시물·API별 수집'),
8:('seoul_cleanup,수동보관:official_document','관련 경로 확인','서울 정비사업 공개자료·정보몽땅 수집. 해당 데이터셋 최신 판본 전체 여부는 구분'),
9:('seoul_cleanup','정례 수집·상세 확대 중','명부와 단계 이력; 상세 조회 완료율 별도'),
16:('eum_housing_notices','정례 수집·과거 확대 중','목록·상세·첨부/OCR 상태를 구분. 최초·변경·취소 전수 이력 보장 아님'),
17:('building_hub,building_hub_incheon,building_hub_details','정례 API 수집','수도권 기본·동별·대지. 과거 법정동·대용량 파일 경로는 별도'),
18:('building_register,building_register_recap','정례 API 수집','표제부·총괄표제부 조회 확대 중'),
19:('molit_statistics,incheon_statistics,molit_monthly_release','정례 통계 수집','시도 총계. 사업별 허가 원장 대체 아님'),
20:('molit_statistics,incheon_statistics','정례 통계 수집','월별 착공. 사업별 착공과 분리'),
21:('molit_statistics,incheon_statistics','정례 통계 수집','월별 준공. 실제 입주 세대수 아님'),
22:('molit_statistics,incheon_statistics','정례 통계 수집','통계 지표·기간을 분리'),
23:('kosis_age,kosis_housing,kosis_household_size,kosis_employment,kosis_household_forecast','정례 통계 수집','선택된 표·연도·지역만; KOSIS 전체 수집 아님'),
24:('sgis_area','정례 통계 수집','선택된 소지역 통계·기간'),
30:('lh_notice,gh_notice,ih_notice','관련 기관 공고만 수집','마이홈 통합 공고·공공임대 단지 전용 경로 미연결'),
32:('기능:nearby_facilities','관련 시설 위치 조회','학교 표준데이터 자체 파일 전수와 학구·계획 변경 이력 미연결'),
33:('','미연결','학구 경계·학교 연계 ID 별도 필요'),
34:('기능:nearby_facilities','관련 시설 위치 조회','어린이집 표준데이터 전수·정원·개원 계획 별도'),
37:('ih_notice,ih_housing_inventory','관련 기관 자료만 수집','iH 준공사업 목록 전용 경로 미연결'),
38:('gh_notice,gh_supply_plan,gh_files,gh_completion_evidence','부분 경로 운영','공고·계획·매입재고·사용검사; GH 모든 사업 목록 아님'),
41:('','탐색용 목록','공공데이터포털 홈페이지 자체는 관측값 출처가 아님'),
42:('sh_files,seoul_cleanup','부분 경로 운영','서울 데이터포털 전체를 수집한 것으로 보지 않음'),
43:('kosis_age,kosis_housing,kosis_household_size','부분 경로 운영','SRC-023과 같은 포털. 중복 신규 출처로 세지 않음'),
44:('complex_approval_reference','관련 파일만 수집','K-apt 전용 API 없음. 부동산원 단지식별 파일로 일부 목적 보완'),
45:('eum_housing_notices','관련 고시 경로 운영','예시 seq의 상세 수집 여부는 별도; 게시판 연결만으로 원문 확보 주장 금지'),
46:('eum_housing_notices','관련 고시 경로 운영','지구 지정과 사업계획 승인·변경 사건 구분'),
47:('policy_907,policy_129,policy_813,urban_930','관련 정책 원문 보유','개별 URL 판본 대조 필요'),
55:('수동보관:official_document','10월 기준자료 보유','공식 브리핑 저장·흑석11/신림2 연결. 다음 회차 자동 탐색은 미구축'),
58:('lh_sale,lh_rent,lh_progress,lh_movein_history','정례 수집','입주계획·과거 공급·단지정보 인천 범위 이번 보완'),
59:('gh_notice','정례 공고 수집','공고 대상·호수·첨부 처리 범위 별도'),
62:('ih_notice','정례 공고 수집','iH 홈페이지 공고; 계약/공가 API와 별개'),
63:('cheongyak','정례 API 수집','APT 2018년 이후. 비APT·무순위·취소후재공급 endpoint 별도'),
65:('complex_approval_reference','관련 파일만 수집','K-apt 목록 API 전용 수집 미연결'),
66:('building_hub,building_hub_incheon','API만 운영·대용량 미연결','다른 팀 대용량 원본은 ZIP에 미포함. 원 파일 인수·파서·증분 적재 필요'),
67:('building_general_permit','관련 API 운영','표준데이터 제공파일 자체와 API는 다른 경로'),
68:('molit_statistics,incheon_statistics','정례 통계 수집','SRC-021과 같은 준공 통계 원천'),
70:('complex_approval_reference','관련 파일만 수집','SRC-044와 동일 데이터셋 15058453; 두 API로 세지 않음'),
72:('seoul_cleanup','정례 수집·상세 확대 중','SRC-009와 동일 시스템'),
73:('lh_notice','관련 기관 공고만 수집','SRC-030과 동일 마이홈. 단지·공고 전용 경로 필요'),
74:('','미연결','교육청 투자심사·학교설립 변경/취소·예정일 정례 수집 필요'),
75:('','미연결','지자체 국공립 어린이집 신축/개원·정원·운영주체 필요'),
76:('vworld_district,vworld_municipality,project_locations','부분 공간 경로 운영','VWorld 모든 레이어를 수집하지 않음. 사업 위치·블록·시설 각각 별도'),
77:('seoul_cleanup,eum_housing_notices','부분 경로 운영','서울/경기 지자체 위원회·시보·인허가 고시의 독립 수집 미완료'),
79:('lh_notice,cheongyak','부분 공고 수집','사전·본청약·정정·취소 회차 연결 및 과거 변동 비교 보강'),
80:('lh_progress,lh_construction','공개 공정 경로 운영','내부 착공예정 명세·자금·보상·철거 현황 미확보'),
81:('','미연결','생활SOC 사업계획·준공·개원 상태 정례 수집 필요'),
82:('lh_department_plans','정례 원문 수집','SRC-004 중복 경로'),
}
DEFER={6:'iH 도시개발 사업목록',7:'GH GIS 지구·토지공급',10:'서울 보도자료',11:'서울 공공임대 공급현황',12:'민간토지 공공주택 운영기준',13:'법령 변경 API',14:'입법예고 API',15:'전자관보',25:'열린재정 사업예산·집행',26:'지방재정365',27:'나라장터 입찰',28:'나라장터 계약·변경',29:'나라장터 계약과정',31:'서울주거포털 보도자료',35:'학교알리미 공시',36:'키스콘 통계',39:'서울 통합심의 결과',40:'리츠 정보',48:'서울 위원회 결과',49:'나라장터 조달요청',50:'조달 개방표준',51:'정례브리핑 목록·다음 회차',52:'정례브리핑 정책 브리프 자동 갱신',53:'전월세 과제 첨부 자동 갱신',54:'정례브리핑문 자동 갱신',56:'금융위 공동 보도자료 자동 갱신',57:'정례브리핑 PDF 자동 갱신',60:'SH 공공임대 공고 게시판',61:'SH 공공분양 공고 게시판',64:'청약 경쟁률·특별공급 결과',69:'청약통장 통계',71:'건물 에너지 사용량',78:'iH 도시개발·준공목록'}
for n,note in DEFER.items():M[n]=('','미연결 또는 정례 자동화 미구축',note+' 전용 경로. 타 경로의 단발 문서 보유와 구분')


def main():
    rows=list(csv.DictReader((IN/'원천사이트_대조.csv').open(encoding='utf-8-sig')))
    datasets={re.search(r'/data/(\d+)/',s['url'])[1]:s['id'] for s in SOURCES if re.search(r'/data/(\d+)/',s['url'])}
    result=[];source_states={}
    for idx,r in enumerate(rows,1):
        match=re.fullmatch(r'SRC-(\d+)',r['통합출처ID'])
        if match:ids,status,note=M[int(match[1])];source_states[r['통합출처ID']]=(ids,status,note)
        else:
            text=r['공식원천명']+' '+r['공식URL'];did=next((v for v in datasets if re.search(r'(?<!\d)'+v+r'(?!\d)',text)),None)
            if did:
                ids=datasets[did];status='이번 추가·실수집 완료' if ids.endswith('_plan_file') or ids=='sh_contract_file' else '대응 수집기 운영';note='동일 데이터셋 번호 대조. 자료 종류·판본별 수집량은 본문 참고'
            elif r['제공기관']=='Exa' or '/_exa' in text or '/_discovery' in text:
                ids='';status='조사 도구·파생 산출물';note='검색 결과 JSON은 공식 원천 행과 구분. ZIP에 원 파일 미포함'
            elif '주택파동' in r['제공기관'] or 'HOME PoC' in r['제공기관']:
                ids='';status='다른 팀의 내부 산출물';note='HOME 정본과 순환 참조·중복 집계 금지. 명시된 원 파일은 ZIP 미포함'
            elif 'lh-completion' in text:
                ids='lh_completion_plan';status='대응 수집기 운영';note='다른 팀은 빈 폴더로 기록했지만 HOME에는 204행 보유'
            else:
                ids='';status='개별 원문·별도 경로 추가 확인';note='외부 팀 경로·게시처 수준 정보. ZIP에 관측 원 파일은 미포함; HOME 수집 완료로 전용하지 않음'
        result.append(dict(대조행=idx,출처ID=r['통합출처ID'],자료명=r['공식원천명'],출처URL=r['공식URL'],제공자료의상태=r['우리_상태'],현재HOME수집기=ids,현재HOME판정=status,검토내용=note))
    write(OUT/'HOME_TEAM_ROUTE_AUDIT_20261019_sources.csv',result)
    fields=list(csv.DictReader((IN/'수집항목_통합.csv').open(encoding='utf-8-sig')));items=[]
    for r in fields:
        keys=re.findall(r'SRC-\d+',r['원천']);states=[source_states[k] for k in keys if k in source_states]
        items.append(dict(항목ID=r['항목ID'],자료명=r['대표_자료명'],요구필드=r['데이터_요소·필드'],단계=r['쓰는_단계'],연결키=r['연결키'],원천=r['원천'],제공자료의수집상태=r['우리_수집상태'],현재HOME대응수집기=';'.join(dict.fromkeys(x[0] for x in states if x[0])),경로판정=';'.join(dict.fromkeys(x[1] for x in states)) or '별도 파일·원천 식별 필요',필드검증='경로 대응표이며 개별 필드 값의 확보·정확도 인증 아님'))
    write(OUT/'HOME_TEAM_ROUTE_AUDIT_20261019_fields.csv',items)
    summary={'source_rows':len(result),'field_rows':len(items),'statuses':dict(Counter(r['현재HOME판정'] for r in result)),'external_link_fields':60,'external_roles':64,'external_quality_rows':236,'note':'출처 행에는 중복 URL·내부 산출물·검색 결과가 포함. 고유 공식 출처 152개나 정확도 분모로 사용하지 않음'}
    (OUT/'HOME_TEAM_ROUTE_AUDIT_20261019.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(summary)

def write(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

if __name__=='__main__':main()
