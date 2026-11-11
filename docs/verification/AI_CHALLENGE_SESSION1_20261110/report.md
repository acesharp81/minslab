# 더주택·국정온 — 기술 검증 및 심사 증빙 보고서

> 2026 공공 AI 대전환 챌린지 세션 1 | 검증 기준: 2026-11-10 23:58~2026-11-11 KST | 두 서비스 개별 출품용

검토 대상은 **더주택** (PoC/10-home)과 **국정온** (PoC/07-NationalAssembly)이다. 사용자 후속 요청에 따라 낮은 비용으로 가능한 증빙 보강과 로컬 문서 출력 보완을 수행했다. **문광위 추가 수집 시연(N-08)은 별도 세션 대상으로 제외**했다. 운영 DB·설정 변경, 신규 모델 호출, 추가 수집, 외부 전송, 운영 배포는 수행하지 않았다.

가장 강한 제출 근거는 더주택의 실제 사업 동일성 검토·판단 원장·연계 ZIP과 국정온의 실제 알림 전송·주제별 보고서·공식자료 대조다. 반면 더주택의 운영 승인 추출 규칙은 0건이고, 국정온의 실제 외부 공유·업무시간 절감과 신규 위원회 증분비용은 입증되지 않았다. 확인 가능한 강점을 중심으로 신청서 문구를 확정했다. 점수는 실제 심사 결과에 따라 달라지므로 임의의 예상 점수를 산정하지 않는다.

## 검증 기준과 읽는 방법

- ①~⑧: 요청한 표준 답변 양식. H-01~08, N-01~09 총 17개 항목이며 N-08은 범위 제외를 명시한다.
- 현재 운영 조회, 과거 실제 실행, 합성/격리 시험, 이번 로컬 보완 결과를 분리했다. 과거 파일의 수치를 현재 운영 총량으로 바꾸어 해석하지 않는다.
- 저장된 근거의 ID·시각·해시 일치는 사실 확인 수단이다. 의미 정확성·정책 확약·업무 효과와 같은 별도 평가를 대체하지 않는다.
- 코드 링크는 현재 작업공간용이다. ZIP에는 인용 코드 발췌·해시·재현 도구를 포함해 저장소가 없어도 핵심 검증을 읽을 수 있도록 했다.

| 구분 | 검증한 버전·상태 | 근거 |
|---|---|---|
| 소스 | 기준 commit `402b6223d5b1804e6bdcb7c7e180008a450ff6fb`; 미커밋 변경 존재. 인용 줄은 검토 작업트리 기준 | [code-version.json](evidence/code-version.json) · [source-sha256.json](evidence/source-sha256.json) |
| 더주택 운영 API | `poc10-home:missing-dash-20261110`, localhost:18101; health HTTP 200 | [runtime.json](evidence/runtime.json) · [home-health.json](evidence/home-health.json) |
| 국정온 운영 API | `poc07-official-evidence-diff:20261109`, localhost:18070; health HTTP 200 | [runtime.json](evidence/runtime.json) · [national-health.json](evidence/national-health.json) |
| 운영 코드 대조 | 선택한 핵심 파일만 운영 컨테이너와 SHA 대조. 전체 저장소 동일성의 증거는 아님 | [deployed-code-comparison.json](evidence/deployed-code-comparison.json) |
| 이번 국정온 보완 | Markdown 보류 표시·시각 명칭 수정; 로컬 검증 완료, **운영 미배포** | [national-export-only.patch](evidence/national-export-only.patch) · [national-export-focused-tests.txt](evidence/national-export-focused-tests.txt) |

## 질문별 검증 결과

### [H-01] 비정형 주택공급 데이터의 구조적 난제

**① 검증 결론**

확인됨

**② 핵심 답변**

일반 건축 인허가에는 `mgmPmsrgstPk`라는 관리키가 있으나, LH 공고의 `panId`나 보도자료의 `list_no`와 같은 사업을 가리키는 공통키는 아니다. 공고·공사·지구·블록·부분 모집의 관리 단위와 사건 시점이 달라 명칭과 호수만으로 연결할 수 없다. 실제 왕숙2 자료는 A01/A-1BL 및 A03/A-3BL 표기가 함께 나타나며, 공식 착공 1,100호와 본청약 1,498호를 동일 사건으로 환산하지 않고 미해결 상태로 보존했다. 따라서 문서 수집·합산에 사업 동일성, 전체·부분 물량, 계획·실적 검증이 추가로 필요하다.

**③ 소스코드 근거**

