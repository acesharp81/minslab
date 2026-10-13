"""Backfill verified prior repairs. Re-running identical entries does not add revisions.
Future repairs: python -m scripts.record_collection_repairs --file reviewed-records.json
JSON is an array of {key, title, cause, action, remaining, stages, status, base_date,
project_ids, source_ids, impact, report_url}. Preserve a stable key when updating a case.
"""
import argparse, json
from backend.service import HomeService
from backend.db import engine_for
from backend.collection_repairs import save, classify_existing

COMMON = dict(base_date='2026-10-12', status='APPLIED_REVIEW_PENDING', project_ids=[], source_ids=[])
REPORT = '/poc/home/assets/reports/'
RECORDS = [
 dict(key='a31-alias-and-documents', title='평택고덕 A31 · 사업 별칭과 공식 문서 연결 누락',
  project_ids=['PRO_89b769c87e8d8ee8f6a837bf','PRO_f579d71a70d2f60499abdb0b'],
  source_ids=['lh_sale','lh_construction','official_document'], stages=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],
  cause='동일 690호 사업이 공급·건설 원천에서 A31 / Ab31로 달리 표기되어 분리됐고 공모·고시·예정 자료를 연결할 경로가 부족했습니다.',
  action='지역·지구·사업명에 명시된 블록·총호수를 대조해 연결 후보를 DB에 저장했습니다. 공식 문서를 사업화·입주 예정·인허가 문서 근거로 구분했습니다.',
  impact='평택고덕 A31 공급 및 건설 기록 2개. 전체/일부 범위와 원천 판본을 유지합니다.',
  remaining='인허가 초안의 2025-000·빈 날짜는 실제 승인일로 사용하지 않습니다. 연결 후보의 최종 동일성과 정책 귀속은 담당자 검토 대상입니다.',
  report_url=REPORT+'EVIDENCE_LINK_REPAIR_20261012.html'),
 dict(key='cross-source-bridges', title='전체 사업 · 분리된 원천을 DB 연결 후보로 관리',
  source_ids=['lh_sale','lh_rent','lh_construction','official_document','lh_notice_detail'],
  stages=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],
  cause='동일 사업의 공급·건설·일정 근거가 별도 원천에 존재해도 사업별 수집 표에서 함께 보이지 않았습니다.',
  action='지역·지구·단일 블록·호수 대조와 원천 판본을 가진 영구 연결을 도입했습니다. 재실행 시 기존 검토·확정·해제를 보존하고 같은 후보를 중복 생성하지 않습니다.',
  impact='최초 정비 시 98개 사업 기록에 131개 후보 연결. 자동 연결 보류 110건은 별도 검토 과제로 유지했습니다. 이후 추가 수집 결과와 누적 혼용하지 않습니다.',
  remaining='호수·블록·복합 계약 범위가 다른 기록은 무조건 같은 사업으로 합치지 않습니다. 후보 수는 주택 수가 아닙니다.',
  report_url=REPORT+'EVIDENCE_LINK_REPAIR_20261012.html'),
 dict(key='geumto-a2-split-tenure', title='성남금토 A-2 · 입주 예정월의 부분 유형 연결 누락',
  project_ids=['PRO_57f146c63d9864e7673d3456','PRO_fcc796121d9c033bc356aaad'],
  source_ids=['lh_rent','lh_construction','lh_notice_detail','official_document'], stages=['APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],
  cause='국민임대 438호의 2027-01 예정월은 이미 수집됐지만 633호 건설 기록과 수량이 달랐고 복합 계약 경고로 연결이 제외됐습니다. 공고 상세도 미수집 상태였습니다.',
  action='공식 승인 문서의 438+195=633 구성을 대조하고 국민·영구임대 공고 상세를 수집했습니다. 각 유형의 2027-01 입주 예정 근거를 일부 범위 후보로 연결하고 정정공고 판본도 보존했습니다.',
  impact='성남금토 A-2 건설 633호와 임대 438호 기록. 금회 모집 219호, 유형 총량 438호, 단지 총량 633호를 분리합니다.',
  remaining='예정월은 실제 입주 시작일이 아닙니다. 일부 유형 일정을 전체 단지 실적으로 합산하지 않으며 담당자 확정이 필요합니다.',
  report_url=REPORT+'LH_NOTICE_GAPS_20261012.html'),
 dict(key='lh-notice-detail-gap', title='LH 전체 · 공고 목록과 상세 일정 사이 수집 단절',
  source_ids=['lh_notice','lh_notice_detail','lh_sale','lh_rent','lh_construction'], stages=['SUPPLY','MOVE_IN'],
  cause='목록 공고는 저장했지만 HTML 상세의 입주 예정월·단지 총량·금회 모집량을 추출하지 않아 일정 연결에서 누락됐습니다.',
  action='상세 수집기를 추가하고 원문 해시·판본과 유형 범위를 보존했습니다. 목록 갱신 후 상세 수집이 이어지도록 연결했습니다.',
  impact='1차 상세 53건 확보, 33개 사업 기록에 63개 연결 추가, 예정월이 없던 9개 기록 보완. 후속 확대에서 상세 115건 확보 및 27개 기록에 67개 연결 추가.',
  remaining='HTML에 없는 PDF/HWP 일정, 복수 단지 분해, 취소·정정 계보는 추가 보완 대상입니다. 두 차수 영향 사업 수는 중복 가능해 더하지 않습니다.',
  report_url=REPORT+'APPROVAL_LINK_REPAIR_20261012.html'),
 dict(key='juam-c2-approval', title='과천주암 C2 · 확보된 인허가와 행복주택 기록 미연결',
  project_ids=['PRO_a56077631c9e69c156861889','PRO_bceb35af2280eaa50c810c09','PRO_9ee37f274e85961971980bc6'],
  source_ids=['building_hub','lh_construction','lh_rent'], stages=['APPROVAL'],
  cause='건축HUB에는 C2 허가일 2020-12-29와 1,030호가 있었지만 (뉴스테이)·괄호 표기와 전체/일부 물량 차이 때문에 행복주택 344호가 연결되지 않았습니다. C1은 날짜 없는 선행 추정이 유지됐습니다.',
  action='지구·단일 블록 정규화와 전체 승인에 포함되는 부분 사업 관계를 저장했습니다. C2는 적용 344호/원천 1,030호, C1은 별도 원천 허가일 2020-12-31로 보강했습니다.',
  impact='C2 건설 1,030호 기존 연결 보존, C2 임대 344호 신규 후보, C1 선행 추정 보강.',
  remaining='모집공고를 승인 고시로 대체하지 않습니다. 승인권자·고시번호·최초/변경승인 원문 대조 및 담당자 확정이 남아 있습니다.',
  report_url=REPORT+'APPROVAL_LINK_REPAIR_20261012.html'),
 dict(key='approval-global-normalization', title='전체 인허가 · 검색 정규화 및 선행 추정 보강',
  source_ids=['building_hub','building_hub_incheon','official_document','lh_construction','lh_rent','lh_sale'], stages=['BUSINESS','APPROVAL'],
  cause='후보 검색에 부가표기가 남았고 공식 문서가 후보 풀에서 빠져 있었습니다. 먼저 저장한 선행 추정은 더 강한 날짜 근거가 나와도 유지됐습니다.',
  action='정규화한 지역·지구·블록으로 검색하고 날짜가 검증된 공식 문서를 후보에 포함했습니다. 미검토 선행 추정만 보강하며 담당자 확정·해제는 유지합니다. 동점 후보 정렬도 고정했습니다.',
  impact='292개 사업 기록 점검. 인허가 미연결 148→147개, 날짜 근거 신규·보강 7개, 그중 선행 추정 보강 6개. 재실행 시 새 판본 0건 확인.',
  remaining='남은 미연결 147개는 미허가 또는 0호라는 뜻이 아닙니다. 필지·주소·복수 블록·고시 탐색을 추가 검토해야 합니다.',
  report_url=REPORT+'APPROVAL_LINK_REPAIR_20261012.html'),
 dict(key='lh-notice-category-region-schedule', title='LH 전체 · 신혼희망타운·인천 및 자동 갱신 누락',
  source_ids=['lh_notice','lh_notice_detail','lh_incheon_sale','lh_incheon_rent'], stages=['SUPPLY','MOVE_IN'],
  cause='LH 공고 API가 분양 05·임대 06과 서울·경기 중심으로 구성돼 신혼희망타운 39와 인천 28이 빠졌고 목록 갱신이 수동이었습니다.',
  action='유형 39와 인천을 추가하고 페이지 총건수·중복을 검증했습니다. 목록은 최근 성공 후 1일 간격 자동 수집, 이후 상세 연계로 전환했습니다.',
  impact='3,050→4,018개 공고, 신규 968건. 신혼희망타운 374건 포함. 어린이집 239건·지역 혼합 2건은 원문 보존 후 주택사업 자동 배분 제외.',
  remaining='공고 수를 공급 호수로 환산하지 않습니다. 미수집 첨부·정정 계보·사업 귀속은 계속 검토합니다. 이전 보고서의 인천·자동 갱신 미보완 항목은 이 후속 조치로 보완됐습니다.',
  report_url=REPORT+'APPROVAL_LINK_REPAIR_20261012.html'),
]


