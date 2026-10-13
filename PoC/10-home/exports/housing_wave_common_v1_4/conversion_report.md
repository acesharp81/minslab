# HOME → 주택파동 공통규격 v1.4 변환 보고서

입력: `/home/ubuntu/apps/myservice/PoC/10-home/data/exports/home-20261010-live-v3`
스냅샷: `2026-10-10T05:02:48.537173+00:00`

## 파일별 레코드 건수

| 파일 | 행 수 |
|---|---:|
| 정책_policies.csv | 3 |
| 프로그램_programs.csv | 16 |
| 사업_projects.csv | 458 |
| 정책사업연결_links.csv | 257 |
| 사업식별자_identifiers.csv | 2,010 |
| 진행이력_events.csv | 797 |
| 공급물량_units.csv | 279 |
| 원천_sources.csv | 1,220 |
| review_required.csv | 503 |

## 변환 원천 건수

| 원천 유형 | 변환 행 |
|---|---:|
| lh_block_project | 217 |
| lh_completion_plan | 181 |
| lh_movein_plan | 217 |
| lh_supply | 76 |
| policy | 3 |
| project | 241 |
| sh_plan_subtype | 4 |

## 원천 ID별 현재 판본과 사용 행

사용 행은 해당 원천 revision 또는 HOME 연결 행을 한 번 이상 출력에 인용한 수다.

| source_id | 현재 판본 | 사용 행 |
|---|---:|---:|
| building_hub | 180,541 | 0 |
| building_hub_details | 48,951 | 0 |
| building_register | 676,746 | 0 |
| cheongyak | 1,110 | 0 |
| gh_files | 21 | 0 |
| gh_notice | 442 | 0 |
| gh_supply_plan | 2 | 2 |
| gyeonggi_plan_notice_pilot | 1 | 0 |
| kosis_employment | 802 | 0 |
| kosis_household_forecast | 22 | 0 |
| kosis_household_size | 464 | 0 |
| kosis_housing | 464 | 0 |
| legal_dongs | 2,629 | 0 |
| lh_block_location | 273 | 0 |
| lh_completion_plan | 181 | 181 |
| lh_construction | 87 | 78 |
| lh_history | 641 | 0 |
| lh_movein_history | 217 | 217 |
| lh_notice | 3,050 | 0 |
| lh_progress | 566 | 9 |
| lh_reit_progress | 1 | 0 |
| lh_rent | 18 | 18 |
| lh_sale | 34 | 34 |
| lh_stock | 1,815 | 0 |
| lh_supply_history | 76 | 76 |
| molit_demolition | 14 | 0 |
| molit_renewal_inventory | 885 | 0 |
| molit_statistics | 640 | 0 |
| policy_129 | 48 | 48 |
| policy_813 | 1 | 1 |
| policy_907 | 1 | 1 |
| policy_history | 5 | 0 |
| seoul_plan_notice_pilot | 1 | 0 |
| sgis_area | 483 | 0 |
| sh_files | 2,364 | 0 |
| sh_inventory | 18 | 2 |
| sh_redevelopment | 16 | 0 |
| sh_supply_plan | 20 | 4 |
| urban_930 | 52 | 51 |
| vworld | 152 | 0 |
| vworld_district | 35 | 0 |
| vworld_municipality | 56 | 0 |
| HOME:program_policy_links | — | 16 |
| HOME:project_program_links | — | 241 |
| HOME:identity_aliases | — | 241 |

원천 기준일 확보: 505/1,220행; 실제 수집 배치일 확보: 722/1,220행.
HOME 내부 연결·식별자 매핑 행에는 원천 수집 배치가 없어 collected_at을 공란으로 둔다. 공고일·입주예정월도 별도 자료 기준일로 오인하지 않는다.

## 제외·보류 건수

원천 행과 물량 행의 기준이 섞여 있으므로 서로 더하지 않는다.

| 사유:유형 | 건수 |
|---|---:|
| CONFLICT_OR_UNALLOCATED:units | 5 |
| DUPLICATE_BLOCK_EVENT:events | 147 |
| EXCLUDED_PROJECT:project_program | 25 |
| MULTI_SITE_CONTRACT:project | 9 |
| NO_CONFIRMED_PUBLIC_PROJECT_LINK:agency_stock | 2,385 |
| NO_CONFIRMED_PUBLIC_PROJECT_LINK:gh_notice | 442 |
| NO_CONFIRMED_PUBLIC_PROJECT_LINK:lh_notice | 3,050 |
| NO_CONFIRMED_PUBLIC_PROJECT_LINK:lh_stock | 1,815 |
| NO_CONFIRMED_PUBLIC_PROJECT_LINK:permit | 180,541 |
| NO_CONFIRMED_PUBLIC_PROJECT_LINK:plan_notice | 2 |
| NO_CONFIRMED_PUBLIC_PROJECT_LINK:project_report | 1,199 |
| NO_CONFIRMED_PUBLIC_PROJECT_LINK:register | 676,746 |
| NO_CONFIRMED_PUBLIC_PROJECT_LINK:renewal_inventory | 885 |
| OLD_SH_DATASET:sh_plan | 16 |
| PUBLIC_PART_UNVERIFIED:project | 16 |
| PUBLIC_SCOPE_OR_LINK_UNVERIFIED:notice | 1,110 |
| SH_PUBLIC_PART_REVIEW:sh_project | 16 |
| UNSUPPORTED_COMPLETION_PLAN_QUANTITY:units | 181 |
| UNSUPPORTED_MOVE_IN_PLAN_QUANTITY:units | 217 |

## 검토 필요 사유

| 사유 | 항목 수 |
|---|---:|
| BLOCK_MATCH_REVIEW | 123 |
| IDENTITY_ALIAS_REVIEW | 105 |
| JOINT_QUANTITY_UNALLOCATED | 2 |
| MALFORMED_DISTRICT_LABEL | 34 |
| MULTI_SITE_CONTRACT | 9 |
| PUBLIC_NOTICE_MATCH_REVIEW | 195 |
| PUBLIC_PART_UNVERIFIED | 16 |
| SH_PUBLIC_PART_REVIEW | 16 |
| TOTAL_CONFLICT | 3 |

## 검증

CSV 8종의 헤더·UTF-8 BOM, 날짜·숫자 형식, 로컬 ID 중복, 모든 source_ref 및 정책·프로그램·사업 참조 무결성 통과.
DEMO 표기 행은 제출 파일에서 제외; 이번 스냅샷에서 해당 행 0건. 공공 여부·사업 동일성이 불확실한 자료는 검토 대장에 기록.
준공예정·입주예정 호수는 v1.4 물량 유형에 없으므로 물량 CSV에 강제로 넣지 않았다. 실제 입주 호수는 미확보.
정책·프로그램 링크는 HOME의 원천 상태대로 REVIEW_REQUIRED이며 공식 정책 귀속 확정으로 해석하면 안 된다.
주택인허가·건축물대장·재고·일반 민간 분양은 공공주택 사업의 확정 연결이 없어 사업·물량으로 전환하지 않았다.

## 오류

형식·참조 검증 오류 0건. 의미 검토 필요 항목은 review_required.csv 참조.
