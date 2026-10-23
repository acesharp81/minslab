"""Finish the established DB handoff with current changes, checksums and recipient notes."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from zoneinfo import ZoneInfo
import zipfile

ROOT=Path(__file__).resolve().parents[1]
KST=ZoneInfo('Asia/Seoul')
DOCKER=['sudo','docker']


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
 folder=Path(sys.argv[1]).resolve()
 if folder.parent!=ROOT/'backups':raise ValueError('Expected a HOME backups directory')
 m=json.loads((folder/'manifest.json').read_text());assert m['restore_verified']
 clean=json.loads((folder/'temporary-resource-cleanup.json').read_text());assert clean['container_and_anonymous_volume_removed']
 if (folder/'restore-attempts.json').exists():
  attempts=json.loads((folder/'restore-attempts.json').read_text());attempts['retry_status']='FULL_RESTORE_VERIFIED';save(folder/'restore-attempts.json',attempts)
 if (folder/'restore-postdata-resume.json').exists():
  verification=json.loads((folder/'restore-verification.json').read_text())
  if 'restore_seconds' in verification:verification['postdata_resume_and_verification_seconds']=verification.pop('restore_seconds')
  verification['snapshot_to_verification_seconds']=round((datetime.fromisoformat(verification['verified_at'])-datetime.fromisoformat(m['snapshot_at_kst'])).total_seconds(),2)
  verification['time_scope_note']='Post-data resume timing excludes earlier successful table loading and index work.'
  save(folder/'restore-verification.json',verification)
 s=json.loads((folder/'schema-comparison.json').read_text())
 d=json.loads((folder/'data-comparison.json').read_text())
 previous=json.loads((ROOT/'backups'/m['previous_package']/'manifest.json').read_text())
 evidence={
  'docs/analysis/reason_restore_and_future_20261022/verification.json':'data-review-verification.json',
  'docs/analysis/reason_restore_and_future_20261022/restoration_cases.csv':'restoration-cases.csv',
  'docs/analysis/reason_restore_and_future_20261022/future_plan_coverage.csv':'future-plan-coverage.csv',
  'data/remediation/review-restore-20261022/applied.json':'reviewed-estimates-applied.json',
  'data/remediation/future-plan-review-20261022/applied.json':'future-plans-applied.json',
  'data/remediation/verified-starts-20261022/applied.json':'verified-starts-applied.json',
  'docs/evidence/HOME_LOADING_FIX_20261022/verification.json':'loading-fix-verification.json',
 }
 for source,target in evidence.items():shutil.copyfile(ROOT/source,folder/target)
 rows=d['tables'];kinds=d['current_revision_kinds']
 table='\n'.join('| '+key+' | '+f"{item['previous']:,}"+' | '+f"{item['current']:,}"+' | '+f"{item['delta']:+,}"+' |' for key,item in rows.items() if item['delta'])
 kindtable='\n'.join('| '+key+' | '+f"{item['previous']:,}"+' | '+f"{item['current']:,}"+' | '+f"{item['delta']:+,}"+' |' for key,item in kinds.items() if item['delta'])
 schema_label='동일' if s['physical_schema_identical'] else '차이 있음: schema-comparison.json 확인'
 changes=f'''# the주택 DB 공유본 변경사항 · 2026-10-22

## 비교 기준과 패키지 성격

- 이전 실제 전달본: `{m['previous_package']}` / {previous['snapshot_at_kst']}.
- 이전본은 `restore_verified=false`, `IN_PROGRESS_TEST_ONLY`인 테스트본입니다. 이번 패키지는 별도 격리 DB에 **전체 복원·검증한 공유본**입니다.
- 이번 스냅샷: **{m['snapshot_at_kst']} (Asia/Seoul)**. 수집이 동시 진행되어도 manifest와 덤프는 동일한 읽기 전용 트랜잭션 스냅샷입니다.
- PostgreSQL {m['postgresql']}, PostGIS {m['extensions'].get('postgis')}, Alembic `{m['alembic_version']}`.
- 사용자·확장 테이블 {len(m['row_counts'])}개. 이전 대비 물리 DDL: **{schema_label}**. 확장 테이블을 포함하므로 업무 테이블만53개라는 뜻은 아닙니다.
- 전체 교체용 PostgreSQL custom 덤프입니다. 기존 DB에 추가 실행하는 증분 병합 파일이 아닙니다.

## 실제 DB 데이터의 차이

| 테이블 | 이전 | 이번 | 증감 |
|---|---:|---:|---:|
{table}

| 현재 판본 kind 중 변경된 항목 | 이전 | 이번 | 증감 |
|---|---:|---:|---:|
{kindtable}

전체 표는 `data-comparison.json`에 있습니다. `home_revision`은 원천·담당자 자료의 과거 판본까지 포함한 행 수이며 사업 수나 공급 실적이 아닙니다. `home_metric_snapshot` 증가도 업무 물량 증가가 아닙니다.

## 담당자 검토값 복구와 근거

1. 기존 개별 채택 사유67개를 재검토하여 **43개 사업의64개 단계 항목(사업화40·인허가24)**을 복구했습니다. 과거 일괄 규칙 적용으로 지워진 담당자 관리 추정값을 원 채택 사유와 함께 복구한 것입니다.
2. `project_profile.progress.<STAGE>.input_rule=REVIEWED_MANAGEMENT_ESTIMATE`, `inferred=true`를 보존합니다. `restoration_review`에는 원 판본·채택자·사유·규칙, 복구 사유, 검토값과 SHA-256을 남깁니다. 이를 새로 입수한 공식 실측값으로 바꾸어 표시하지 않습니다.
3. `backend/measurement_estimates.py`는 복구값의 날짜·범위·원 사유·해시를 검사합니다. 새 원천과 충돌하거나 값의 검토 해시가 달라지면 자동 보존하지 않습니다. JSON의 검토 메타데이터를 지우면 같은 결과를 보장할 수 없습니다.
4. 관리 추정은 빈 항목을 무조건 목표와 같게 채우는 규칙이 아닙니다. 선후 사건·현재 범위·기준일·원천 충돌을 확인하며, 추정값을 독립적인 실제 사건 증거로 재사용하지 않습니다.
5. 검단AA10-1 1,458호와 광주역세권316호의 근거를 재검토해 착공 관리값 합계1,774호를 복구했습니다. 광주역세권은 준공 확인316호를 추가했습니다. 이 작업으로 공급·입주 실적을 추가하지 않았습니다.

반영 목록·판본은 `reviewed-estimates-applied.json`, `verified-starts-applied.json`, 원 채택 사유와 개별 결정은 `restoration-cases.csv`에서 확인합니다.

## 2027년 계획의 반영과 남은 검토

- 공식2027년 수도권 공공분양 계획45개·26,695호 중, 이번 검토는 기존 관리사업6개의 공급 일정4,628호를 보완했습니다. 근거 연결4개와 신규 목표3개를 추가하고 기존 추정 목표3개를 수정했습니다.
- 예정 공급일은 실제 착공·공급 사건이 아닙니다. 기존 사업의 일정 보완이므로 관리사업177개·원천 사업452개와 사업화 총량이 늘어나는 수정이 아닙니다.
- 현재45개 계획 중16개가 연결됐고 **29개·16,497호는 원장 사업과 미연결**입니다. `future-plan-coverage.csv`에 항목별 상태를 제공합니다. 미연결 계획을 정책 실적으로 가산하지 않았습니다.
- 복구 검토 **3개 단계 항목은 보류 상태**입니다: 광교A17 사업화·인허가, 수원당수2A3 인허가. 저장된 보류 사유·수량 범위·샘플 원천 구분은 `restoration-cases.csv`와 `data-review-verification.json`을 확인합니다. 이후 추가로 확인한 원문이나 연구 내용도 DB에 채택되지 않았다면 이번 덤프의 확정값으로 해석하지 않습니다.
- 이 공유본은 **현재 저장 상태를 전달하는 덤프이며 모든 데이터 정리가 완료된 기준본은 아닙니다.** DB 복원 검증의 완료와 업무 데이터 검토 완료를 구분합니다.

## 정책 집계 및 그래프를 읽는 방법

현재 정책 관리범위는177개 관리사업입니다. 별도 시각의 읽기 전용 앱 조회값(`application-projection.json`)에서 추정 포함 현재 누적은 사업화152,802호, 인허가99,462호, 착공81,131호, 공급35,410호, 입주 미측정입니다. 이 파일의 `captured_at_kst`는 DB 덤프 스냅샷 시각과 구분합니다. 정확한 DB 건수는 `manifest.json`을 기준으로 합니다.

- 화면 아래부터 사업화 → 인허가 → 착공(건설) → 공급 → 입주 순서입니다.
- 각 단계의 실색 물량은 **해당 단계 누적 − 다음 단계 누적**입니다. 붉은 사선은 `max(목표 단계 물량 − 실제 단계 물량, 0)`이며 `미달성(공급)`처럼 표시합니다. 누적값 자체를 단계마다 중복으로 쌓지 않습니다.
- 부족 비율은 `부족분 / (부족분 + 해당 단계 누적 달성분)`입니다. 알 수 없는 값은0으로 바꾸지 않습니다.
- 미래는 현재의 단계별 `max(실제 물량, 목표 물량)`에서 시작해 저장된 계획의 날짜별 증가분을 반영합니다. 후속 단계로10호가 전환되면 전 단계에서10호를 빼고 후속 단계에10호를 더합니다.
- 미래는 연한색, 현재까지는 진한색으로 구분하고 날짜 사이를 곡선으로 연결합니다. 전환 기준은 데이터의 현재일이며 조회용 기준일 입력을 바꿔도 이 전환일은 움직이지 않습니다.
- Y축 상한은 **현재 화면에 보이는 기간의 누적 최대값×약1.3**입니다. 전체 목표 범위 선택은 별도입니다.
- 현재 누적 카드, 원천 비교용 `actual_points`, 추정 포함 `tracking.actual_points`, 미래 계획 `tracking.forecast_points`, 그래프의 단계별 예상 면적은 서로 다른 표현이므로 하나의 수치로 치환하지 않습니다. 화면 결과는 `web/assets/policy-stage-flow.js`와 `policy-907.js`의 현재 로직을 함께 사용합니다.
- DB 원장의 후보·해제·과거 판본·후속정책 관련관계를 전부 합산하지 않습니다. 현재 판본, 승인 매핑, 정책 귀속, 동일사업 중복 제외, 기준일·단계·수량 범위를 적용합니다.

## 앱 화면·성능 변경: DB 복원과 별도로 적용할 내용

- 정책·프로그램 보고서와 사업별 보고서의 구성을 구분했습니다. 사업 보고서는 추진 현황과 입지 분석을 중심으로 정리했습니다.
- 단계 선택 카드·버튼 연결, 공급 명칭, 누적 순서, 범례 색상, 곡선, 미래색·붉은 갭, 날짜 기준선과 카드 연동을 보완했습니다.
- 처음·현재·마지막·사업화 버튼을 한 행으로 배치하고, 처음은 포함 사업의 가장 이른 시작점으로 이동합니다. 내부 세로 스크롤을 제거했습니다. 사업 목록은 검색하기 쉽게 내림차순으로 정리했습니다.
- 왼쪽 메인 메뉴 이름을 **매뉴얼 → 문서**로 변경했습니다.
- 그래프가 같은 날짜 시계열을 반복 정렬·계산하던 부분을 한 번의 계산 동안 재사용하도록 개선했습니다. 동일 조건 비교에서 첫 그래프 표시가 약6.8초→1.7초로 줄었으며 SVG 전체 결과가 동일함을 확인했습니다. 측정값은 해당 환경의 비교값이며 모든 접속의 고정 응답시간을 의미하지 않습니다.
- 입지 분석에서 지역 산업 통계와 전국 비교값이 모두 없을 때 발생하던 `Cannot read properties of null (reading 'total')` 오류를 수정했습니다. 미확보 항목을 비워 두고 나머지 지표는 계속 표시합니다. 인천송림4 실제 화면과 관련38개 검증을 통과했습니다.

주요 앱 파일의 SHA-256은 `application-code-fingerprints.json`에 있습니다. 17개 파일은 생성 시점 작업공간과 실행 중 API의 내용이 같았습니다. 미커밋 변경이 있어 커밋ID 하나만으로 동일 앱을 보장하지 않습니다. **앱 소스 자체는 이전 규격과 같이 이 DB ZIP에 포함하지 않습니다.**

## 스키마·JSON 계약과 수신 측 적용

- Alembic 현재 버전은 `{m['alembic_version']}`입니다. 이번 덤프와 비교 대상의 물리 DDL은 {schema_label}입니다. 세부 SQL은 `schema.sql`과 `schema-comparison.json`을 확인합니다.
- 공급유형은 기존 JSON·앱 분류 구조입니다. `supply_type`, `supply_type_basis`, `supply_type_evidence_url`, `supply_type_assessment` 및 `project_profile.overrides`의 담당자·사유를 보존합니다. `PUBLIC`, `PURCHASE_NEW`, `PRIVATE_RENEWAL`, `OTHER_PRIVATE`, `PUBLIC_SUPPORTED_RENT`, `UNKNOWN`, `MIXED`를 수용합니다. 분류 확인을 정책 귀속·단계 완료의 확인으로 대신 쓰지 않습니다.
- `policy_relationship.aggregate_into_parent=false`인 후속 관계는 원 정책 물량에 자동 가산하지 않습니다. `quantity_attribution_status`, `reference_only`, `excluded_from_new_quantity`를 보존합니다.
- 전체 최신 데이터를 쓰려면 **별도 빈 DB에 전체 복원**한 후 앱을 연결합니다. `alembic upgrade head`는 담당자 입력·수집 판본·매핑 데이터를 옮기는 명령이 아닙니다.
- 수신 환경에서 이미 바꾼 데이터를 덮어쓰거나 임의 병합하지 않습니다. 이번 파일은 기존 변경을 합치는 SQL을 제공하지 않습니다.
- 처음 대조할 때 `POC10_AUTO_COLLECT=false`와 수집worker 미실행 상태를 사용합니다. 이후 수집이 시작되면 manifest의 고정 건수와 달라질 수 있습니다.
'''
 (folder/'SCHEMA_AND_DATA_CHANGES.md').write_text(changes)
 readme=f'''# the주택 DB 공유·복원 안내

스냅샷: **{m['snapshot_at_kst']} (Asia/Seoul)**.

이전 전달본과 같은 PostgreSQL custom archive 규격입니다. `home.dump`에는 스키마·데이터·인덱스·제약조건·시퀀스·확장 및 담당자 입력·추정·매핑·변경 이력을 포함합니다.

별도 격리 컨테이너에 전체 복원하여 **{len(m['row_counts'])}개 사용자·확장 테이블의 행 수, 현재 kind별 건수, 확장 버전, 인덱스 유효성**을 대조했습니다. 운영 DB 내용·자원 한도를 변경하지 않았고 검증 컨테이너와 임시 볼륨은 제거했습니다.

먼저 [변경사항과 적용 방법](SCHEMA_AND_DATA_CHANGES.md)을 확인하세요. 보류3개 단계 항목과2027년 계획 미연결29개가 남아 있는 현재 상태를 공유합니다. 복원 검증 성공은 모든 업무 사실을 확정했다는 뜻이 아닙니다.

## 구성

- `home.dump`, `manifest.json`, `SHA256SUMS.txt`: DB와 정확한 스냅샷 명세·무결성 확인.
- `SCHEMA_AND_DATA_CHANGES.md`, `data-comparison.json`, `schema-comparison.json`, `schema.sql`: 이전 테스트본 대비 실제 차이와 적용법.
- `SHARE_MESSAGE.txt`: 조원에게 붙여 넣을 전달문.
- `restoration-cases.csv`, `future-plan-coverage.csv`, `*-applied.json`: 복구·보류·2027년 계획의 적용 기록.
- `application-code-fingerprints.json`, `application-projection.json`: 앱 식별과 별도 조회 시점의 정책 집계 참고.
- `restore-verification.json`, `temporary-resource-cleanup.json`, `credential-safety-check.json`: 검증 결과.
- `APPLICATION_README.md`: 현재 앱 안내의 사본.

앱 소스, DB 외부 원문 PDF/HTML, `.env`·런타임 환경파일, API 키·비밀번호·DB 로그인 역할/권한은 제외합니다. 원문 열람에는 해당 `data/raw/` 등 파일이 별도로 필요합니다. 입력자와 사유 등 업무 이력을 포함하므로 조원 공유 범위에서 보관합니다.

## 1. 무결성 확인

압축을 풀어 이 폴더 안에서 실행합니다.

```bash
sha256sum -c SHA256SUMS.txt
```

Windows PowerShell에서는 `Get-FileHash .\\home.dump -Algorithm SHA256`을 `manifest.json`의 `sha256`과 대조합니다.

## 2. 별도 DB 준비

새 비밀번호로 `restore.env`를 직접 만듭니다.

```dotenv
POSTGRES_USER=home
POSTGRES_PASSWORD=새로_정한_비밀번호
POSTGRES_DB=postgres
```

```bash
docker run -d --name home-import-db --env-file ./restore.env -p 127.0.0.1:15432:5432 -v home-import-pgdata:/var/lib/postgresql/data postgis/postgis:16-3.5
docker exec home-import-db pg_isready -U home -d postgres
```

기존 동명 자원이 있으면 다른 이름을 사용합니다. DB와 대형 인덱스를 복원할 여유 공간·메모리를 확보합니다. 생성 검증 환경의 임시 성능 설정을 운영 환경에 복사할 필요는 없습니다.

## 3. 복원

준비 완료 후 bash 등 파일 리디렉션을 지원하는 셸에서 실행합니다.

```bash
docker exec home-import-db createdb -U home -T template0 home_import
docker exec -i home-import-db pg_restore -U home -d home_import --no-owner --no-privileges --exit-on-error < home.dump
docker exec home-import-db psql -U home -d home_import -c "SELECT version_num FROM alembic_version; SELECT count(*) FROM home_revision; SELECT extname,extversion FROM pg_extension ORDER BY extname;"
```

고정 스냅샷 기대값: Alembic `{m['alembic_version']}`, 원천 판본 **{m['row_counts']['public.home_revision']:,}행**. 전체 테이블별 기대값은 `manifest.json`을 확인합니다. 예전 DB에 덧씌우는 방식으로 복원하지 않습니다.

## 4. 앱 연결과 확인

```dotenv
POC10_DATABASE_URL=postgresql+psycopg://home:새_비밀번호@DB호스트:15432/home_import
POC10_AUTO_COLLECT=false
```

비밀번호의 특수문자는 URL 인코딩합니다. 같은 Docker 네트워크면 DB호스트로 컨테이너 이름과5432포트를 사용합니다. 최초 대조 동안 별도 수집worker도 실행하지 않습니다.

동일 앱 소스와 외부 API 설정은 별도로 준비합니다. DB만 복원하면 예전 앱에 최신 추정 보존·집계·그래프·오류 수정 코드가 적용되는 것은 아닙니다. 필요한 코드의 내용 해시는 `application-code-fingerprints.json`을 확인합니다.

검증과 전체 건수 대조 후 수집을 시작합니다. 수집 이후 건수는 증가할 수 있습니다. 오류 발생 시 사용한 ZIP명과 복원 오류 로그를 함께 기록합니다.
'''
 if (folder/'restore-attempts.json').exists():
  readme+='\n## 복원 재시도 기록\n\n첫 시도는 이미지 초기화용 PostgreSQL이 최종 서버로 재시작되는 동안 연결이 종료돼 데이터 적재 전에 중단됐습니다. 초기화 완료 조건을 보완해 동일 덤프를 새 격리 컨테이너에서 다시 전체 복원했고 최종 대조를 통과했습니다. 최초 로그는 `restore-initial-attempt.log`, 최종 검증은 `restore-verification.json`에 구분해 남겼습니다.\n'
 if (folder/'restore-postdata-resume.json').exists():
  readme+='\n대형 인덱스 작업은 이미 커밋된 데이터·객체를 보존하고 미완료 post-data 객체만 카탈로그와 대조해 병렬로 재개했습니다. 마지막에 전체 행 수·확장·인덱스를 다시 대조했고, 스키마는 별도 빈 DB에 재복원해 추가 확인했습니다. 상세 명세는 `restore-postdata-resume.json`, 병렬 재개 전 중단 기록은 `restore-serial-attempt.log` 을 참고하세요.\n'
 if (folder/'schema-roundtrip-verification.json').exists():
  readme+='\n## 스키마 SQL 표기 차이\n\n전체 데이터 복원의 행 수·현재 원천별 건수·확장·인덱스 유효성은 통과했습니다. 별도 빈 DB의 전체 스키마 재복원으로, 두 인덱스 조건에서 배열 전체 varchar[]→text[] 변환이 요소별 변환으로 출력되는 동일 의미의 표기 차이를 확인했습니다. 원문 차이는 `restored-schema-difference.json`, 의미 비교 확인은 `schema-roundtrip-verification.json`에 보존했습니다. 실제 조건값이나 인덱스 이름 변경은 같은 것으로 처리하지 않습니다.\n'
 (folder/'README.md').write_text(readme)
 (folder/'SHARE_MESSAGE.txt').write_text(f'''조원 공유용 the주택 최신 DB 덤프입니다.

기준 시각: {m['snapshot_at_kst']} (Asia/Seoul)
파일: {folder.name}.zip
규격: 이전과 같은 PostgreSQL16 / PostGIS3.5 custom archive(home.dump).
검증: 별도 격리 DB 전체 복원 후53개 사용자·확장 테이블 건수, 현재 원천별 건수, 스키마·확장·인덱스 대조 완료.

이전 테스트본 대비 주요 변경:
- 원천 판본 {previous['row_counts']['public.home_revision']:,} → {m['row_counts']['public.home_revision']:,}행. 매핑452건 유지.
- 기존 채택 사유를 재검토해43개 사업64개 단계 관리 추정값 복구. 공식 실측과 구분하고 원 사유·판본을 보존했습니다.
- 근거가 확인된 착공1,774호 복구, 기존6개 사업의2027년 공급 일정 보완.
- 정책 그래프의 누적·미래 전환·붉은 미달성 표시·축·버튼을 정리했고, 반복 연산과 입지 분석 null 오류를 수정했습니다.
- 메인 메뉴 ‘매뉴얼’을 ‘문서’로 변경했습니다.

남은 상태: 복구 보류3개 단계 항목,2027년 계획 미연결29개·16,497호가 있습니다. 이를 이번 덤프의 확정 실적으로 가산하지 않았습니다.

압축을 풀어 README.md와 SCHEMA_AND_DATA_CHANGES.md를 먼저 읽고 SHA256SUMS.txt를 확인한 후 별도 빈 DB에 복원해 주세요. 앱 소스·API 키·DB 외부 원문 파일은 이전 규격과 같이 별도입니다. 최신 화면과 계산을 재현하려면 application-code-fingerprints.json에 적힌 현재 앱 코드도 함께 맞춰야 합니다.
''')
 app_readme=ROOT/'README.md';content=app_readme.read_text();start=content.index('최신 공유용 DB 덤프:');end=content.index('\n\n| 자료·코드',start)
 latest=f'''최신 공유용 DB 덤프: **{m['snapshot_at_kst']} 기준**.

- ZIP: [backups/{folder.name}.zip](backups/{folder.name}.zip)
- SHA-256: [backups/{folder.name}.zip.sha256](backups/{folder.name}.zip.sha256)
- 복원 안내: [backups/{folder.name}/README.md](backups/{folder.name}/README.md)
- 변경사항: [backups/{folder.name}/SCHEMA_AND_DATA_CHANGES.md](backups/{folder.name}/SCHEMA_AND_DATA_CHANGES.md)
- 조원 전달문: [backups/{folder.name}/SHARE_MESSAGE.txt](backups/{folder.name}/SHARE_MESSAGE.txt)
- 별도 격리 컨테이너 전체 복원 후 사용자·확장 테이블{len(m['row_counts'])}개의 행 수·현재kind별 건수·확장·DDL·인덱스를 대조했습니다. 운영 DB 내용·자원 한도는 변경하지 않았습니다.
- 이전 테스트본 대비 실제 건수 차이와 복구·일정 보완·앱 변경을 동봉했습니다. 보류3개 단계 항목과2027년 계획 미연결29개가 남아 있는 현재 상태의 공유본입니다.
- 앱 소스·DB 외부 원문·환경 인증값은 포함하지 않습니다. 주요 코드 해시, README 사본·복원 안내·체크섬을 포함합니다. 덤프는 Git/정적 웹 공개 대상이 아닙니다.

같은 형식의 기본 덤프 도구는 `scripts/backup_database.py`, 이번 격리 복원·패키지 작업은 `scripts/package_database_share_20261022.py`와 `scripts/finalize_database_share_20261022.py`를 사용합니다.'''
 app_readme.write_text(content[:start]+latest+content[end:]);shutil.copyfile(app_readme,folder/'APPLICATION_README.md')
 scanner=(ROOT/'scripts/scan_handoff_credentials.py').read_text()
 pending_scan=folder/'credential-safety-check.pending.json'
 if pending_scan.exists() and not (folder/'credential-safety-check.json').exists():
  print('WAITING_FOR_EXISTING_CREDENTIAL_SCAN',flush=True)
  for _ in range(90):
   try:scan_receipt=json.loads(pending_scan.read_text())
   except json.JSONDecodeError:scan_receipt=None
   if scan_receipt and scan_receipt.get('logical_dump_bytes_scanned'):
    if scan_receipt['secret_value_matching_rows'] or scan_receipt['credential_query_value_candidates']:raise RuntimeError('Credential scan reported candidates')
    if sha(folder/'home.dump')!=m['sha256']:raise RuntimeError('Dump changed during credential scan')
    scan_receipt['custom_dump_sha256']=m['sha256'];save(folder/'credential-safety-check.json',scan_receipt);pending_scan.unlink();break
   time.sleep(10)
  else:raise RuntimeError('Existing credential scan did not finish')
 prior_scan=json.loads((folder/'credential-safety-check.json').read_text()) if (folder/'credential-safety-check.json').exists() else {}
 if prior_scan.get('custom_dump_sha256')!=m['sha256']:
  print('CREDENTIAL_SCAN_STARTING',flush=True)
  with (folder/'home.dump').open('rb') as src,(folder/'credential-safety-check.json').open('wb') as out:
   restore=subprocess.Popen(DOCKER+['exec','-i','poc10-home-db','pg_restore','--no-owner','--no-privileges','--file=-'],stdin=src,stdout=subprocess.PIPE)
   scan=subprocess.Popen(DOCKER+['exec','-i','poc10-home-api','python','-c',scanner],stdin=restore.stdout,stdout=out)
   restore.stdout.close();scan_code=scan.wait();restore_code=restore.wait()
   if scan_code or restore_code:raise RuntimeError('Credential scan failed; inspect sanitized result counts')
 scan_result=json.loads((folder/'credential-safety-check.json').read_text());assert not scan_result['secret_value_matching_rows'] and not scan_result['credential_query_value_candidates']
 m['credential_safety_check']=dict(file='credential-safety-check.json',configured_secret_matches=0,credential_query_candidates=0,logical_dump_bytes_scanned=scan_result['logical_dump_bytes_scanned'],scope='Current configured credentials, encoded variants, and common credential query parameters; not a claim about unknown historical secrets')
 m['schema_comparison']=dict(file='schema-comparison.json',physical_schema_identical=s['physical_schema_identical'],previous_package=m['previous_package'])
 m['change_notes']='SCHEMA_AND_DATA_CHANGES.md';m['restoration_resource_cleanup']='temporary-resource-cleanup.json'
 m['app_code_fingerprints']='application-code-fingerprints.json';m['packaged_at_kst']=datetime.now(KST).isoformat();save(folder/'manifest.json',m)
 # No initial/pending files or build-status messages are needed by the recipient.
 (folder/'build-status.json').unlink(missing_ok=True)
 docs=[p for p in sorted(folder.iterdir()) if p.is_file() and p.name not in ['home.dump','SHA256SUMS.txt']]
 result=subprocess.run(DOCKER+['exec','-i','poc10-home-api','python','-c',scanner],input=b'\n'.join(p.read_bytes() for p in docs),capture_output=True,check=True)
 (folder/'documentation-credential-safety-check.json').write_bytes(result.stdout)
 files=[p for p in sorted(folder.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt']
 (folder/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in files))
 archive=folder.with_suffix('.zip');pending=archive.with_suffix('.zip.pending')
 print('ZIP_BUILD_STARTING',flush=True)
 with zipfile.ZipFile(pending,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
  for p in sorted(folder.iterdir()):
   if p.is_file():z.write(p,folder.name+'/'+p.name)
 with zipfile.ZipFile(pending) as z:
  if z.testzip() is not None:raise RuntimeError('ZIP CRC failure')
  if any(name.endswith('.env') or '/runtime/' in name for name in z.namelist()):raise RuntimeError('Unexpected environment file')
 pending.replace(archive);checksum=sha(archive)
 archive.with_suffix('.zip.sha256').write_text(checksum+'  '+archive.name+'\n')
 # Verify each digest from disk after final ZIP assembly.
 for line in (folder/'SHA256SUMS.txt').read_text().splitlines():
  expected,name=line.split('  ',1)
  if sha(folder/name)!=expected:raise RuntimeError('Checksum mismatch: '+name)
 result=dict(archive=str(archive),bytes=archive.stat().st_size,sha256=checksum,snapshot_at_kst=m['snapshot_at_kst'],restore_verified=True,tables=len(m['row_counts']),revision_rows=m['row_counts']['public.home_revision'],member_files=len(list(folder.iterdir())),raw_and_source_excluded=True,unresolved_review_cases=3,unlinked_2027_plans=29)
 save(archive.with_suffix('.verification.json'),result)
 print('PACKAGE_READY '+json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