RECORDS.extend([
 dict(key='completion-stage-semantics', title='준공 예정일 · 공급 계획으로 중복 표시되던 분류 정비',
  source_ids=['lh_construction','lh_incheon_construction','lh_progress','lh_completion_plan'], stages=['CONSTRUCTION','SUPPLY','MOVE_IN'],
  cause='공사 계약의 예상 준공일이 공급 단계에도 표시되어 분양·모집 일정처럼 해석될 수 있었습니다.',
  action='착공 예정·예상 준공을 건설 단계에만 배치했습니다. 착공 0%→준공 100%의 기간 비례 추정 계획과 실제 원천 공정률을 분리하고 월별 계획을 표시합니다.',
  impact='관련 건설 원천의 사업×단계 표·상세. 공급 단계에는 공급 자료가 있을 때만 표시합니다.',
  remaining='선형 공정계획은 공식 공정표가 아닌 추정입니다. 준공일로 공급일이나 입주 시작일을 대신하지 않습니다.'),
 dict(key='schedule-unknown-semantics', title='고양창릉 S-02 등 · 미정과 항목 미제공 구분',
  source_ids=['lh_sale','lh_rent','lh_incheon_sale','lh_incheon_rent','gh_supply_plan'], stages=['SUPPLY','MOVE_IN'],
  cause='날짜가 비어 있다는 이유만으로 일정 미정 또는 자료 미확보로 뭉뚱그리면, 원문에 항목이 없는 경우와 실제 미정 표기를 구분할 수 없었습니다.',
  action='원문 미정, 원천 공란, 해당 항목 미제공, 원문 확인 전을 별도 상태로 관리합니다. 예정 또는 확보 정보 중 하나만 있으면 확보된 부분만 표시합니다.',
  impact='사업별 공급·입주 일정 칸. 원천 예정월·반기 표기는 원래 정밀도로 보존합니다.',
  remaining='고양창릉 S-02를 포함해 날짜 공란만으로 미정 확정을 하지 않습니다. 실제 입주 현황은 예정자료와 별도 수집 과제입니다.'),
 dict(key='missing-data-classification', title='전체 단계 · 미확보·미계획·수집 방법 미확인을 분리',
  source_ids=['lh_sale','lh_rent','lh_construction','gh_supply_plan','sh_supply_plan','building_hub'],
  stages=['POLICY','BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],
  cause='자료가 보이지 않는 이유가 원천 0건, 아직 계획 미수립, 수집 누락, 사업 연결 실패인지 구분하기 어려웠습니다.',
  action='사업×단계별 원천·목표·확보 근거를 분리하고 담당자 원인 판정을 저장합니다. 기관·단계·사유가 같은 수집 과제를 묶고 사업 선택 시 해당 칸으로 이동하도록 연결했습니다.',
  impact='사업별 수집·연계의 단계 표, 기관별 공통 과제, 담당자 판정 및 상세보기.',
  remaining='미확보는 0이 아닙니다. 아직 계획이 없다는 판정도 담당자·원문 근거가 필요합니다. 자료 수집과 실적 확인을 구분합니다.')
])

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--file'); p.add_argument('--classify-existing', action='store_true'); args=p.parse_args()
    service=HomeService(engine_for(), '/app/data')
    if args.classify_existing:
        print(json.dumps(classify_existing(service),ensure_ascii=False)); raise SystemExit(0)
    records=json.load(open(args.file)) if args.file else RECORDS
    result=[]
    for record in records:
        item={**COMMON, **record}; key=item.pop('key'); result.append(save(service,key,item))
    print(json.dumps(result,ensure_ascii=False))