- [PoC/10-home/backend/general_building_permits.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/general_building_permits.py:18) · `def parse` · **18행** · 원천 관리키 및 namespace 보존
- [PoC/10-home/backend/lh_notice_detail.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/lh_notice_detail.py:50) · `def parse_detail` · **50행** · LH 공고 항목·공급 범위 추출
- [PoC/10-home/backend/identity.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/identity.py:26) · `def reconcile_identity_links` · **26행** · 지역·지구·블록 단일 후보를 REVIEW 연결로 저장
- 관련 테스트: [PoC/10-home/tests/test_identity.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_identity.py); [PoC/10-home/tests/test_yeonnam_sh_identity.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_yeonnam_sh_identity.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 더주택 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: 원천 3종 이상 비교는 부록 F 참조. 이번 운영 원장의 동일성 별칭 조회와 2026-10-17 왕숙2, 10-20 연남동 검토 기록을 대조했다. [home-identity-examples.json](evidence/home-identity-examples.json) · [home-source-examples.json](evidence/home-source-examples.json) · [home-wangsuk2-20261017.json](evidence/home-wangsuk2-20261017.json) · [home-yeonnam-20261020.json](evidence/home-yeonnam-20261020.json)
- 데이터 기준시각·입력 범위: home_identity_alias 전체 행; 고유 사업 수·자동 연결 정확도와 다름; 2026-11-11 00:00 KST 전후; 운영 PostgreSQL.
- 확인한 결과: 별칭 4,361행: CONFIRMED 99행, REVIEW 4,262행; 원천 비교 4유형. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 동일성 별칭 상태 및 실제 원천 사례
- 측정값과 단위: 별칭 4,361행: CONFIRMED 99행, REVIEW 4,262행; 원천 비교 4유형
- 측정 대상·분모: home_identity_alias 전체 행; 고유 사업 수·자동 연결 정확도와 다름
- 비교 기준: 기관 간 관리 단위와 원천별 필드를 비교
- 측정 방법: 읽기 전용 SQL GROUP BY와 보존된 실제 자료 대조
- 측정 환경과 시각: 2026-11-11 00:00 KST 전후; 운영 PostgreSQL
- 제한사항: REVIEW에는 단순 원천 앵커도 포함되므로 4,262행 모두를 연결 실패로 계산하지 않음

**⑥ 심사에서 사용할 수 있는 설명**

더주택은 원천별 식별자와 지구·블록·물량 범위를 함께 대조해 주택공급 자료를 연결한다. 일반 인허가 관리번호와 모집공고 번호의 관리 단위가 다름을 확인했으며, 왕숙2의 공식 착공 실적과 본청약 물량처럼 사건과 범위가 다른 수치를 별도로 보존한다. 동일성이 불명확한 자료는 검토 상태로 남겨 단순 합산에 따른 중복·오인 연결을 줄이는 구조를 갖췄다.

**⑦ 미확인 사항 및 반대 근거**

모든 공공데이터에 식별키가 없는 것은 아니다. 일반 인허가 관리키의 존재가 확인된다. 왕숙2 공식 실적의 구성 블록은 보존된 검토에서 미해결이며, 이번에는 새 원천 수집으로 해소하지 않았다.

**⑧ 추가 검증이 필요한 사항**

왕숙2 공식 1,100호의 구성 블록·실적 인정일이 명시된 자료 1건을 확보해 기존 A01/A03 원장과 대조한다. 원천 추가 수집은 허용된 수집 범위에서 수행한다.

### [H-02] AI 추출 알고리즘 개선과 규칙 축적

**① 검증 결론**

부분 확인

**② 핵심 답변**

AI의 실패 진단, 제한된 CSS 본문 규칙 제안, 사람의 시험·승인, 승인 규칙 조회·적용 경로는 구현돼 있다. 규칙은 `algorithm_rules`에 범위·판본과 함께 저장되며, `extract_approved`의 본문 추출에는 생성형 AI 호출이 없다. 그러나 이번 운영 SQLite 조회에서 규칙·시험·승인·검토이력 테이블은 모두 0건이므로 실제 운영 승인 규칙의 축적 실적은 확인되지 않았다. 개발 과정의 날짜 파서 개선은 합성 16사례 시험으로 확인되며 운영 실자료의 개선 실적과 구분해야 한다.

**③ 소스코드 근거**

- [PoC/10-home/backend/ai_agent_workflows.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/ai_agent_workflows.py:40) · `class RuleProposal` · **40행** · 제안 응답 계약
- [PoC/10-home/backend/algorithm_review.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/algorithm_review.py:109) · `def validate` · **109행** · 본문 전후 및 같은 경로 정상 자료 회귀 검증
- [PoC/10-home/backend/algorithm_review.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/algorithm_review.py:158) · `def decide` · **158행** · 명시적 승인·충돌 검사·규칙 저장
- [PoC/10-home/backend/algorithm_review.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/algorithm_review.py:197) · `def extract_approved` · **197행** · 모델 호출 없는 로컬 규칙 적용·기본 추출 복귀
- 관련 테스트: [PoC/10-home/tests/test_algorithm_review.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_algorithm_review.py); [PoC/10-home/tests/test_dataset_slices.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_dataset_slices.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 더주택 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: [home-ai-ledger.json](evidence/home-ai-ledger.json)에서 운영 테이블 건수 확인. [home-algorithm-20261102.md](evidence/home-algorithm-20261102.md)에는 11월 2일도 승인 규칙 0건으로 기록. 합성 날짜 파서 개선은 `PoC/10-home/docs/evidence/AI_AUTOMATION_FINAL_CHECK_20261029/README.md`와 `parser_*.py`, `fixed_cases.json`, `results.json` 참조.
- 데이터 기준시각·입력 범위: 운영 알고리즘 4개 테이블; 별도 합성 날짜 사례 16개; 운영 조회 11-11 00시경; 합성 모델시험 10-29; 신규 모델 호출 없음.
- 확인한 결과: 운영 규칙·시험·승인·이력 각 0건; 합성 baseline 12/16, Solar 15/16→16/16. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 운영 규칙 축적과 합성 개선시험
- 측정값과 단위: 운영 규칙·시험·승인·이력 각 0건; 합성 baseline 12/16, Solar 15/16→16/16
- 측정 대상·분모: 운영 알고리즘 4개 테이블; 별도 합성 날짜 사례 16개
- 비교 기준: 개선 전 파서와 고정 정답 비교
- 측정 방법: SQLite mode=ro 집계; 기존 합성 시험 기록 및 이번 격리 회귀시험
- 측정 환경과 시각: 운영 조회 11-11 00시경; 합성 모델시험 10-29; 신규 모델 호출 없음
- 제한사항: 16/16은 동일 정답 재시험이며 독립 holdout·운영 정확도·비용절감률이 아님

**⑥ 심사에서 사용할 수 있는 설명**

AI가 실패 원인을 진단하고 제안한 본문 추출 규칙을 사람이 시험·승인한 뒤 재사용하는 경로를 구현했다. 승인 규칙을 적용하는 본문 추출은 모델 호출 없이 실행되며, 분석·업무 판단 에이전트의 호출과 구분된다. 합성 파서 개선과 격리 승인·적용 시험은 확인했으나, 현재 운영 원장에는 승인 규칙이 없어 실제 규칙 축적 성과는 후속 검증 대상이다.

**⑦ 미확인 사항 및 반대 근거**

승인 가능 범위는 HTML 본문 CSS 규칙이며 운영 소스코드·API 수집기·날짜·물량 규칙의 자율 수정 기능이 아니다. 뒤이은 비정형 분석은 모델을 호출할 수 있다. “AI로 계속 자동 개선해 비용이 0원”이라는 표현은 불가하다.

**⑧ 추가 검증이 필요한 사항**

이미 저장된 실패 HTML 1건과 동일 경로 정상 HTML 2건을 임시 원장에 복제해 제안→승인→반복 추출을 재현하고 추출 단계 호출 수 0을 기록한다. 운영 승인 자체는 이번 검증에서 실행하지 않는다.

### [H-03] 3개 AI 에이전트 협업과 실제 행정업무 수행

**① 검증 결론**

부분 확인

**② 핵심 답변**

알고리즘은 실패·개선안을, 수집은 원문·분석 후보를, 업무담당자는 근거 대조와 Yes/No/HOLD 및 집행 결과를 남기며 하나의 큐에서 순차 처리한다. 업무담당자의 별도 검증 요청은 동일 선택 모델을 다시 호출하는 방식이며 서로 다른 두 모델의 독립 판정은 아니다. 11월 5일 실기록에서 비주택·재계약 안내 2건 제외, 시흥거모 기존 연결 재확인, 근거 부족 보류와 DB 상태 변경을 확인했다. 최근 전체 작업 하나는 332대상 검토를 완료했지만 318대상은 보류였고, 다음 작업은 예산으로 중지돼 신규 사업·정책·실적까지 전부 자동 집행됐다고 할 수 없다.

**③ 소스코드 근거**

- [PoC/10-home/backend/ai_agent_workflows.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/ai_agent_workflows.py:98) · `def process` · **98행** · 역할별 입력·작업·결과
- [PoC/10-home/backend/ai_officer_decisions.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/ai_officer_decisions.py:301) · `def execute` · **301행** · 결정과 별도 모델 검증·코드 검증
- [PoC/10-home/backend/ai_officer_decisions.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/ai_officer_decisions.py:231) · `def apply` · **231행** · 자료·사업·정책·단계 저장 경로
- [PoC/10-home/backend/officer_campaign.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/officer_campaign.py:221) · `def _advance` · **221행** · 작업목록·실저장 대조·보류·재개
- 관련 테스트: [PoC/10-home/tests/test_ai_agents.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_ai_agents.py); [PoC/10-home/tests/test_algorithm_review.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_algorithm_review.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 더주택 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: 실행 `4a67c892-634f-42de-9dbc-e787af6b27fa`: GPT-5.4 6호출, 18,140토큰. No: `DOC_63aa5d0ed29ad8e77b39764d` REVIEW→EXCLUDED; Yes: `DOC_87cca7787d542e5eb6512549` APPROVED→APPROVED; HOLD: `DOC_734a618c7ff3c2ec53a62f89` REVIEW→HOLD. [home-officer-20261105.json](evidence/home-officer-20261105.json) · [home-ai-ledger.json](evidence/home-ai-ledger.json)
- 데이터 기준시각·입력 범위: 전체 작업 a171ae54…의 문서 192+단계후보 140; 후속 5846e51c…; 11-05 과거 실기록; 11-11 00시경 현재 SQLite 조회.
- 확인한 결과: 완료 작업 332대상: Yes 3, No 11, HOLD 318; 후속 작업 335대상 중 155검토·180남음. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 최종 판단과 실제 반영
- 측정값과 단위: 완료 작업 332대상: Yes 3, No 11, HOLD 318; 후속 작업 335대상 중 155검토·180남음
- 측정 대상·분모: 전체 작업 a171ae54…의 문서 192+단계후보 140; 후속 5846e51c…
- 비교 기준: 결론을 실저장 원장과 대조; Yes를 신규 실적과 구분
- 측정 방법: 기존 검증 JSON의 before/after 및 현재 campaign summary 읽기
- 측정 환경과 시각: 11-05 과거 실기록; 11-11 00시경 현재 SQLite 조회
- 제한사항: 동일 문서 재검토 중복 가능; 11-05 사업·정책 목표·실적·매핑 불변; 전체 100%는 승인율이 아님

**⑥ 심사에서 사용할 수 있는 설명**

더주택은 알고리즘·수집·업무담당자의 역할과 판단 이력을 분리하고, 업무담당자의 Yes·No·보류를 실제 저장 상태와 대조한다. 운영 기록에서 비주택 자료 제외와 근거 부족 보류를 확인했으며, 기존 사업 연결 재확인도 신규 실적 증가와 구분한다. 전체 검토 완료 후에도 보류를 남기고 예산 중지 시 미처리 목록을 보존해 담당자가 진행 범위와 한계를 추적할 수 있다.

**⑦ 미확인 사항 및 반대 근거**

위임 AI 판단은 실제 기관 담당자의 승인이나 외부 인증이 아니다. 별도 정책·단계 효과는 각각 검증 후 처리하며 핵심 결론 저장 뒤 후속 처리가 남을 수 있다. 최근 상태 PAUSED_BUDGET, Yes 0·No 7·HOLD 148·미처리 180을 완료로 바꾸어 설명하면 안 된다.

**⑧ 추가 검증이 필요한 사항**

새 호출 없이 완료 작업의 Yes 3건에 대해 effect.kind와 before/after를 한 장으로 대조한다. 신규 PROJECT/POLICY/STAGE 효과가 실제 존재하는지 별도 표본을 확보하고 없으면 자료 처리 성과로 범위를 제한한다.

### [H-04] 주택공급 정책 추진현황의 실질적 가시화

**① 검증 결론**

부분 확인

**② 핵심 답변**

정책→프로그램→사업, 사업화·인허가·건설·공급·입주를 연결하는 집계와 보고서 출력이 구현돼 있다. 11월 10일 생성된 실제 전달 자료에서 9·7 정책 목표 1,350,000호, 식별 배정 91,849호, 미식별 유보 1,258,151호를 확인했으며 이는 착공 완료량이 아니다. 집계 계약에 `mapping_review_included=true`가 있어 화면 값을 전부 확정 사업의 공식 실적으로 설명해서는 안 된다. 시흥거모 S1·안산신길2 A6·과천지식정보타운 S-12는 원천 공고와 연결되지만 모집 물량과 계약·입주 실적을 구분해야 한다.

**③ 소스코드 근거**

- [PoC/10-home/backend/policy_delivery.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/policy_delivery.py:94) · `def _build_delivery` · **94행** · 사업군·원천사건·수동값·추정 범위 결합
- [PoC/10-home/backend/policy_delivery_comparison.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/policy_delivery_comparison.py:10) · `def comparison_index` · **10행** · 목표·실적·예측 대조
- [PoC/10-home/backend/policy_delivery_view.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/policy_delivery_view.py:33) · `def screen_view` · **33행** · 정책·프로그램 표시 투영
- 관련 테스트: [PoC/10-home/tests/test_policy_delivery_comparison.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_policy_delivery_comparison.py); [PoC/10-home/tests/test_policy_delivery_view.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_policy_delivery_view.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 더주택 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: [home-projects-policy-delivery-97.json](evidence/home-projects-policy-delivery-97.json) · [home-S1-view-policy.json](evidence/home-S1-view-policy.json) · [home-policy-screen-20261023.png](evidence/home-policy-screen-20261023.png) · [home-policy-audit-20261103.json](evidence/home-policy-audit-20261103.json). 화면은 10-23 과거 캡처, 집계 JSON은 11-10 17:53 KST 생성 ZIP의 원본. 사업별 예시·사건·상태는 부록 G에 정리.
- 데이터 기준시각·입력 범위: 해당 9·7 정책 응답의 각 컬렉션; 전국 모든 사업이 아님; 자료 until 2026-11-10 17:53:01 KST; 화면 예시 10-23.
- 확인한 결과: 목표 1,350,000호; 배정 91,849호; 유보 1,258,151호; 표시 identification_pct 6.8036%; cohorts 77개·management_projects 232개. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 정책 식별 범위·사업 사례
- 측정값과 단위: 목표 1,350,000호; 배정 91,849호; 유보 1,258,151호; 표시 identification_pct 6.8036%; cohorts 77개·management_projects 232개
- 측정 대상·분모: 해당 9·7 정책 응답의 각 컬렉션; 전국 모든 사업이 아님
- 비교 기준: 목표 = 배정+유보; 식별 비율과 달성률 구분
- 측정 방법: 기존 ZIP JSON 직접 재계산·원천 URL 대조
- 측정 환경과 시각: 자료 until 2026-11-10 17:53:01 KST; 화면 예시 10-23
- 제한사항: 77과 232는 서로 다른 집합; 원문 미확보·범위 불일치 및 검토 상태가 남음

**⑥ 심사에서 사용할 수 있는 설명**

정책 목표와 프로그램·사업의 단계별 진행 자료를 연결해 부족한 식별 범위와 근거를 함께 확인할 수 있다. 9·7 정책의 실제 데이터에서 목표, 사업 배정, 미식별 유보를 구분하고 모집공고를 계약·입주 실적과 분리한다. 계획·추정·검토 상태를 보존해 수치의 해석 범위를 드러내며, 정책 보고서와 원천 연결 자료를 통해 개별 수치의 확인 경로를 제공한다.

**⑦ 미확인 사항 및 반대 근거**

전체 정책 목표에 해당하는 모든 사업을 확보한 상태가 아니다. 11-03 공급 37,772호에도 검토 연결 1,424호가 포함됐다. 이번에 정책 1개·사업 3개의 최신 화면을 각각 새로 촬영하지는 않았으며 현재 데이터와 과거 화면은 기준시각이 다르다.

**⑧ 추가 검증이 필요한 사항**

현재 보유 API 결과와 동일 기준시각으로 정책 1개 및 사업 3개 화면을 저장하고, 확정·검토·추정 범례와 분모를 함께 캡처한다. 미식별 유보는 정책 실적 부족으로 해석하지 않도록 설명을 붙인다.

### [H-05] 실제 업무 효율성 및 기술적 경제성

**① 검증 결론**

부분 확인

**② 핵심 답변**

반복 수집 배치·AI 호출·토큰 장부는 확인되지만 수작업과 동일 조건으로 비교한 업무시간 절감률은 없다. 11월 3~10일 수집 원장은 75개 source_id에서 성공 1,865배치·실패 151배치를 기록했으며 문서 처리 건수와는 다르다. 같은 기간 AI 장부에는 GPT-5.4 및 Solar의 완료 호출·거절·비용 미확정 기록이 남아 서비스 전체를 무비용으로 설명할 수 없다. 규칙 기반 본문 추출의 호출 부재와 에이전트·검색·저장·운영 비용을 분리해야 한다.

**③ 소스코드 근거**

- [PoC/10-home/backend/ai_collection_models.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/ai_collection_models.py:148) · `def invoke` · **148행** · 모델 요청·사용량·비용 정산
- [PoC/10-home/backend/ai_agents_store.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/ai_agents_store.py:63) · `def economics` · **63행** · 역할별 경제성 집계
- [PoC/10-home/backend/algorithm_review.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/algorithm_review.py:197) · `def extract_approved` · **197행** · 규칙 본문 추출
- 관련 테스트: [PoC/10-home/tests/test_ai_agents.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_ai_agents.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 더주택 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: [home-batches.json](evidence/home-batches.json) · [home-ai-ledger.json](evidence/home-ai-ledger.json). 비용은 운영 원장의 기록액이며 실제 제공사 청구·할인·무제한 계약의 청구액을 조회한 결과가 아니다.
- 데이터 기준시각·입력 범위: 2026-11-03 00:00 이상~11-11 00:00 미만 KST의 HOME 호출 원장; 운영 기록을 11-11 00시경 조회; 새 모델 호출 없음.
- 확인한 결과: GPT-5.4 완료 22호출·86,566토큰·$0.2987025; Solar 완료 1,738호출·7,605,311토큰·$3.0653943; Solar REJECTED 330, UNKNOWN_COST 55. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 수집 실행·AI 호출·토큰·기록 비용
- 측정값과 단위: GPT-5.4 완료 22호출·86,566토큰·$0.2987025; Solar 완료 1,738호출·7,605,311토큰·$3.0653943; Solar REJECTED 330, UNKNOWN_COST 55
- 측정 대상·분모: 2026-11-03 00:00 이상~11-11 00:00 미만 KST의 HOME 호출 원장
- 비교 기준: 수작업 또는 동일 품질 직접 모델 추출 비교: 미측정
- 측정 방법: 배치 시간 차 및 호출 원장 상태별 SUM; building_hub 성공 8배치 평균 109.06752초
- 측정 환경과 시각: 운영 기록을 11-11 00시경 조회; 새 모델 호출 없음
- 제한사항: 합계 비용을 실청구로 보지 않음; UNKNOWN_COST 토큰 77,420·기록액 $0.0349485 별도; 문서당·직원당 절감률 미측정

**⑥ 심사에서 사용할 수 있는 설명**

더주택은 수집 실행과 AI 호출을 별도 원장으로 기록해 규칙 처리와 모델 분석의 비용을 구분할 수 있다. 최근 8일간 수집 성공·실패 배치 및 모델별 호출·토큰 사용을 확인했고, 규칙 본문 추출에는 모델 호출이 없음을 코드로 검증했다. 다만 실제 청구액과 표준 단가 기록액은 다르며, 수작업 대비 업무시간·비용 절감률은 아직 계측하지 않았다.

**⑦ 미확인 사항 및 반대 근거**

성공 배치 수는 추출 성공 문서 수가 아니다. 동일 데이터·동일 품질·동일 환경의 직접 모델 처리 비교가 없고 사람의 검토시간도 미측정이다. AI 사용 원장의 REJECTED는 유료 요청 전 차단일 수 있어 전체를 공급자 호출로 더하지 않는다.

**⑧ 추가 검증이 필요한 사항**

기존 원문 20건을 규칙만으로 오프라인 재처리해 처리시간·성공 문서·검토 필요 건수를 기록한다. 직접 모델 비교와 사람 작업시간 비교는 별도 승인·동일 정답 기준으로 실시한다.

### [H-06] 타 시스템 연계를 위한 데이터 추출 기능

**① 검증 결론**

확인됨

**② 핵심 답변**

`home-slices/1` 전체·변경분 생성, manifest·파일 해시·행 수·허용 필드 검증과 관리자 다운로드가 구현돼 있다. 기존 운영 작업 `8e5d063476864013ac7a577efd51c822`의 ZIP을 별도 임시 수신 폴더에서 원본 검사기로 읽어 검증했다. 31종은 기관 수가 아닌 데이터 슬라이스 종류이며, 106개 manifest 대상 파일에 manifest 자체를 더해 ZIP 항목은 107개다. 실제 수신 DB의 이전 판이 없으므로 운영 변경분 병합·외부 시스템 화면 대조 완료까지는 입증되지 않는다.

**③ 소스코드 근거**

- [PoC/10-home/backend/dataset_slices.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/dataset_slices.py:130) · `def snapshot` · **130행** · READ ONLY·REPEATABLE READ 스냅샷
- [PoC/10-home/backend/dataset_slices.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/dataset_slices.py:327) · `def build` · **327행** · 파일 생성·검증·ZIP 봉인
- [PoC/10-home/backend/app.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/app.py:1298) · `def dataset_slice_start` · **1298행** · 관리자 생성·상태·다운로드 API
- [PoC/10-home/backend/slice_contract/tools/ledger/home-slice.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/slice_contract/tools/ledger/home-slice.py:486) · `def read_package` · **486행** · 수신측 해시·행 수 검사
- 관련 테스트: [PoC/10-home/tests/test_dataset_slices.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_dataset_slices.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 더주택 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: [제출용 비식별 ZIP](evidence/home-slices-submission-redacted.zip) · [home-slices-state.json](evidence/home-slices-state.json) · [home-slices-manifest.json](evidence/home-slices-manifest.json) · [home-slices-verification.json](evidence/home-slices-verification.json). 이번 검증은 기존 ZIP 재사용이며 새 운영 생성 요청·외부 업로드 없음. `api/project-collection/slices/jobs/{job_id}/download`는 완료된 관리자 작업만 제공.
- 데이터 기준시각·입력 범위: 작업 8e5d0634…의 변경분 ZIP 1개; 모든 31슬라이스 행 검증; since 2026-10-22 00:00 KST; until 11-10 17:53:01.171014 KST; 재검증 11-11 00:02.
- 확인한 결과: 31슬라이스; manifest 파일 106개·ZIP 항목 107개; 39,359행; 28,390,282바이트; 검사 PASS. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 실제 ZIP 호환성
- 측정값과 단위: 31슬라이스; manifest 파일 106개·ZIP 항목 107개; 39,359행; 28,390,282바이트; 검사 PASS
- 측정 대상·분모: 작업 8e5d0634…의 변경분 ZIP 1개; 모든 31슬라이스 행 검증
- 비교 기준: 제공된 원본 home-slice.py 규격·manifest
- 측정 방법: 격리 임시 폴더 read_package + Slice.check_row; 전체·변경분 apply는 모의 회귀시험
- 측정 환경과 시각: since 2026-10-22 00:00 KST; until 11-10 17:53:01.171014 KST; 재검증 11-11 00:02
- 제한사항: 운영 변경분을 이전 수신판에 실제 병합하지 않음; 31종이 모든 운영 테이블이나 31기관을 뜻하지 않음

**⑥ 심사에서 사용할 수 있는 설명**

더주택은 원천 판본과 연결·감사 자료를 home-slices/1 규격의 전체 또는 변경분 ZIP으로 추출한다. 실제 생성 ZIP의 31종 슬라이스를 독립된 임시 수신 환경에서 읽어 파일 해시·행 수·허용 필드를 검증했다. 기준시각·판본·삭제 정보를 함께 전달하고 개인정보 제거 절차를 적용하며, 실제 외부 수신 DB 병합과 화면 대조는 별도 연계 검증 단계로 구분한다.

**⑦ 미확인 사항 및 반대 근거**

전체 패키지와 변경분의 복원 회귀시험은 모의 데이터다. 실제 운영 ZIP은 변경분이며 수신 기준판 없이는 단독 완전 복원이 불가능하다. 수신기관 운영 연계나 직접 업로드가 완료됐다는 증거는 없다. 기존 실패 작업에는 서비스 재시작·source-summary 조회 실패도 존재한다.

**⑧ 추가 검증이 필요한 사항**

수신 측에서 기준판을 준비한 후 제공 도구 apply로 병합하고 golden/API의 정책·사업 수치와 대조한다. 이번 패키지의 SHA-256과 실행 명령은 부록 H에 제공한다.

### [H-07] 공통 사업 식별키 부재의 확인 및 표준화 방향

**① 검증 결론**

확인됨

**② 핵심 답변**

검토 대상 원천에는 각자의 공고·인허가 식별자가 있지만 사업·블록·단계 사건을 기관 간 연결하는 공통키는 확인되지 않았다. 연남동 공공임대주택은 SH 자료의 위치·물량과 대조해 기존 사업 ID를 재사용했고 8호를 다시 더하지 않았다. 왕숙2 및 노원구 도전숙 사례는 사업 범위·주소·구성 블록의 부족으로 미해결·보류 근거가 남아 있다. 아래 표준화안은 이 개발 과정에서 제안하는 개선 방향이며 이미 운영 중인 국가 표준이라는 뜻은 아니다.

**③ 소스코드 근거**

- [PoC/10-home/backend/db.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/db.py:106) · `class IdentityAlias` · **106행** · 원천별 ID와 공통 후보 사업 연결
- [PoC/10-home/backend/identity.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/identity.py:20) · `def grouping_key` · **20행** · 지역·지구·블록 후보
- [PoC/10-home/backend/ai_officer_decisions.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/ai_officer_decisions.py:149) · `def identity` · **149행** · 인용·사업 식별 검증
- [PoC/10-home/scripts/confirm_yeonnam_sh_identity_20261020.py](/home/ubuntu/apps/myservice/PoC/10-home/scripts/confirm_yeonnam_sh_identity_20261020.py:32) · `def verify_pdf` · **32행** · 연남동 공식 자료 대조 스크립트
- 관련 테스트: [PoC/10-home/tests/test_identity.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_identity.py); [PoC/10-home/tests/test_yeonnam_sh_identity.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_yeonnam_sh_identity.py); [PoC/10-home/tests/test_split_block_identity.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_split_block_identity.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 더주택 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: [home-yeonnam-20261020.json](evidence/home-yeonnam-20261020.json) · [home-yeonnam-source-20261020.json](evidence/home-yeonnam-source-20261020.json) · [home-identity-examples.json](evidence/home-identity-examples.json) · [home-officer-20261105.json](evidence/home-officer-20261105.json). 연남동 사업 `PRO_b8e9b07eb43ee60a807ec231`, SH 근거 `DOC_2587e87ac1f72a71cd250383`, 원문 79쪽.
- 데이터 기준시각·입력 범위: 2026-10-20 해당 보정 작업의 보호 대상; 10-20 보존 결과; 이번 read-only 조회.
- 확인한 결과: 연남동 신규 사업 0·신규 실적 사건 0·추가 물량 0호; 보호 레코드 3,111개 전후 해시 동일. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 중복 방지와 기존값 보존
- 측정값과 단위: 연남동 신규 사업 0·신규 실적 사건 0·추가 물량 0호; 보호 레코드 3,111개 전후 해시 동일
- 측정 대상·분모: 2026-10-20 해당 보정 작업의 보호 대상
- 비교 기준: 보정 전후 원장·정책 매핑
- 측정 방법: 기존 applied.json의 변경·불변 항목 및 해시 검토
- 측정 환경과 시각: 10-20 보존 결과; 이번 read-only 조회
- 제한사항: 이번에는 과거 보정 스크립트를 재실행하지 않음; 전 기관 공통키 부재를 전수 조사한 것은 아님

**⑥ 심사에서 사용할 수 있는 설명**

기관별 원천 식별자는 유지하면서 사업·지구·블록·사건 범위를 대조하는 연결 구조를 구현했다. 연남동 사례에서는 공식 자료를 추가해 기존 사업 ID를 재사용하고 이미 반영된 8호를 중복 가산하지 않았음을 검증 기록으로 확인했다. 사업 공통키와 원천 식별자, 단계 사건·물량·판본을 함께 제공하는 API 표준화 방향을 제안하되 현행 국가 표준과 구분한다.

**⑦ 미확인 사항 및 반대 근거**

홈 내부 HPR_/PRO_ ID는 서비스 내부 식별자다. 표준 도입 효과는 설계상 기대이며 실측 성과가 아니다. 원천 ID가 있어도 사업 범위가 공사계약·블록·금회 모집으로 다르면 별도 관계 정의가 필요하다.

**⑧ 추가 검증이 필요한 사항**

개선안: project_uid·source_namespace/native_id·district_uid/block_uid·주소/필지·관계유형; event_uid·stage·event_date/observed_at·planned/actual·quantity/unit/scope·valid_from/to·revision·supersedes·source_url/hash를 분리한다. 서로 다른 기관 자료 3건으로 매핑 가능성을 먼저 검토한다.

### [H-08] 서비스 완성도 신뢰성 재사용성

**① 검증 결론**

부분 확인

**② 핵심 답변**

원문·판본·감사 원장, 동일성 보류, 사람 변경과의 충돌 방어, 작업 중지·재개 및 역할별 모델 선택이 구현돼 있다. 이번 운영 건강검사는 HTTP 200이었고 추출·규칙·동일성 격리 시험 41개가 통과했다. 그러나 최근 전체 작업은 예산으로 중지됐으며 전체 원천 판본 집계 조회도 15초 제한으로 취소되어 모든 경로의 안정성을 입증한 것은 아니다. 설치·백업 문서와 기존 복구 기록은 존재하지만 이번에 복원훈련·장기 가용성·모든 모델 교체를 검증하지 않았다.

**③ 소스코드 근거**

- [PoC/10-home/backend/db.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/db.py:281) · `def upsert_revision` · **281행** · 원천 해시·이전 판본 보존
- [PoC/10-home/backend/officer_campaign.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/officer_campaign.py:295) · `def advance` · **295행** · 작업 재개·저장 결과 대조
- [PoC/10-home/backend/ai_agents_store.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/ai_agents_store.py:25) · `def configure` · **25행** · 역할 설정 저장
- [PoC/10-home/backend/ai_collection_models.py](/home/ubuntu/apps/myservice/PoC/10-home/backend/ai_collection_models.py:148) · `def invoke` · **148행** · 제공사·모델 어댑터 및 한도
- 관련 테스트: [PoC/10-home/tests/test_dataset_slices.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_dataset_slices.py); [PoC/10-home/tests/test_algorithm_review.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_algorithm_review.py); [PoC/10-home/tests/test_identity.py](/home/ubuntu/apps/myservice/PoC/10-home/tests/test_identity.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 더주택 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: [home-health.json](evidence/home-health.json) · [runtime.json](evidence/runtime.json) · [home-offline-tests.txt](evidence/home-offline-tests.txt) · [home-ai-ledger.json](evidence/home-ai-ledger.json) · [deployed-code-comparison.json](evidence/deployed-code-comparison.json). API 실행 이미지 `poc10-home:missing-dash-20261110`; 핵심 4개 파일은 배포 파일과 작업트리 해시 일치.
- 데이터 기준시각·입력 범위: 선별 3개 테스트 파일; 해당 운영 컨테이너·캠페인; 상태 11-10 23:58 KST; 회귀 11-11 00시대.
- 확인한 결과: HTTP 200; 선별 회귀 41 passed·경고 1; 완료 332대상 작업과 중지 335대상 작업 공존. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 현재 가동·회귀·중단 상태
- 측정값과 단위: HTTP 200; 선별 회귀 41 passed·경고 1; 완료 332대상 작업과 중지 335대상 작업 공존
- 측정 대상·분모: 선별 3개 테스트 파일; 해당 운영 컨테이너·캠페인
- 비교 기준: 기대 무결성·접근 제어·규칙 승인 조건
- 측정 방법: 상태 GET, 이미지·파일 해시, 임시 SQLite 회귀시험
- 측정 환경과 시각: 상태 11-10 23:58 KST; 회귀 11-11 00시대
- 제한사항: 회귀는 합성·모의 데이터이며 SLA·장애율·실운영 복원시간 미측정

**⑥ 심사에서 사용할 수 있는 설명**

더주택은 원천 판본과 감사 이력을 보존하고, 불명확한 판단은 보류하며 중단된 작업의 미처리 목록을 유지한다. 현재 운영 상태와 핵심 코드의 배포 일치를 확인했고, 데이터 추출·규칙 승인·동일성 관련 격리 시험 41개가 통과했다. 역할별 모델 설정과 원천별 수집 모듈은 재사용 기반을 제공하되, 장기 가용성과 신규 기관 적용 범위는 별도 검증이 필요하다.

**⑦ 미확인 사항 및 반대 근거**

11-02 의존성 누락에 따른 배포 실패·원복 이력이 있다. 최근 예산 중지는 데이터 손상과 별개지만 미완료 업무를 남긴다. 역할 모델 허용 목록은 전체 모델 호환성 보증이 아니며 현재 선택값과 실제 호출 모델은 실행 기록으로 확인해야 한다.

**⑧ 추가 검증이 필요한 사항**

기존 백업 1개를 외부 호출이 차단된 임시 DB에 복원해 원장·해시·보류 작업을 대조한다. 서버의 실부하·메모리·디스크·복구시간은 사전에 범위를 정해 짧게 계측한다.

### [N-01] 실시간 회의 모니터링의 업무 혁신

**① 검증 결론**

확인됨

**② 핵심 답변**

관심 문구·범위를 등록한 후 새로 들어온 발언을 감지하고 화면 알림·선택형 카카오 전송·주제 종료 및 누적 요약으로 이어지는 경로가 있다. 실제 예결위 제7차 회의의 비시험 알림에서 수신 판본, 알림 생성, 카카오 SENT 시각을 확인했다. 발언 원문과 보고서를 다시 열 수 있으므로 상시 시청을 보조하는 업무 흐름은 입증된다. 다만 대상 밖 회의, 수집 누락, 자막 오인식·표현 차이, 카카오 실패가 있으며 방송 발언 자체의 절대시각과 업무시간 절감률은 확보하지 못했다.

**③ 소스코드 근거**

- [PoC/07-NationalAssembly/backend/app/services/watch_matcher.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/watch_matcher.py:37) · `def match_watch_rule` · **37행** · 관심 문구·제외 조건 감지
- [PoC/07-NationalAssembly/backend/app/services/watch_lifecycle.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/watch_lifecycle.py:14) · `def official_recess_status` · **14행** · 주제 전환·종료 생명주기
- [PoC/07-NationalAssembly/backend/app/db/watch_delivery_repository.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/db/watch_delivery_repository.py:10) · `class WatchDeliveryRepository` · **10행** · 전송 원장
- [PoC/07-NationalAssembly/backend/app/main.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/main.py:1719) · `def ended_live_broadcast_transcript` · **1719행** · 저장 원문 확인
- 관련 테스트: [PoC/07-NationalAssembly/backend/tests/test_summary_cache.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/tests/test_summary_cache.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 국정온 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: 회의 `532ab55a-12e2-42f4-b425-ec2401139a33`, 제439회 제07차 예산결산특별위원회. 감지 `44a2a49f-4226-46d8-9188-e070620c039b`: 11-10 23:53:41.094 최초 수신, 23:53:56.522 판본 수신, 23:54:19.059 알림 생성, 23:54:45.009 카카오 SENT(KST). [national-watch-samples.json](evidence/national-watch-samples.json) · [national-watch-counts.json](evidence/national-watch-counts.json)
- 데이터 기준시각·입력 범위: is_test=false 원장; 화면·카카오 채널 행은 고유 알림 수와 다름; 11-11 00:00 KST 조회; 표본 사건 11-10 23:53~23:54.
- 확인한 결과: 표본 1건 판본 수신→알림 생성 22.537초, 생성→카카오 SENT 25.949초; 보존 원장 카카오 SENT 1,087행·FAILED 51행. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 실제 감지·알림·전송 시각
- 측정값과 단위: 표본 1건 판본 수신→알림 생성 22.537초, 생성→카카오 SENT 25.949초; 보존 원장 카카오 SENT 1,087행·FAILED 51행
- 측정 대상·분모: is_test=false 원장; 화면·카카오 채널 행은 고유 알림 수와 다름
- 비교 기준: 동일 detection_id의 시각 차
- 측정 방법: 읽기 전용 JOIN·타임스탬프 대조; matched_term·사용자 ID는 추출하지 않음
- 측정 환경과 시각: 11-11 00:00 KST 조회; 표본 사건 11-10 23:53~23:54
- 제한사항: start_offset_ms=null; detected_at이 판본 수신값과 동일하므로 실제 발언→탐지 지연이나 전체 평균으로 해석 금지; SENT는 열람 확인 아님

**⑥ 심사에서 사용할 수 있는 설명**

국정온은 관심 문구가 포함된 새 회의 발언을 감지해 화면 알림과 선택형 카카오 알림을 제공하고, 주제 요약과 근거 원문 확인으로 연결한다. 실제 예산결산특별위원회 회의의 수신·알림 생성·카카오 전송 원장을 확인했다. 상시 시청을 보조하는 경로가 운영 중이며, 자막 누락과 알림 전송 실패는 별도 상태로 남겨 모든 발언 감지나 수신자 열람을 보장하지 않는다.

**⑦ 미확인 사항 및 반대 근거**

규칙 생성 전 발언을 자동 소급 감지하지 않는다. 원장 보존기간·정리 정책 때문에 전체 서비스 생애의 전송 총량은 아니다. 카카오 실패 51행이 확인돼 무누락·무실패 주장은 불가하다. 직원 대기시간 단축은 미측정이다.

**⑧ 추가 검증이 필요한 사항**

저장된 동일 감지 ID로 화면 알림→관련 발언→주제 보고서의 화면을 개인정보를 가린 채 캡처한다. 감지율 검증은 공식 원문과 수집 자막의 표본 정답 집합을 먼저 만든다.

### [N-02] 주제 중심 AI 회의 분석

**① 검증 결론**

부분 확인

**② 핵심 답변**

국정온은 시간순 발언을 대주제·쟁점·질의/답변·후속 과제로 재구성하고 원문 식별자와 인용 구간을 연결한다. 행안위 실제 자료는 원문 4,573구간, 보고서 기준 1,029발언, 표시 대주제 46개·쟁점 349개·과제 66개다. 두 인용 필드(task_evidence_spans, request_spans)를 함께 검사해 62개 과제에서 원문 위치·인용문·해시·판본이 일치했고, 65개는 쟁점 ID를 참조했다. 나머지 4개는 REVIEW_REQUIRED 상태를 유지하며, 이 상태가 Markdown 출력에서도 드러나도록 로컬 코드를 보완했다.

**③ 소스코드 근거**

- [PoC/07-NationalAssembly/backend/app/services/meeting_topic_groups.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/meeting_topic_groups.py:1183) · `def build_meeting_topic_groups` · **1183행** · 주제별 묶음
- [PoC/07-NationalAssembly/backend/app/services/task_source_links.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/task_source_links.py:15) · `def _tokens` · **15행** · 과제·원문 연결
- [PoC/07-NationalAssembly/backend/app/services/topic_report_coverage.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/topic_report_coverage.py:7) · `def topic_report_coverage` · **7행** · 근거 포괄 검증
- [PoC/07-NationalAssembly/backend/app/main.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/main.py:1762) · `def ended_live_broadcast_brief_response` · **1762행** · 저장 구조화 보고서 제공
- [PoC/07-NationalAssembly/backend/app/services/task_source_links.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/task_source_links.py:84) · `def verified_task_spans` · **84행** · 두 인용 필드의 원문·해시·판본 검증
- 관련 테스트: [PoC/07-NationalAssembly/backend/tests/test_task_source_links.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/tests/test_task_source_links.py); [PoC/07-NationalAssembly/backend/tests/test_report_review_export.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/tests/test_report_review_export.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 국정온 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: 회의 `a242709a-df14-437f-a2bd-65f298d95eb0`, 행정안전위원회 국정감사(행정안전부 등). [national-interior-transcript.json](evidence/national-interior-transcript.json) · [national-interior-report.json](evidence/national-interior-report.json) · [national-interior-report.md](evidence/national-interior-report.md) · [national-interior-verification.json](evidence/national-interior-verification.json) · [national-task-link-gaps.json](evidence/national-task-link-gaps.json). 저장 원문·주제별 출력의 비교 예시는 부록 I. 최종 판단은 [national-task-final-verification.json](evidence/national-task-final-verification.json) 기준이다. 초기 필드별 점검의 58건은 task_evidence_spans만 센 값이며, request_spans의 추가 유효 4건을 포함한 최종 직접 근거 연결은 62건이다. [national-interior-report-reviewed.md](evidence/national-interior-report-reviewed.md)는 운영 자료를 수정 코드로 로컬 출력한 파일이다(미배포).
- 데이터 기준시각·입력 범위: 2026-10-26 행안위 회의 1건; 인용 필드 2종의 합집합; 2026-11-11 확보한 API 저장 자료, 오프라인 재검증.
- 확인한 결과: 4,573원문 구간; 보고서 1,029발언; 46대주제·349쟁점·66과제; 유효 직접 근거 62/66, 쟁점 ID 65/66. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 원문·보고서 구조 및 직접 근거 연결
- 측정값과 단위: 4,573원문 구간; 보고서 1,029발언; 46대주제·349쟁점·66과제; 유효 직접 근거 62/66, 쟁점 ID 65/66
- 측정 대상·분모: 2026-10-26 행안위 회의 1건; 인용 필드 2종의 합집합
- 비교 기준: 시간순 원문과 동일 회의의 주제별 보고서; 동일성 검증과 의미 검증 구분
- 측정 방법: 원문 slice·quote·content_hash·revision_ids 대조; tools/verify_evidence.py 재현
- 측정 환경과 시각: 2026-11-11 확보한 API 저장 자료, 오프라인 재검증
- 제한사항: 62/66은 인용 연결 무결성이지 과제의 의미·정책 확약 정확도가 아님; 4건 보류·1건 주제 미연결

**⑥ 심사에서 사용할 수 있는 설명**

국정온은 시간순 회의 발언을 정책 주제와 쟁점, 질의·답변 및 후속 과제로 재구성한다. 실제 행안위 보고서의 349개 쟁점과 66개 과제를 원문과 대조했고, 62개 과제에서 인용 위치·해시·판본 일치를 확인했다. 근거 대조가 필요한 나머지 과제는 보류 상태로 관리하며, 원문 연결의 완전성과 실제 정책 확약 여부를 구분해 검토할 수 있도록 한다.

**⑦ 미확인 사항 및 반대 근거**

원문 근거 ID 존재만으로 직접 인용 검증이나 후속조치 확정을 뜻하지 않는다. 과제 4건은 보류이며 이 중 1건은 topic_id도 없다. 628/628 원천 atom 분류와 349/349 쟁점 요약은 구조적 포괄 지표이며 원문 전체 의미를 빠짐없이 정확하게 요약했다는 검증은 아니다.

**⑧ 추가 검증이 필요한 사항**

완료: 두 인용 필드 통합 검사, 4개 보류 과제 표시 보완, 원문 불변 오프라인 출력 및 회귀시험 5건. 남은 보류 과제는 담당자가 원문을 대조해 유지·수정·제외를 결정한다. 운영 적용은 아직 하지 않았다.

### [N-03] 모델 비종속성과 JSON 기반 구조화 처리

**① 검증 결론**

부분 확인

**② 핵심 답변**

공통 JSON 응답 계약과 파서·근거·언어 검증을 제공사 어댑터와 분리해 시험한 모델을 같은 처리 경로에 적용한다. 10월 30일 합성 12발언 비교에서 Mini와 Nemo는 계약 검사를 통과했고 실제 Nemo 10발언의 응답·토큰·시간 기록도 있다. 반면 Gemma 시험은 429로 품질 평가를 완료하지 못했으며 의미 오류가 계약 검증을 통과한 사례도 남아 있다. 통합·공식 대조·음성전사 등 업무별 전용 경로가 있어 JSON 출력 지원만으로 모든 모델의 호환을 보장하지 않는다.

**③ 소스코드 근거**

- [PoC/07-NationalAssembly/backend/app/services/summary_contract.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/summary_contract.py:25) · `def summary_response_schema` · **25행** · 공통 JSON 계약
- [PoC/07-NationalAssembly/backend/app/services/summary_contract.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/summary_contract.py:162) · `def validated_summary_items` · **162행** · ID·근거·과제·언어 검증
- [PoC/07-NationalAssembly/backend/app/services/summary_client.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/summary_client.py:52) · `def build_summary_client` · **52행** · 제공사별 클라이언트 선택
- [PoC/07-NationalAssembly/backend/app/services/summary_cache.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/summary_cache.py:89) · `def cache_missing_summaries` · **89행** · 공통 캐시·저장·실패 처리
- 관련 테스트: [PoC/07-NationalAssembly/backend/tests/test_summary_cache.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/tests/test_summary_cache.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 국정온 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: [national-model-comparison-20261030.md](evidence/national-model-comparison-20261030.md) · [national-model-test-20261030.json](evidence/national-model-test-20261030.json) · [national-summary-counts.json](evidence/national-summary-counts.json). 원응답: `PoC/07-NationalAssembly/docs/evidence/MODEL_REPLACEMENT_20261030/poc7-comparison.json`, `poc7-nemo-comparison.json`, `REAL_MINI_NEMO_10_20261030/nemo-results.json`.
- 데이터 기준시각·입력 범위: 합성 12발언, 별도 실제 10발언, 11-03~10 저장 행을 각각 구분; 모델 비교 10-30; 운영 집계 11-11 00:00.
- 확인한 결과: 합성 Mini 12/12·Nemo 12/12; 실제 Nemo 10요청 실패 0·검증 거절 0·31,627토큰; 최근 저장 Mini 6,551·Nemo 3,014·Luna 710요약. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 계약 통과·실제 모델 처리
- 측정값과 단위: 합성 Mini 12/12·Nemo 12/12; 실제 Nemo 10요청 실패 0·검증 거절 0·31,627토큰; 최근 저장 Mini 6,551·Nemo 3,014·Luna 710요약
- 측정 대상·분모: 합성 12발언, 별도 실제 10발언, 11-03~10 저장 행을 각각 구분
- 비교 기준: 동일 합성 입력 비교; 실제 Mini는 과거 저장 결과로 동시 A/B가 아님
- 측정 방법: 기존 응답·검증 기록 및 모델별 저장 요약 GROUP BY
- 측정 환경과 시각: 모델 비교 10-30; 운영 집계 11-11 00:00
- 제한사항: 검증기 통과≠의미 정확성; 요청 수와 저장 발언 수는 다름; 미시험 모델은 미확인

**⑥ 심사에서 사용할 수 있는 설명**

국정온은 실시간 요약의 JSON 계약과 근거 검증을 제공사별 호출 코드에서 분리해 시험한 모델을 공통 처리 경로로 활용한다. Mini·Nemo의 응답 검증과 실제 저장 실적을 확인했으며, 형식 검사 뒤에도 남는 의미 오류와 호출 제한을 따로 기록한다. 모델 교체 가능 범위는 검증된 작업과 모델에 한정하고, 모든 JSON 지원 모델의 자동 호환을 주장하지 않는다.

**⑦ 미확인 사항 및 반대 근거**

Gemma 429·시험 인증 오류는 의미 품질 실패가 아니다. Nemo의 즉석 설명 요청 혼입, Mini의 근거 없는 표현·후속 약속 누락 사례가 있어 어느 모델도 정답 판정자로 간주할 수 없다. 과거 Gemini 보고서는 현재 기본 라우팅을 뜻하지 않는다.

**⑧ 추가 검증이 필요한 사항**

기존 캡처 응답을 공통 검증기에 오프라인 재생해 형식·근거·과제 오류를 별도 집계한다. 신규 모델 채택 시에는 대표 실제 발언과 미사용 holdout을 같은 조건으로 승인된 예산 내에서 시험한다.

### [N-04] 2개 모델 병렬 경쟁풀의 기술적 효과

**① 검증 결론**

부분 확인

**② 핵심 답변**

OpenRouter와 OpenAI 경로는 독립 스레드에서 서로 다른 발언 작업을 가져가며 원문 해시·프롬프트 버전 기반 PostgreSQL 세션 잠금으로 경쟁한다. 잠금 획득 뒤 유효 저장 결과를 재확인하고 실패·거절 자료를 보류해 다른 경로가 처리할 수 있게 한다. 현재 로그 표본에 두 provider의 summary.pool 실행과 저장 결과가 확인된다. 다만 단일 경로 대비 동일 조건의 처리량·대기시간·비용 비교가 없어 2배 속도나 비용 감소를 수치로 주장할 수 없다.

**③ 소스코드 근거**

- [PoC/07-NationalAssembly/backend/app/ingestion/summary_worker.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/ingestion/summary_worker.py:204) · `def run_grouped_pool` · **204행** · 독립 경로 스레드 실행
- [PoC/07-NationalAssembly/backend/app/ingestion/summary_worker.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/ingestion/summary_worker.py:180) · `def run_pool_lane` · **180행** · 독립 주기·오류 대기
- [PoC/07-NationalAssembly/backend/app/services/summary_cache.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/summary_cache.py:89) · `def cache_missing_summaries` · **89행** · 공급자 공통 잠금·완료 결과 재확인
- [PoC/07-NationalAssembly/backend/app/db/summary_repository.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/db/summary_repository.py:92) · `def existing_hashes` · **92행** · 저장 요약 재사용
- 관련 테스트: [PoC/07-NationalAssembly/backend/tests/test_summary_cache.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/tests/test_summary_cache.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 국정온 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: [national-parallel-log.json](evidence/national-parallel-log.json) · [national-summary-counts.json](evidence/national-summary-counts.json) · [national-offline-tests-final.txt](evidence/national-offline-tests-final.txt). 최신 컨테이너 로그 100줄에서 summary.pool 14행을 추출: OpenAI 12행·OpenRouter 2행. 로그 이벤트 수는 모델 호출 수·발언 수와 다르다.
- 데이터 기준시각·입력 범위: 선택 기간의 저장 요약 행; 로그는 11-11 00시대 별도 표본; summary-worker 실행 이미지 poc07-monthly-credit:20261105; 로그 시각은 파일에 UTC로 보존.
- 확인한 결과: 11-03~10 저장 Mini 6,551요약·Nemo 3,014요약; 최근 로그에 두 provider 실행 존재. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 병렬 경로 가동·모델별 저장량
- 측정값과 단위: 11-03~10 저장 Mini 6,551요약·Nemo 3,014요약; 최근 로그에 두 provider 실행 존재
- 측정 대상·분모: 선택 기간의 저장 요약 행; 로그는 11-11 00시대 별도 표본
- 비교 기준: 단일 모델 동일 조건 비교: 미측정
- 측정 방법: 로그 허용 필드 추출 및 원장 GROUP BY; 잠금·캐시 코드 대조
- 측정 환경과 시각: summary-worker 실행 이미지 poc07-monthly-credit:20261105; 로그 시각은 파일에 UTC로 보존
- 제한사항: 누적 행만으로 동시성·중복 호출 0·속도 향상률 입증 불가; 재시도는 추가 호출 가능

**⑥ 심사에서 사용할 수 있는 설명**

실시간 부분요약은 두 모델 경로가 작업 잠금으로 서로 다른 발언을 분담하고 이미 저장된 유효 결과를 재사용하도록 구성했다. 실제 원장에서 Mini·Nemo의 저장 실적과 두 경로의 실행 로그를 확인했다. 한 경로의 실패가 다른 경로의 실행을 막지 않는 구조이지만, 단일 경로 대비 속도·대기시간·비용 개선율은 동일 조건 비교시험 전까지 확정하지 않는다.

**⑦ 미확인 사항 및 반대 근거**

경쟁풀은 같은 발언을 두 모델에 동시에 보내 우승 답변을 선택하는 방식이 아니다. 이번 확인은 실행 로그·저장·코드이며 장기 부하나 제공사 장애를 새로 유발하지 않았다. 1초 선행 설정은 코드값이지 실측 처리시간 차이가 아니다.

**⑧ 추가 검증이 필요한 사항**

저장 응답과 지연시간을 사용하는 모의 큐로 단일/이중 경로의 동일 입력·동일 실패조건을 재현한다. 실제 제공사 비교는 별도 승인·예산 내에서 대기시간 p50/p95와 호출·재시도 수를 함께 계측한다.

### [N-05] 비공식 회의자료와 공식자료의 변경 추적

**① 검증 결론**

확인됨

**② 핵심 답변**

LIVE/STT·AI 잠정 결과와 공식 원문을 분리하고 기존 판본을 남긴 채 공식 연결·변경·추가·삭제 표시를 제공한다. 11월 9일 실제 공식본 35건의 투영 감사와 실제 화면 변경 강조 기록을 확인했다. 예결위 제4차 회의에서는 세부 요약 289개 중 공식 근거가 직접 연결된 것이 58개였고 나머지 231개는 실시간 근거로 표시됐다. 공식 원문 연결은 해당 구절의 출처 확인이며 AI 요약 전체의 정확성이나 모든 화자·수치의 공식 검증을 뜻하지 않는다.

**③ 소스코드 근거**

- [PoC/07-NationalAssembly/backend/app/services/official_evidence_presentation.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/official_evidence_presentation.py:153) · `def official_utterance_diff` · **153행** · 원문 변경 구간 계산
- [PoC/07-NationalAssembly/backend/app/services/official_evidence_presentation.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/official_evidence_presentation.py:200) · `def build_official_evidence_presentations` · **200행** · 동일 판본 근거 비교·부분 비교 보류
- [PoC/07-NationalAssembly/backend/app/db/official_integration_repository.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/db/official_integration_repository.py:7) · `class OfficialIntegrationRepository` · **7행** · 공식 통합 결과 보존
- [PoC/07-NationalAssembly/backend/app/services/official_change_report.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/official_change_report.py:52) · `def deterministic_changed_report` · **52행** · 변경 안내 구조화
- 관련 테스트: [PoC/07-NationalAssembly/backend/tests/test_official_evidence_presentation.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/tests/test_official_evidence_presentation.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 국정온 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: [national-official-20261109.md](evidence/national-official-20261109.md) · [national-official-diff-20261109.png](evidence/national-official-diff-20261109.png). 대표 회의 `64c5e92a-5cbc-42a2-8d2f-fc3eb0550ca6`; 화면 변경 비교 대표 `24be1685-9070-4522-ab28-456cde194ae1`. 최종 배포 이미지 `poc07-official-evidence-diff:20261109`와 핵심 파일 해시 일치 확인.
- 데이터 기준시각·입력 범위: 11-09 감사 대상 35개 공식본; 대표 회의 1건; 과거 화면·감사 11-09; 현재 배포 해시 11-11.
- 확인한 결과: 공식본 투영 감사 35건; 대표 회의 연결 123/123묶음·원문한계 4묶음/7건; 289요약 중 직접 공식근거 58개. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 공식 연결·원문 한계·화면 비교
- 측정값과 단위: 공식본 투영 감사 35건; 대표 회의 연결 123/123묶음·원문한계 4묶음/7건; 289요약 중 직접 공식근거 58개
- 측정 대상·분모: 11-09 감사 대상 35개 공식본; 대표 회의 1건
- 비교 기준: 동일 revision의 LIVE 근거와 현재 공식 원문
- 측정 방법: 보존된 projection audit·최종 browser 결과 검토, 이번 diff 모의 회귀
- 측정 환경과 시각: 과거 화면·감사 11-09; 현재 배포 해시 11-11
- 제한사항: 123/123 연결은 전원문 의미 확인이 아님; 공식자료의 요약 화자 확인 74/1,335에 한정된 기록도 있음

**⑥ 심사에서 사용할 수 있는 설명**

국정온은 실시간·잠정 자료와 공식 원문을 분리해 보존하고, 같은 판본의 연결 근거로 변경·추가·삭제 구간을 보여준다. 실제 공식본 감사와 화면에서 변경 강조를 확인했으며 비교 기준이 부족한 경우에는 부분 비교 또는 공식 원문만 표시한다. 공식 근거가 연결된 구절과 실시간 근거에 남은 요약을 구분해, 공식 화면이라는 이유로 AI 요약 전체를 공식 검증값으로 바꾸지 않는다.

**⑦ 미확인 사항 및 반대 근거**

11-09 중간의 카드 내 전체 원문 표시 방식은 철회돼 최종 화면 근거로 쓰지 않았다. 최종 화면은 화자별 요약과 별도 근거 패널이다. PARTIAL_BASELINE·SOURCE_LIMITED는 미완료 작업과 다른 원문 한계이며 모든 수치·정책결정 변경이 자동 확정되는 것은 아니다.

**⑧ 추가 검증이 필요한 사항**

대표 회의의 같은 revision_id·segment_id에 대한 LIVE 원문, 공식 원문, diff_spans와 최종 화면을 한 묶음으로 제시한다. 공식 근거가 없는 231개 요약은 실시간 근거 표시가 유지되는지 점검한다.

### [N-06] 실제 행정안전위원회 보고서 활용 사례

**① 검증 결론**

부분 확인

**② 핵심 답변**

행정안전위원회 국정감사 회의의 저장 보고서를 현재 API에서 JSON과 Markdown으로 실제 내려받았다. Markdown 응답은 HTTP 200이며 X-LLM-Calls: 0을 반환해 추가 모델 호출 없이 저장 결과를 재사용하는 출력 경로가 확인된다. 회의 종료 기록과 기초 보고서 저장 시각도 확인되지만 현재 세부 구조화 완료시각이나 사용자의 “보고서 만들기” 클릭 이력으로 대체할 수는 없다. 외부 메일·메신저 공유와 별도 편집 없이 실제 업무에 쓰인 사실은 제공된 증빙에서 확인하지 못했다.

**③ 소스코드 근거**

- [PoC/07-NationalAssembly/backend/app/main.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/main.py:2154) · `def ended_live_broadcast_brief_markdown` · **2154행** · 저장 보고서 MD 출력
- [PoC/07-NationalAssembly/web/meeting-report-document.js](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/web/meeting-report-document.js:8) · `function meetingDocumentSource` · **8행** · 보고서 문서 렌더링·인쇄 경로
- [PoC/07-NationalAssembly/backend/app/db/meeting_brief_repository.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/db/meeting_brief_repository.py:10) · `class MeetingBriefRepository` · **10행** · 기초 보고서·판본 저장
- 관련 테스트: [PoC/07-NationalAssembly/web/tests/meeting-document-overview.test.cjs](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/web/tests/meeting-document-overview.test.cjs). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 국정온 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: 회의 ID a242709a…; 기초 brief e6a0652e…. 종료 2026-10-26 22:29:51.225 KST; 기초 brief 저장 23:41:11.830 KST. 현재 STRUCTURED 파일은 [national-interior-report.md](evidence/national-interior-report.md)와 [national-interior-report.json](evidence/national-interior-report.json); 다운로드 헤더·시각은 [national-report-download.json](evidence/national-report-download.json). 이번 보완 결과 [national-interior-report-reviewed.md](evidence/national-interior-report-reviewed.md)는 로컬 재출력본이다. 저장 시각의 의미와 4개 과제의 검토 상태를 명시했으며, 원본 다운로드 파일도 별도 보존했다.
- 데이터 기준시각·입력 범위: 행안위 회의 1건의 현재 저장 출력; 다운로드 2026-11-11 00:01:50 KST; 종료·기초 저장일 10-26.
- 확인한 결과: MD 495,304바이트·HTTP 200·X-LLM-Calls 0; 기초 보고서 1건 저장; 쟁점 349·과제 66. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 실제 출력·기초 저장시각
- 측정값과 단위: MD 495,304바이트·HTTP 200·X-LLM-Calls 0; 기초 보고서 1건 저장; 쟁점 349·과제 66
- 측정 대상·분모: 행안위 회의 1건의 현재 저장 출력
- 비교 기준: 기존 저장 결과→추가 문서 작성 없이 파일 취득 경로
- 측정 방법: GET brief 및 brief.md?view=structured 응답 보존
- 측정 환경과 시각: 다운로드 2026-11-11 00:01:50 KST; 종료·기초 저장일 10-26
- 제한사항: 외부 공유·업무 사용·사용자 클릭·인쇄 실행은 미확인; 기초 generated_at을 최종 구조화 완료시각으로 사용 금지

**⑥ 심사에서 사용할 수 있는 설명**

행정안전위원회 실제 회의의 저장 분석 결과를 주제별 보고서 파일로 출력할 수 있음을 확인했다. 현재 서비스에서 349개 쟁점과 66개 과제를 포함한 Markdown 보고서를 추가 모델 호출 없이 내려받아, 별도 문서 작성에 필요한 재정리 과정을 줄일 수 있는 경로를 보여준다. 다만 외부 메일·메신저 공유나 편집 없이 실제 업무에 활용된 사실은 별도 이용 증빙이 필요하다.

**⑦ 미확인 사항 및 반대 근거**

API 응답의 생성 가능성과 실제 조직 내 활용 성과는 다르다. 출력 파일의 근거 연결·주제 공백은 N-02에 기록했다. 과거 Gemini 기초 생성시각을 2026-11 현재 화면의 최종 생성시각으로 소개하면 오류다.

**⑧ 추가 검증이 필요한 사항**

완료: Markdown의 생성 시각을 “기초 보고서 저장 시각”으로 명확히 하고 REVIEW_REQUIRED 과제 표시를 추가했다. 집중 회귀 5건 및 실제 저장 자료 재출력이 통과했다. 실제 공유·업무 활용 성과는 기존 사용자 증빙이 확보될 때 추가한다.

### [N-07] 축적 데이터 기반 정책 인사이트

**① 검증 결론**

부분 확인

**② 핵심 답변**

정부 안건·국회 쟁점·시각·기관·원문 출처를 연결하는 API와 온톨로지·동향 집계가 구현돼 있다. 실제 API 응답에서 금융사기 관련 국무회의 안건과 국회 논의를 공통 근거 단어로 연결한 사례를 확인했다. 이 응답은 link_scope=SPECIFIC_TOPIC_SIGNAL_ONLY로 연결 수준을 제한하므로 정책 인과관계나 정부의 이행 완료를 의미하지 않는다. 신규·지속·급증 분류와 법안·과제 관계의 전체 정확도 또는 정책 의사결정 효과는 이번에 계측하지 않았다.

**③ 소스코드 근거**

- [PoC/07-NationalAssembly/backend/app/services/cross_institution_flow.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/cross_institution_flow.py:210) · `def build_specific_cross_institution_flow` · **210행** · 구체 정책 신호·시점·근거 연결
- [PoC/07-NationalAssembly/backend/app/db/policy_issue_repository.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/db/policy_issue_repository.py:33) · `def _build_specific_issue_flow` · **33행** · 누적 쟁점 집계
- [PoC/07-NationalAssembly/backend/app/services/meeting_topic_groups.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/meeting_topic_groups.py:1414) · `def build_meeting_topic_ontology` · **1414행** · 주제 온톨로지
- [PoC/07-NationalAssembly/backend/app/main.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/main.py:1246) · `def cross_institution_policy_flow` · **1246행** · 정책 흐름 조회 API
- 관련 테스트: [PoC/07-NationalAssembly/backend/tests/test_cross_institution_flow.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/tests/test_cross_institution_flow.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 국정온 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: [national-insights.json](evidence/national-insights.json) 실제 GET `/api/policy/cross-institution-flow?limit=5`. 예시: 2026-09-17 국회 논의와 09-22 제41회 국무회의 금융사기 관련 안건, 원천 URL·해시·parser version·공통 키워드가 포함된다. 과거 온톨로지 분모 비교는 [national-ontology-20261019.json](evidence/national-ontology-20261019.json).
- 데이터 기준시각·입력 범위: 현재 API 표본과 과거 감사 모집단은 별도; 현재 응답 11-11 00시대; 과거 분모 검증 10-19.
- 확인한 결과: 현재 상위 5건 요청 응답 확보; 10-19 과거 43보고서의 정책주제 3,163개 중 온톨로지 주제 2,327개. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 정책 흐름 응답·과거 온톨로지 적용
- 측정값과 단위: 현재 상위 5건 요청 응답 확보; 10-19 과거 43보고서의 정책주제 3,163개 중 온톨로지 주제 2,327개
- 측정 대상·분모: 현재 API 표본과 과거 감사 모집단은 별도
- 비교 기준: 같은 원천·분모의 과거/현재 규칙 재생 비교
- 측정 방법: 현재 GET 응답, 연결 조건 코드, 과거 JSON 검토
- 측정 환경과 시각: 현재 응답 11-11 00시대; 과거 분모 검증 10-19
- 제한사항: 온톨로지 coverage는 분류 정확도·인과 정확도가 아님; 일부 bills=[] 등 관계 공백

**⑥ 심사에서 사용할 수 있는 설명**

국정온은 축적된 회의 쟁점을 정부 안건과 연결해 기관 간 논의 순서와 공통 정책 신호를 확인하도록 한다. 실제 응답에는 관련 국회·국무회의 근거, 시점, 원문 URL과 해시가 포함돼 사용자가 연결 근거를 검토할 수 있다. 이 연결은 주제 신호의 대응 관계이며 정책 결정의 인과나 이행 완료를 뜻하지 않고, 온톨로지 적용률도 정확도와 구분해 관리한다.

**⑦ 미확인 사항 및 반대 근거**

관련 주제의 시계열 근접·키워드 일치만으로 정책 영향·수행 완료를 확정할 수 없다. “온톨로지 98%”처럼 과거 작은 분모의 적용률을 현재 전체에 전용하면 안 된다. 실제 기관 사용자의 정책 의사결정 개선 효과는 미측정이다.

**⑧ 추가 검증이 필요한 사항**

현재 API 5건을 원문과 대조해 올바른 주제 연결·과도한 연결·미연결을 분류한다. 신규/지속/급증 표본별 산식·기간·회의 수 분모를 함께 제시한다.

### [N-08] 신규 위원회 확장성 검증

**① 검증 결론**

계획·시험 예정

**② 핵심 답변**

사용자 지시에 따라 문광위 추가 수집 시연은 별도 세션의 개발·검증 대상으로 분리했다. 본 보고서는 국정온의 기존 운영 증빙만 검토하며 해당 시연의 코드·설정·실행 결과를 추가 분석하지 않는다. 신규 위원회 확장 성공이나 설정만으로 가능한 확장이라는 결론은 이번 보고서에서 확정하지 않는다. 별도 세션의 최종 결과가 확보되면 그 증빙을 이 항목에 연결하면 된다.

**③ 소스코드 근거**

검토 범위에서 제외. 별도 세션 증빙을 연결할 항목이다.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 본 세션 확인 제외
- 서비스/배포 버전: 국정온 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: 별도 세션 담당. 이 보고서의 검토·보완·시연 범위에서 제외. 실행 ID·결과 파일·배포 버전은 별도 결과 수령 전 미확인.
- 데이터 기준시각·입력 범위: 사용자가 별도 세션에서 진행 중인 문광위 추가 수집 시연; 별도 결과 대기.
- 확인한 결과: 본 세션 미측정. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 신규 위원회 확장 시험
- 측정값과 단위: 본 세션 미측정
- 측정 대상·분모: 사용자가 별도 세션에서 진행 중인 문광위 추가 수집 시연
- 비교 기준: 본 세션 비교 없음
- 측정 방법: 분석 제외
- 측정 환경과 시각: 별도 결과 대기
- 제한사항: 성공·실패·비용·소스 무수정 여부를 여기서 판정하지 않음

**⑥ 심사에서 사용할 수 있는 설명**

국정온의 신규 위원회 수집 시연은 별도 세션에서 개발·검증 중이며, 본 보고서는 기존 운영 서비스의 수집·분석·보고서 증빙을 정리한다. 문광위 추가 수집의 성공 여부와 설정 변경만으로 가능한 확장 범위는 별도 세션의 실제 실행 결과를 근거로 확정할 예정이다. 현재 신청서에는 확장 완료나 무수정 확대 실적으로 기재하지 않는다.

**⑦ 미확인 사항 및 반대 근거**

사용자 요청에 따른 검토 제외이며 구현 부재나 실패 판정이 아니다.

**⑧ 추가 검증이 필요한 사항**

이 세션에서 추가 개발·분석하지 않는다. 별도 세션의 확정된 결과와 증빙 경로만 최종 제출 때 연결한다.

### [N-09] 위원회 확대에 따른 한계비용과 지속가능성

**① 검증 결론**

부분 확인

**② 핵심 답변**

기존 수집·분석·보고서 플랫폼을 재사용하는 구조와 모델·음성 사용량 원장은 확인된다. 10월 30일 국정온 전용 감사는 서비스 호출과 비교시험을 분리하고 중복 request_id를 제거해 모델별 사용량을 집계했다. 11월 3~10일 음성 원장에는 Voxtral 1,845이벤트·114,102.52초·기록액 $5.705126이 있어 음성전사 역시 증분 비용 항목임을 확인했다. 신규 위원회별 실제 비교, 서버 여유 용량과 저장·통신·운영인력 비용을 계측하지 않아 “AI 이용료가 주요 또는 유일한 증분 비용”이라는 가설은 아직 확정할 수 없다.

**③ 소스코드 근거**

- [PoC/07-NationalAssembly/backend/app/db/summary_repository.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/db/summary_repository.py:302) · `def record_monthly_token_usage` · **302행** · 요청별 사용량 원장
- [PoC/07-NationalAssembly/backend/app/services/model_workloads.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/model_workloads.py:10) · `def openai_limit` · **10행** · 업무별 모델 배정
- [PoC/07-NationalAssembly/backend/app/services/shared_budget.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/shared_budget.py:20) · `def _solar` · **20행** · 공통 예산·요청 관리
- [PoC/07-NationalAssembly/backend/app/services/mistral_transcription.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/app/services/mistral_transcription.py:17) · `class TranscriptionResult` · **17행** · 음성전사 경로
- 관련 테스트: [PoC/07-NationalAssembly/backend/tests/test_summary_cache.py](/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/backend/tests/test_summary_cache.py). 실행 여부와 결과는 부록 J 참조.
- 코드 버전: 위 공통 버전표 및 `evidence/code-references.json`의 파일별 SHA-256.

**④ 운영 서비스 및 데이터 근거**

- 확인 일시(KST): 2026-11-10 23:58~11-11; 파일별 checked_at·아래 사건 시각을 우선 적용
- 서비스/배포 버전: 국정온 공통 버전표 참조. 과거 실행 버전은 과거 파일에 기재된 범위만 확인.
- 기능이 확인된 실제 화면·API / 실행 ID / 결과 경로: [national-cost-audit-20261030.md](evidence/national-cost-audit-20261030.md) · [national-cost-metrics-20261030.json](evidence/national-cost-metrics-20261030.json) · [national-audio-usage.json](evidence/national-audio-usage.json) · [national-usage.json](evidence/national-usage.json) · [national-summary-counts.json](evidence/national-summary-counts.json). 단일 llm_provider_token_usage_events 표는 Mini 등 전체 요청을 포괄하지 않아 총비용 원장으로 쓰지 않았다.
- 데이터 기준시각·입력 범위: 과거 PoC7 전용 감사와 최근 audio_usage_events를 각각 분리; 모델 감사 10-30 00:00~21:44:17 KST; 음성 집계 11-03~10.
- 확인한 결과: 10-30 서비스 Mini 434호출·1,590,380토큰, Dots 259호출·760,785토큰; 11-03~10 음성 114,102.52초·장부 $5.705126. 별도 화면이나 실행 ID가 없는 집계는 해당 원장 조회 결과를 근거로 사용한다.

**⑤ 정량적 증빙**

- 측정한 지표: 기존 모델·음성 사용량
- 측정값과 단위: 10-30 서비스 Mini 434호출·1,590,380토큰, Dots 259호출·760,785토큰; 11-03~10 음성 114,102.52초·장부 $5.705126
- 측정 대상·분모: 과거 PoC7 전용 감사와 최근 audio_usage_events를 각각 분리
- 비교 기준: 신규 위원회 추가 전후 동일 조건 비교: 미측정
- 측정 방법: 기존 감사의 request_id 중복 제거 결과; 음성 원장 SQL SUM
- 측정 환경과 시각: 모델 감사 10-30 00:00~21:44:17 KST; 음성 집계 11-03~10
- 제한사항: 장부 금액≠실청구; 음성은 정부·국회 혼합일 수 있어 신규 위원회 비용으로 귀속 불가; 서버 용량 미측정

**⑥ 심사에서 사용할 수 있는 설명**

국정온은 공통 수집·보고서 기능을 재사용하고 모델 호출·토큰·음성 처리량을 원장으로 추적한다. 기존 운영 감사에서 모델별 호출과 비교시험을 분리했고, 최근 음성전사의 처리량과 비용 기록도 확인했다. 신규 위원회 확대의 비용은 분석·전사뿐 아니라 저장·통신·운영부담까지 포함해 계측해야 하며, AI 이용료가 주요 증분 비용이라는 설명은 확장 시험 후 검증한다.

**⑦ 미확인 사항 및 반대 근거**

무료 모델 reported_cost=0, 월 크레딧, 표준단가 환산액과 실제 청구액은 서로 다르다. 저장 요약 수를 호출 수로 간주하거나 공통 프로젝트 예산을 국정온 비용으로 전용하면 안 된다. 서버 여유 용량·동시 방송 수·운영 인력은 미측정이다.

**⑧ 추가 검증이 필요한 사항**

기존 원장의 서비스별·모델별 집계와 실제 청구 기준을 대조한다. 신규 위원회 증분비용은 별도 세션의 확정 결과를 연결한다. 본 세션에서 문광위 추가 수집 시연이나 별도 계측 작업을 수행하지 않는다.
## A. 평가기준별 증빙 종합표

우선순위 P0는 제출 전 문구·증빙의 일치, P1은 작은 비용의 재현·출력 보완, P2는 별도 실증을 뜻한다. 실제 심사점수나 점수 상승폭을 예측한 표는 아니다.

### 더주택

| 평가항목 | 관련 질문 ID | 확인된 핵심 강점 | 근거 파일·실행 기록 | 남은 약점 | 보완 우선순위 |
|---|---|---|---|---|---|
| 필요성 20점 | H-01, H-07 | 인허가·공고·공사·문서의 관리 단위 차이를 실제 사업으로 입증 | [왕숙2 검토](evidence/home-wangsuk2-20261017.json), [연남동 중복 방지](evidence/home-yeonnam-20261020.json) | 기관 간 공통 사업키·구성 블록 확인 부족 | P0: 단순 수집 대비 필요한 검증 절차 설명 |
| 창의성 30점 | H-02, H-03, H-07 | 역할별 AI 판단과 코드 검증·승인 규칙·사업 동일성 원장 결합 | [업무 집행](evidence/home-officer-20261105.json), [규칙 경로](evidence/home-algorithm-20261102.md) | 운영 승인 추출 규칙 0건; 최근 보류 다수 | P0: 구현된 경로와 운영 축적 성과 구분 |
| 활용성 20점 | H-03~06 | 실제 자료 제외·보류, 정책 집계, 다른 도구에서 읽는 데이터 출력 | [정책 계획](evidence/home-policy-plan-97.json), [수신 재현](evidence/portable-verification.json) | 조직 사용자 활용·시간 절감·실제 기관 연계 미확인 | P1 완료: 실제 ZIP 수신 검증 |
| 완성도 15점 | H-03, H-08 | 판본·중복 방지·승인값 보존·예산 중단 및 미처리 기록 | [원장](evidence/home-ai-ledger.json), [회귀시험](evidence/home-offline-tests.txt) | 과거 의존성 배포 실패; 현재 미완료 작업 | P0: 실패·보류까지 시연; P2 복원 실증 |
| 확산가능성 15점 | H-06~08 | home-slices/1 계약·31종 데이터·독립 수신 도구 | [manifest](evidence/home-slices-manifest.json), [검사 도구](tools/verify_evidence.py) | 기준 판 없는 delta 실제 합병·외부 기관 연결 미확인 | P1 완료: 휴대 가능한 검사 도구; P2 수신기관 실증 |

### 국정온

| 평가항목 | 관련 질문 ID | 확인된 핵심 강점 | 근거 파일·실행 기록 | 남은 약점 | 보완 우선순위 |
|---|---|---|---|---|---|
| 필요성 20점 | N-01, N-06 | 상시 시청을 보조하는 감지·알림·근거 확인과 보고서 출력 | [실제 감지](evidence/national-watch-samples.json), [실제 출력](evidence/national-report-download.json) | 실제 직원 대기시간·업무시간 감소 미측정 | P0: 실제 타임라인과 기능 연결 제시 |
| 창의성 30점 | N-02~05, N-07 | 주제별 재구성·모델 공통 계약·경쟁풀·공식자료 대조 결합 | [행안위](evidence/national-interior-report.json), [공식 대조](evidence/national-official-20261109.md), [병렬 로그](evidence/national-parallel-log.json) | 형식 검증 후 의미 오류; 속도 우위 미측정 | P1 완료: 두 인용 필드의 직접 근거 재검증 |
| 활용성 20점 | N-01, N-02, N-06 | 실제 알림 전송, 349쟁점·66과제의 추가 모델 호출 없는 파일 출력 | [Markdown](evidence/national-interior-report.md), [최종 인용 검증](evidence/national-task-final-verification.json) | 실제 외부 공유·기관 활용 증빙 없음 | P1 완료: 검토 필요 과제·시각 명칭 로컬 보완 |
| 완성도 15점 | N-02~05 | 원문 인용·해시·판본 대조, 잠정/공식 출처 구분, 작업 잠금·재사용 | [보완 시험](evidence/national-export-focused-tests.txt), [공식 대조 화면](evidence/national-official-diff-20261109.png) | 과제 4건 검토 필요; 공식자료 연결 한계; 기존 UI 문자열 검사 1건 실패 | P0: 보류 상태 명시; P1 출력 보완은 운영 미배포 |
| 확산가능성 15점 | N-03, N-07~09 | 시험된 모델 교체 경로·공통 처리·요청/음성 사용량 추적 | [모델 비교](evidence/national-model-comparison-20261030.md), [비용 감사](evidence/national-cost-audit-20261030.md) | 신규 위원회 시연은 별도 세션; 실제 한계비용 미확인 | P0: 별도 결과 연결 전 확대 완료 주장 제외 |

## B. 심사용 핵심 증빙 5건

아래 시간은 **작품별 5분 영상** 안에서의 배치다. 새 운영 작업을 실행하는 대신 저장 화면·실제 파일·원장을 보여주면 비용 없이 재현 가능하다. 현재 화면과 과거 캡처에는 각각 기준일을 표시한다.

### 더주택

| 순서·증빙 제목 | 입증 항목 | 실제 결과와 근거 경로 | 5분 영상에서 보여줄 방법 | 추가 검증 |
|---|---|---|---|---|
| 1. 같은 사업도 숫자를 바로 더할 수 없다 | 필요성·창의성 | 왕숙2 공식 착공 1,100호와 모집 1,498호의 범위 불일치 [검토](evidence/home-wangsuk2-20261017.json) | 0:00~0:50 원천 두 값→블록/단계 차이→UNRESOLVED | 구성 블록 확인은 미해결로 표시 |
| 2. AI 판단을 실제 저장 결과와 대조 | 창의성·활용성 | 비주택 2건 제외·기존 연결 재확인·보류 [실행](evidence/home-officer-20261105.json) | 0:50~1:50 Yes/No/HOLD 각 1건과 전후 상태 | 신규 사업·실적 증가로 표현하지 않음 |
| 3. 정책 목표부터 개별 사업·원천까지 | 활용성 | 목표 135만호·식별 배정 91,849호·미식별 1,258,151호 [정책 자료](evidence/home-policy-plan-97.json) | 1:50~3:00 정책→사업 3개→공고 물량·REVIEW 상태 | 과거 화면/현재 데이터 날짜 분리; 공식 착공 실적으로 표현 금지 |
| 4. 중복 신규 등록을 막은 실제 사례 | 완성도 | 연남동 기존 8호 사업 재사용, 신규 사업·추가 물량 0 [전후 결과](evidence/home-yeonnam-20261020.json) | 3:00~3:45 원문 페이지→기존 ID→보호 원장 해시 | 별도 신규 실행 불필요 |
| 5. 다른 시스템이 읽을 수 있는 실제 산출물 | 확산가능성 | ZIP 31종·39,359행·106개 파일 검사 PASS [재현 결과](evidence/portable-verification.json) | 3:45~5:00 ZIP 구조→한 슬라이스→검사 명령·PASS | 외부 기관 연계와 delta 합병은 미실증 |

### 국정온

| 순서·증빙 제목 | 입증 항목 | 실제 결과와 근거 경로 | 5분 영상에서 보여줄 방법 | 추가 검증 |
|---|---|---|---|---|
| 1. 관심 발언 감지에서 알림까지 | 필요성·활용성 | 예결위 실제 수신·알림·카카오 SENT [원장](evidence/national-watch-samples.json) | 0:00~0:50 4개 시각과 원문 확인 동선; 개인 알림 내용 제외 | SENT는 열람 확인 아님 |
| 2. 시간순 원문을 정책 보고서로 | 창의성·활용성 | 4,573원문 구간→46대주제·349쟁점·66과제 [보고서](evidence/national-interior-report.json) | 0:50~2:00 같은 회의 원문과 주제별 보고서를 나란히 표시 | 1,029발언·628 atom의 다른 분모를 혼동하지 않음 |
| 3. 근거가 남는 과제와 보류 표시 | 완성도 | 직접 인용 무결성 62/66, 나머지 4건 보류 [최종 감사](evidence/national-task-final-verification.json) | 2:00~2:50 인용문·원문 위치→보류 과제→로컬 출력본 표시 | 보완본은 미배포임을 자막으로 표시 |
| 4. 공식자료 발간 뒤에도 출처 차이를 확인 | 창의성·완성도 | 잠정 원문과 공식 회의록 변경 구간 [화면](evidence/national-official-diff-20261109.png), [감사](evidence/national-official-20261109.md) | 2:50~4:00 공식/잠정 표시와 한성숙 발언 변경 구간 확대 | 화면 사례와 35보고서 감사의 분모 구분 |
| 5. 저장 분석을 바로 보고서 파일로 | 활용성·확산가능성 | 실제 Markdown 다운로드 HTTP 200·X-LLM-Calls 0 [응답](evidence/national-report-download.json) | 4:00~5:00 저장 보고서→파일→원문 근거·시각; 모델 계약은 마지막 10초 | 실제 조직 공유·활용 성과는 별도 증빙 필요 |

## C. 신청서에 사용할 확정 문구

본 절은 확인된 범위로 작성한 제출용 문구다. 소개는 100자 내외, 나머지는 300자 내외이며 항목별 입력란에 맞춰 축약 가능하다. 로컬 수정의 운영 적용 완료나 별도 위원회 확장 성공을 전제로 하지 않는다.

### 더주택

**핵심 소개**

더주택은 기관마다 다른 주택공급 자료를 사업·정책·단계별로 연결하고, 원천과 검토 이력을 함께 보여주는 서비스다. 서로 다른 물량의 단순 합산을 피하고, 확인되지 않은 연결과 실적은 보류 상태로 관리한다.

**주요 기능 및 창의성**

기관별 공고·인허가·공사 자료의 식별자와 지구·블록·물량 범위를 대조해 사업 동일성을 검토한다. 알고리즘·수집·업무담당자의 AI 역할을 나누고, 판단 결과를 코드 검증 및 실제 저장 상태와 연결한다. 원문 추출 규칙은 시험·승인 후 모델 호출 없이 재사용하는 경로를 갖췄다. 실제 왕숙2 자료의 착공·모집 물량 차이와 연남동 사업의 중복 등록 방지 사례를 확인했으며, 불명확한 근거는 검토 상태로 남긴다. 현재 운영 승인 추출 규칙은 0건이므로 구현 경로와 운영 축적 실적을 구분한다.

**실제 업무 활용성과 성과**

운영 기록에서 비주택 자료 2건 제외, 기존 사업 연결 재확인, 근거 부족 자료의 보류를 확인했다. 9·7 정책의 목표·식별 배정·미식별 물량과 개별 사업의 공급 공고를 함께 검토할 수 있고, 모집 물량을 착공·입주 실적으로 오인하지 않도록 단계와 검토 상태를 구분한다. 실제 데이터 ZIP을 독립 수신 도구로 읽어 31종 데이터와 39,359행의 계약·해시 검사를 통과했다. 이를 통해 자료 검토와 보고·전달에 필요한 근거를 재사용하는 경로를 입증했으며, 직원 업무시간이나 비용의 절감률은 아직 측정하지 않았다.

**범정부 확산가능성**

원천별 수집·정규화, 사업 동일성 대조, 정책·단계 집계와 데이터 전달 계약을 분리해 다른 자료와 업무에 재사용할 기반을 갖췄다. home-slices/1은 데이터 종류·허용 필드·기준시각·판본·해시를 명시하며, 기존 실제 ZIP을 격리된 수신 도구로 읽고 검증할 수 있다. 기관 간 공통 사업키가 부족한 문제에 대해서는 원천 식별자와 단계별 사건·물량·판본을 함께 제공하는 표준화 방향을 제안한다. 다만 현재 확인한 운영 범위가 모든 지역·사업을 포괄하지 않으며, 다른 기관 시스템과의 실제 연결·운영은 추가 실증이 필요하다.

### 국정온

**핵심 소개**

국정온은 관심 정책 발언의 감지·알림부터 주제별 회의 보고서와 근거 원문 확인까지 연결하는 서비스다. 시간순 발언을 정책 쟁점과 후속 과제로 재구성하고, 잠정 분석과 공식자료의 출처를 구분한다.

**주요 기능 및 창의성**

시간순 회의 기록을 대주제·쟁점·질의와 답변·후속 과제로 재구성하고 원문 식별자와 인용 구간을 연결한다. 실제 행안위 보고서는 46개 표시 대주제, 349개 쟁점, 66개 과제를 제공하며, 62개 과제에서 인용 위치·해시·판본 일치를 확인했다. 실시간 요약은 제공사별 호출과 공통 JSON 계약·검증을 분리하고 두 제공사 작업풀의 실행 기록을 남긴다. 공식자료가 발간된 뒤에는 잠정 자료와의 변경 구간을 확인할 수 있다. 인용 무결성과 과제 의미의 정확성을 구분하고, 검토가 필요한 항목은 보류 상태로 관리한다.

**실제 업무 활용성과 성과**

실제 예산결산특별위원회 회의에서 발언 수신, 관심 내용 감지, 알림 생성과 카카오 전송 기록을 확인했다. 담당자는 알림을 출발점으로 관련 발언과 주제별 보고서의 근거를 확인할 수 있다. 행정안전위원회 회의의 저장 분석 결과를 실제 Markdown 파일로 내려받았고, 해당 응답은 추가 모델 호출 0건을 기록했다. 이는 반복 시청과 문서 재정리를 보조하는 기능의 실제 작동을 보여준다. 다만 전송 완료가 수신자의 열람을 뜻하지 않으며, 외부 메일·메신저 공유나 조직 내 활용에 따른 업무시간 절감은 별도 증빙이 필요하다.

**범정부 확산가능성**

실시간 요약의 공통 데이터 계약과 제공사 어댑터, 원문 검증 및 결과 저장 경로를 분리해 시험된 모델을 교체 적용할 수 있다. 실제 Mini·Nemo 비교와 모델별 저장 결과, 요청·토큰·음성 처리량 원장을 확인했다. 정부 안건과 국회 쟁점의 공통 정책 신호를 원문·시각·해시와 연결하는 API도 제공한다. 이러한 구조는 다른 정책업무에 재사용할 기반이지만, 모든 모델의 호환이나 기관 간 정책 인과를 보장하지 않는다. 신규 위원회 수집 시연은 별도 세션에서 진행 중이며 확대 성공과 증분비용은 그 결과로 확정한다.

## D. 확인되지 않은 주장과 수정안

| 사용을 피할 표현 | 확인되지 않거나 다른 사실 | 사용할 수 있는 수정안 |
|---|---|---|
| “수집부터 정책 실적 반영까지 완전 자동화” | 보류·예산 중지·명시적 승인 경로 존재. 11-05 정책 실적·목표·매핑 불변 | “AI의 역할별 판단과 코드 검증을 결합하고, 실저장·보류·미처리 이력을 관리한다.” |
| “AI가 학습할수록 모든 처리비용 0원” | 승인 CSS 추출 경로만 무호출. 현재 승인 규칙 0건이며 다른 에이전트 호출 지속 | “승인된 본문 추출 규칙을 적용하는 로컬 단계는 모델 호출이 없다.” |
| “모든 주택공급사업을 실시간 통합” | 현재 범위 SEOUL_GYEONGGI, 미식별 물량과 자료 공백 존재 | “현재 확보한 대상 원천과 사업을 연결하고 미확보·미식별 범위를 표시한다.” |
| “정책 목표 135만호 중 91,849호 달성” | 91,849호는 식별 배정이며 확정 착공 실적 아님; 검토 중 매핑 포함 | “목표 135만호의 식별 배정 91,849호와 미식별 유보 1,258,151호를 구분한다.” |
| “모든 공공데이터에는 사업 식별키가 없다” | 인허가 mgmPmsrgstPk 등 원천 관리키 존재 | “기관·자료별 관리키가 있으나 기관 간 동일 사업·블록·단계를 잇는 공통키가 부족하다.” |
| “JSON을 지원하는 모든 AI와 즉시 호환” | 시험한 업무·모델만 확인; 429·의미 오류 존재 | “공통 계약과 제공사 어댑터로 시험한 모델을 같은 처리 경로에 적용한다.” |
| “두 모델로 속도 두 배, 중복 호출 0” | 병렬 구조·잠금·실행은 확인, 동일 조건 성능 비교와 전 구간 중복 계측 없음 | “두 제공사의 작업풀과 공통 잠금·캐시 재검사로 병렬 처리한다.” |
| “문광위 확대 완료, 코드 수정 불필요” | 별도 세션 개발·검증 중이며 본 검토 제외 | “신규 위원회 시연은 별도 결과에 따라 확장 범위를 확정한다.” |
| “업무시간·비용 80% 절감” | 수작업 기준선·동일 작업 A/B 미측정 | “실제 알림·저장 보고서 재출력·데이터 재사용 경로를 확인했다.” |
| “타 기관 시스템 연계 완료” | 실제 ZIP 수신 검사는 완료, 기관 시스템 연결·delta 합병 미실증 | “계약 기반 ZIP을 독립 수신 도구에서 검증해 재사용 가능성을 확인했다.” |
| “66개 과제 모두 직접 근거가 검증된 확정 후속조치” | 직접 인용 무결성 62/66, 4건 검토 필요; 인용 일치도 확약 검증과 다름 | “66개 과제를 제공하며 62개에서 직접 인용의 위치·판본 일치를 확인했다.” |
| “전부 공식 회의록 기반의 확정 보고서” | 잠정 원문·AI 요약·공식 근거가 혼재하며 공식 매칭 제한 존재 | “잠정 분석과 공식 근거를 구분하고 확인 가능한 변경을 추적한다.” |
| “보고서 생성일=현재 상세 보고서 최종 완성일” | generated_at은 기초 보고서 저장 시각 | “기초 보고서 저장 시각과 구조화 자료의 판본을 구분한다.” |
| “무료 모델을 쓰므로 운영비 0원” | reported_cost=0과 실제 청구 다름; 전사·저장·통신·운영비 미포함 | “모델·토큰·음성 처리량을 기록하고 실제 청구와 인프라 비용을 별도 산정한다.” |

## E. 증빙 패키지

[파일별 인덱스](evidence-index.csv)는 더주택·국정온·공통과 현재 조회·과거 기록·격리 시험·로컬 보완을 구분한다. [해시 목록](manifest.sha256)은 배포 파일의 동일성을 확인하는 용도다.

- `report.pdf` / `report.md` / `report.html`: 동일한 본문과 A~J 부록. PDF는 33쪽이며 HTML은 브라우저 열람·인쇄용이다. `application-copy.md`는 신청서 확정 문구만 분리한 파일이다.
- `evidence/home-*`: 더주택 원천·업무처리·정책·원장·실제 ZIP·검증 결과.
- `evidence/national-*`: 국정온 알림·회의 원문·보고서·모델·공식자료·비용·수정 검증 결과.
- `evidence/*version*`, `*sha256*`, `runtime.json`: 공통 버전·실행환경. 비밀 환경변수와 DB 접속정보는 추출하지 않았다.
- `tools/verify_evidence.py`: 모델·DB·네트워크 없이 실제 ZIP과 직접 인용 무결성을 재검증하는 Python 표준 라이브러리 도구.
- `tools/home-contract/`: 원래 수신 도구·스키마의 복사본. `tools/task_span_contract.py`는 원래 근거 검증 함수의 복사본이다.
- `code-excerpts.md`: 질문에서 인용한 코드의 함수·행·해시 및 관련 발췌.
- `evidence/national-export-only.patch`: 이번 세션의 좁은 출력 수정만 포함. 다른 세션의 미커밋 변경은 배포 패치에 섞지 않았다.

사용자 계정·구독자 식별자·개인별 감지 문구·수신자·비밀키·인증정보를 증빙용 조회에서 제외했다. 공개 회의 발언·공적 직무자의 성명은 원문 검증을 위한 출처 정보다. 제출본은 자동 문자열/키 검사와 선택 파일 검토를 거치며 검사 범위와 결과를 `evidence/package-safety-review.json`에 기록한다. 원문 PDF·개별 운영 DB·환경 파일·전체 컨테이너 로그는 넣지 않는다. N-08 설정 파일과 별도 확장 시험 분석은 제출 패키지에서 제외한다.

초기 필드 검사 파일의 58/66 및 8건 목록은 **한 필드만 센 중간값**이다. 최종 수치는 `national-task-final-verification.json`의 62/66과 4건 보류다. 원본과 정정된 감사 경로를 함께 남겨 결과의 변화를 추적할 수 있게 했다.

## F. 더주택 원천 구조와 사업 동일성 사례

| 원천·실제 사례 | 형식·관리 식별정보 | 관리 단위·해석 | 연결 시 필요한 검증 | 근거 |
|---|---|---|---|---|
| 일반 건축 인허가 | API 응답의 mgmPmsrgstPk, namespace ArchPmsHubService.mgmPmsrgstPk | 허가 관리키이며 LH 모집공고 ID와 별개 | 위치·대지·사업·블록 대응 확인; 원천키 존재 인정 | `backend/general_building_permits.py` |
| LH 왕숙2 A01/A03 모집 자료 | LH 공고 panId; 현재 project 자료의 district/block/name/rows | A01·A03 표기와 공고별 부분 모집 범위 | A-1BL·A-3BL과 대조; 공식 착공 1,100과 모집 812+686=1,498은 별개 | [왕숙2 검토](evidence/home-wangsuk2-20261017.json), [원천 필드](evidence/home-source-examples.json) |
| LH 시흥거모 S-1 보도자료 | HTML 문서 list_no=12169, document_evidence | 문서 ID이며 사업키 아님; 공공분양 300호 공급 기사 | 기존 시흥거모 S1과 연결, 보도자료 중복 사업 등록 방지 | [LH 원문](https://www.lh.or.kr/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12169), [처리 전후](evidence/home-officer-20261105.json) |
| LH 왕숙 S-18 공사진행 | bzdtCd=105175, hcBlkCd=22, 블록 S-18 | 지구·공사블록 진행자료; 왕숙2 A01/A03와 별개 | 지구명 유사성만으로 같은 사업으로 연결하지 않음 | [원천 필드](evidence/home-source-examples.json) |
| SH 연남동 공공임대 | PDF A0069855.pdf 79쪽, 기존 PRO_b8e9b07eb43ee60a807ec231 | 문서 페이지·기존 사업 대응; 확인 8호 | 기존 사업 재사용, 신규 물량 합산 금지 | [원천 manifest](evidence/home-yeonnam-source-20261020.json), [반영 기록](evidence/home-yeonnam-20261020.json) |

확인된 문제는 기관 간 공통 식별·관리 범위의 불일치다. 다음은 **개발 과정의 표준화 제안**이며 이미 운영 중인 범정부 표준이라고 주장하지 않는다.

| 제안 필드 묶음 | 필요 내용 | 줄일 수 있는 반복 검토 |
|---|---|---|
| 사업 식별 | 공통 project_id, 원천 source_namespace/source_object_id, 상·하위 지구/블록 관계 | 기관별 ID와 명칭의 재대조 |
| 공간·범위 | 법정동/지구/블록, 위치, 전체·부분 scope_id, 중복 여부 | 같은 지구 다른 블록·부분 모집 혼합 |
| 단계별 사건 | event_id, stage, 계획/실적, 발생일·발표일·기준일 | 모집·계약·착공·입주 시점 혼합 |
| 수량 | units, 단위, 전체/부분, 중복 집계 규칙 | 서로 다른 사건 물량의 단순 합산 |
| 근거·판본 | 원문 URL, 문서 페이지·구간, content_hash, revision, supersedes, 검토 상태 | 정정 자료와 과거 값의 혼동 |

## G. 정책 1개·사업 3개 원천 대조

정책 `POL_2025_0907`의 기준은 2026~2030 수도권 착공 목표다. 기존 ZIP에 들어 있는 2026-11-10 정책 출력 기준이며 신규 전수 조회가 아니다.

| 대상 | 확인 수치·원천 사건 | 심사에서 설명할 범위 | 제한 |
|---|---|---|---|
| 9·7 주택공급 확대방안 | 목표 1,350,000호; 식별 배정 91,849호; 미식별 유보 1,258,151호; 식별률 약 6.8036% | 식별/미식별을 드러내는 관리 화면 | 달성률 아님; 검토 중 매핑 포함; 관리 사업 232개와 cohort 77개의 분모 다름 |
| 시흥거모 S1 | 2026-10-23 공급 공고 300호, REVIEW | 기존 사업과 공고 원천의 대응 | 계약·입주·확정 정책 착공 실적 아님 |
| 안산신길2 A6 | 2026-10-30 공급 공고 251호, 부분 모집 범위 | 같은 사업의 전체 계획과 부분 모집 구분 | 251호를 사업 전체 물량으로 대체하지 않음 |
| 과천지식정보타운 S-12 | 2026-10-28 공급 공고 1,424호, 검토 대상 | 관리 사업 목록·공고 추적 | cohort와 동일 집합 아님; 검토 중 수치를 확정 정책 실적으로 사용 금지 |

근거: [정책 출력](evidence/home-policy-plan-97.json), [사업 목록](evidence/home-projects-policy-delivery-97.json), [상세 정책 뷰](evidence/home-S1-view-policy.json). [화면 캡처](evidence/home-policy-screen-20261023.png)는 **2026-10-23 과거 화면**이므로 위 11-10 수치를 보여주는 현재 화면이라고 설명하지 않는다. 사업별 최신 실화면 캡처 3건은 이번 패키지에서 확보하지 못했으며 API/저장 출력 대조로 보완했다.

## H. 실제 ZIP 격리 수신 재현

ZIP은 새로 생성한 모의자료가 아니라 기존 생성 작업 `8e5d063476864013ac7a577efd51c822`의 실제 운영 산출물이다. 입력 변경 구간은 2026-10-22 00:00 KST 이후~2026-11-10 17:53:01.171 KST까지다. ZIP SHA-256은 `3cf27ef962a3c939755dd6d2bdf5751e64d4a68130087a8dbb10b8a364ab2239`다.

31종 목록: area_stat, block_location, collection_link, delivery_setting, district, document_evidence, evidence_bridge, execution_schedule, gh_notice, home_audit, home_batch, home_identity_alias, home_mapping, home_program_mapping, home_project, lh_completion_plan, lh_movein_plan, lh_notice, mapping_decision, municipality, notice, policy, policy_delivery_plan, policy_municipality, project, project_location, project_profile, project_report, stage_evidence, statistic, unsold.

이는 **데이터 종류 31개**이며 기관 수 31개가 아니다. manifest에 열거된 106개 파일은 슬라이스 31개·API 출력 10개·웹 코드 4개·golden 출력 61개다. ZIP에는 manifest 자체를 포함해 107개 멤버가 있다. 전체 슬라이스 39,359행은 여러 엔터티 종류의 합이며 고유 사업 수가 아니다.

압축을 해제한 패키지 폴더에서 실행한다.

```sh
python3 tools/verify_evidence.py
```

Python 3.10 이상과 표준 라이브러리만 필요하다. 임시 폴더에서 원래 수신 도구의 `read_package`와 `Slice.check_row`로 해시·행 수·허용 필드를 검사한다. DB·네트워크·모델은 사용하지 않는다. 이 자료는 delta ZIP이므로 완전한 수신 원장 복원에는 적합한 기준 판이 추가로 필요하다. 실제 기존 수신 원장에 delta를 합병하는 시험은 하지 않았고, full/delta 합병 동작의 합성 회귀시험은 별도로 통과했다.

## I. 행안위 원문·보고서·과제 대조

| 비교 대상 | 실제 저장 결과 | 해석 |
|---|---|---|
| 시간순 원문 | 4,573 segment, 보고서 기준 발언 수 1,029 | 저장 구간 수와 발언 단위를 구분 |
| 구조화 입력 | atom 628개, 분류 628개 | 입력 atom의 구조적 분류 포괄이며 원문 전체 의미 정확도 아님 |
| 주제별 보고서 | 표시 상위 주제 46개, 쟁점 349개, 서술 요약 349개 | 서술 포함 상태 COMPLETE는 내용 무오류를 뜻하지 않음 |
| 후속 과제 | 66개, 근거 ID 66개, 쟁점 ID 65개 | ID 존재와 직접 인용 무결성 구분 |
| 직접 인용 | task_evidence_spans 존재 58개, request_spans 존재 7개, 중복을 제외한 유효 과제 62개 | 두 필드 합집합을 원문·해시·판본과 검사. 58+7=65를 그대로 쓰면 중복 오류 |
| 검토 필요 | 4개; 한강버스, 친밀관계폭력 법률, 소방 정신건강, 지방계약 평가 | 직접 근거가 검증된 정책 확약으로 표시하지 않음 |
| 출력 보완 | 4개 보류 과제의 표시가 주제 본문과 과제 목록에 각각 나타나 총 8회 | 경고 8회를 과제 8개로 세지 않음 |

원본: [전체 발언 기록](evidence/national-interior-transcript.json), [보고서 JSON](evidence/national-interior-report.json), [운영에서 받은 Markdown](evidence/national-interior-report.md). 보완 검증: [최종 직접 인용 검사](evidence/national-task-final-verification.json), [미배포 로컬 출력본](evidence/national-interior-report-reviewed.md).

본 보고서는 원문 기반으로 확인할 수 없는 약속을 만들어 빈칸을 채우지 않는다. 특히 “적극 공감”과 같은 답변, 넓은 주제와 여러 법률의 일반적 언급, 문제 제기만으로 과제의 확정 이행 약속을 판정하지 않는다. 별도 담당자의 의미 검토가 필요한 이유다.

## J. 이번에 완료한 보완과 검증 결과

| 보완 | 실제 변경·산출물 | 검증 | 운영 반영 |
|---|---|---|---|
| 더주택 연계 증빙 강화 | 실제 기존 ZIP을 읽는 독립 도구와 데이터 목록·해시·재현 명령 | 31종·39,359행·106개 파일 검사 PASS | 운영 변경 없음 |
| 국정온 과제 감사 정밀화 | 인용 필드 2종을 함께 검증, 62개 직접 근거·4개 보류 확정 | 실제 저장 자료로 반복 실행 PASS | 데이터 수정 없음 |
| 국정온 문서 출력의 검토 상태 보존 | `_meeting_brief_markdown`의 세 과제 출력 경로에 REVIEW_REQUIRED 표시 추가 | 집중 회귀 5건 PASS; 실제 66과제 자료의 입력 불변·4개 보류 표시 확인 | **로컬 수정, 미배포** |
| 국정온 출력 시각의 의미 명확화 | “생성 시각”→“기초 보고서 저장 시각” | 회귀시험 및 실제 출력본 확인 | **로컬 수정, 미배포** |
| 심사 제출 준비 | 17개 질문·평가기준표·핵심 증빙·확정 문구·과장 수정·인덱스 | 문구 길이·코드 심볼·증빙 링크 검사 | 문서 산출물 |

시험 결과는 다음처럼 구분한다.

- 더주택: 데이터셋·승인 규칙·동일성 관련 격리 회귀 **41 passed**. 합성 시험을 운영 승인 규칙 실적으로 계산하지 않는다.
- 국정온 보완: 출력 보류 표시와 원문 근거 검증 관련 **5 passed**.
- 국정온 확장된 관련 시험: **8 passed, 1 failed**. 실패는 기존 `test_meeting_brief_schema.py::MeetingBriefSchemaTests::test_api_and_beta_ui_link_results_to_evidence`가 현재 웹 소스에서 예전 문자열 `if (ended.meeting_brief?.brief)`을 찾는 검사다. 이번 수정은 백엔드 Markdown 함수에 한정되며 해당 웹 파일·기존 검사 파일을 바꾸지 않았다. 전체 회귀 통과로 표현하지 않는다.
- 별도 실행의 공식자료·정책 흐름·캐시 관련 결과는 보존하되 N-08 관련 검사를 이번 확장성 증거로 사용하지 않는다. 초기 도구 환경의 pydantic_settings 누락은 검증 환경 의존성 문제이며 서비스 장애로 산정하지 않는다.
- 실제 데이터 재현: `portable-verification.json`과 `national-task-final-verification.json` 확인. 신규 모델 호출 0, 운영 DB 쓰기 0.

점수 확보를 위한 다음 작은 단계는 확보한 원장과 파일을 그대로 쓰는 **작품별 5분 시연 녹화**와 기존 사용자에게 이미 있는 **실제 업무 활용 증빙의 비식별 첨부**다. 새 성과를 가정해 비용·시간 절감률을 기재하는 대신 실제 작동과 원문 검증을 보여주는 편이 현재 증빙 수준에 맞다. 문광위 시연은 별도 세션의 결과만 연결한다.

### 제출용 ZIP 비식별 처리 기록

원본 실제 ZIP은 로컬에 보존하고 제출 패키지에는 `home-slices-submission-redacted.zip`을 넣었다. 공개 원문 발췌 1개 파일의 이메일·전화번호·담당자 연락처 문구를 비식별 처리했으며, 31종 슬라이스 데이터 행은 변경하지 않았다. 해당 파일의 manifest 해시를 다시 계산하고 같은 수신 도구로 재검증했다. 따라서 원본 ZIP 해시와 제출본 해시는 다르다. [비식별 처리 내역 및 두 해시](evidence/home-submission-redaction.json)를 함께 확인해야 한다. 원본 106개 파일 검사 결과는 `home-slices-verification.json`, 제출본 재검증은 `portable-verification.json`에 구분해 기록했다.
