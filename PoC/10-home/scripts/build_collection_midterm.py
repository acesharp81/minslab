"""Build the standalone HOME collection scorecard from frozen local evidence.

Run from PoC/10-home:
    python3 scripts/build_collection_midterm.py --test-report docs/evidence/HOME_COLLECTION_MIDTERM_20261016/regression.xml

Rubric levels are analyst judgments. Ratios and benchmark counts are calculated.
No collection, database writes, external requests, or application changes occur.
"""
import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from html import escape
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
STEM = 'HOME_DATA_COLLECTION_MIDTERM_20261016'


def read(path):
    return json.loads((ROOT / path).read_text())


def rounded(value, places=2):
    return float(Decimal(str(value)).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP))


def criterion(code, name, weight, reason, next_step, evidence, *, level=None, ratio=None):
    assert (level is None) != (ratio is None)
    if ratio is not None:
        numerator, denominator = ratio
        assert denominator > 0 and 0 <= numerator <= denominator
        fraction = numerator / denominator
        method = '관측 비율'
    else:
        assert level in range(5)
        numerator = denominator = None
        fraction = level / 4
        method = '근거 등급'
    return dict(id=code, name=name, weight=weight, level=level, numerator=numerator,
                denominator=denominator, fraction=fraction, score=weight * fraction,
                method=method, reason=reason, next_step=next_step, evidence=evidence)


def build_data(test_report):
    folder = 'docs/evidence/HOME_COLLECTION_PIPELINE_20261016/'
    sources = read(folder + 'sources.json')['items']
    summary = read(folder + 'summary.json')
    requirements = read(folder + 'requirements.json')
    quality = read(folder + 'quality.json')
    audit = read('docs/OFFICIAL_ACCURACY_REVIEW_20261016.json')
    manifest = read('docs/HOME_COLLECTION_PIPELINE_MASTER_20261016.manifest.json')
    n_sources = len(sources)
    success = sum(s['status'] == 'SUCCESS' for s in sources)
    automatic = sum(not s.get('manual_only', False) for s in sources)
    m = lambda key: requirements['metrics'][key]['without_estimates']
    q = lambda key: (m(key)['count'], m(key)['total'])
    categories = []

    def category(code, name, group, verdict, items):
        for item in items:
            item['category_id'] = code
            item['category_name'] = name
        categories.append(dict(id=code, name=name, group=group, verdict=verdict,
                               items=items, weight=sum(i['weight'] for i in items),
                               score=sum(i['score'] for i in items)))

    c = criterion
    category('A', '원천 확보와 수집 실행', 'foundation', '등록 원천의 확보와 다형식 수집 기반은 갖췄다.', [
        c('A1', '등록 원천의 최근 성공 상태', 3, f'{n_sources}개 등록 원천 중 최근 상태가 SUCCESS인 원천은 {success}개다. 단일 관측 시점의 상태이며 장기 성공률은 아니다.', '원천별 최근 30일 성공률과 실패 지속시간을 측정한다.', ['sources'], ratio=(success, n_sources)),
        c('A2', '등록 원천의 자동 순회 대상 비율', 3, f'일반 자동 순회 대상 {automatic}/{n_sources}개, 수동 전용 {n_sources-automatic}개다. 대상 설정은 정시 실행 성공과 다르다.', '수동 원천별 실행 담당·기한·자동 전환 계획을 정한다.', ['sources', 'scheduler'], ratio=(automatic, n_sources)),
        c('A3', '페이지 완결성과 수집 중단 보호', 2, '페이지 누락·중복·총건수 변경을 거부하는 코드와 격리 회귀검증이 있다. 모든 기관·기간의 전수 검증은 아니다.', '핵심 원천마다 예상/수신 건수와 누락 재수집 결과를 남긴다.', ['coverage', 'regression'], level=3),
        c('A4', 'API와 비정형 자료의 정형화', 2, 'API·HTML·DOCX·PDF·공개파일을 실제 수집한다. 미지원 첨부와 기관별 상세 범위가 남아 있다.', '미지원 형식·양식 변경을 탐지하고 영향 필드만 재처리한다.', ['master', 'collectors'], level=3),
    ])
    category('B', '모집단과 수집 범위', 'facts', '등록 범위는 있으나 수도권 전체 사업 분모가 확정되지 않았다.', [
        c('B1', '추적할 전체 사업 명부와 분모', 4, '311개는 원천 사업 기록이다. 수도권 전체 실사업 명부와 대조한 완전한 분모는 확인되지 않는다.', '지역·공급방식·기관별 대상 명부와 판본을 구축한다.', ['master', 'identity', 'plan'], level=1),
        c('B2', '수도권 지역별 사업 수집 완결성', 4, '서울·경기·인천 경로가 있으나 일부 인천 수집·연결과 SH 상세의 공백이 기록되어 있다. 현재 잔여 범위는 재현 확인이 필요하다.', '지역별 누락 후보와 의도적 제외를 분리하고 대상 명부와 대조한다.', ['master', 'sources', 'quality'], level=2),
        c('B3', '공급방식별 실사업 수집', 4, '공공건설 중심의 연결 기반과 정비·허가 참고 원천은 있다. 일반 민간·매입·전세지원의 사건 원장까지 완결된 증거는 부족하다.', '공급방식별 대상 명부와 사건 수집 경로를 확장한다.', ['master', 'identity', 'plan'], level=1),
        c('B4', '지역·기간·페이지 커버리지 기록', 3, 'home_coverage와 원천별 조회 범위가 있다. 조회 완료와 모집단 전수 확보는 분리되며 미지원 원천별 범위가 남는다.', '모든 핵심 원천의 기간·지역·페이지 커버리지를 동일 계약으로 관리한다.', ['coverage', 'db', 'regression'], level=2),
    ])
    category('C', '사업 식별과 원천 연결', 'foundation', '안정 ID와 보수적 연결은 작동하며 전면 통합은 진행 중이다.', [
        c('C1', '원천 ID와 안정 사업 ID 관리', 3, 'home_project·별칭·원천 근거가 존재하고 중복 실행·담당자 재지정 검증을 통과했다.', '원천별 키 변경·사업 분할·병합 이력을 확장한다.', ['db', 'identity', 'regression'], level=3),
        c('C2', '참고 원천의 실사업 후보 승격', 3, '사업 앵커는 주로 kind=project에서 생성한다. 정비·허가 참고 자료가 관리사업으로 이어지지 않는 사례가 남아 있다.', '미연결 참고 원천에서 고유키·지역 기반 사업 후보를 생성한다.', ['identity', 'difference'], level=2),
        c('C3', '전체 조회의 실사업 ID 통일', 2, '기존 화면·매핑에는 PRO 원천 ID 경로가 남아 있다. HPR 발급이 전 경로의 고유 사업 통합을 뜻하지 않는다.', 'ID 대응표와 충돌함을 먼저 검증하고 조회 경로를 단계적으로 전환한다.', ['db', 'identity', 'master'], level=1),
        c('C4', '동명 사업과 오병합 방지', 2, '지역·블록·물량 충돌·모호한 복수 후보를 보류하고 확정·해제를 보호하는 회귀검증이 있다. 전체 매칭 오차율은 미측정이다.', '동명·별칭·복합사업 표본을 늘리고 오연결률을 별도 측정한다.', ['bridge', 'identity', 'regression'], level=3),
    ])
    category('D', '수집된 실적과 일정 근거', 'facts', '계획 자료보다 실제 단계의 비추정 근거가 적다.', [
        c('D1', '비추정 실적·진척 근거 확보', 5, '등록된 9·7 사업 197건의 985개 단계 셀 중 312개에 비추정 근거가 있다. 진행상태도 포함하며 실제 입주 호수 확보율은 아니다.', '기관 원천의 실제 사건일·인정 물량을 단계별로 확보한다.', ['requirements'], ratio=q('F-03')),
        c('D2', '목표와 실적 근거의 동시 확보', 4, '같은 985개 단계 셀 중 목표와 실적 근거를 함께 확보한 셀은 241개다. 최종 물량 범위 검증은 별도다.', '같은 사건·범위의 계획과 실적을 연결한다.', ['requirements'], ratio=q('F-02')),
        c('D3', '날짜가 있는 비추정 단계 계획', 3, '197개 사업 중 189개에 날짜가 있는 비추정 계획이 최소 한 단계 존재한다. 전 단계 일정 완비를 의미하지 않는다.', '각 사업의 필요한 모든 단계에서 최초·현재 계획을 확보한다.', ['requirements'], ratio=q('F-05')),
        c('D4', '비추정 최초 기준선 확보', 3, '최초 약속에 해당하는 비추정 기준선은 276/985개 셀에 등록돼 있다. 추정 포함 기준선은 분리 보존한다.', '최초 약속의 근거·승인 시점과 계획 변경 이력을 확보한다.', ['requirements'], ratio=q('F-06')),
    ])
    category('E', '물량과 기간 및 집계 정합성', 'facts', '주요 의미 구분과 중복 보호는 있으나 전 경로 일관성 검수가 남아 있다.', [
        c('E1', '계획·실제·추정과 시각 구분', 3, '일정·실제 사건·관측일·추정을 구분하고 미래 입주계획을 실적으로 만들지 않는 검증이 있다. 모든 원천의 공통 사건 계약은 보완 대상이다.', '모든 핵심 원천에 동일한 사건·기간·단위 계약을 적용한다.', ['delivery', 'bridge', 'regression'], level=3),
        c('E2', '전체·부분 물량 포함관계', 3, '주암 1,030/344, 검단 1,323=991+332, 계양 463/309 등 범위를 구분한다. 임의 비율 대신 구성 근거를 검사한다.', '지구·블록·공급구획·회차별 포함관계를 범용화한다.', ['bridge', 'master', 'regression'], level=3),
        c('E3', '중복 사건과 재공급 보호', 2, '반복 원천·추가모집·공유 공고를 무조건 더하지 않는 규칙과 테스트가 있다. 공고 취소·정정 계보의 범용 완결은 남아 있다.', '정정·취소·추가·재모집의 원사건과 회차 키를 통일한다.', ['bridge', 'delivery', 'regression'], level=3),
        c('E4', '원천에서 지도·CSV까지 같은 집계', 2, '저장 근거를 정책·지도에 전달하는 보완 코드와 공통 계산 테스트는 있다. C21/C49의 최신 운영 전 경로 일치까지 재검증한 것은 아니다.', '같은 기준시각·범위·검토수준의 상세·지도·차트·CSV를 비교한다.', ['delivery', 'quality', 'regression'], level=2),
    ])
    category('F', '원문과 판본 및 감사 추적', 'foundation', '가장 강한 기반이며 과거 사건 시점 재현을 더 확장해야 한다.', [
        c('F1', '원문 보관과 내용 해시', 3, '원문 manifest·SHA-256·수집 배치를 보존하며 중간 점검 동결 근거도 해시로 확인할 수 있다.', '새 원천에도 같은 보관·검사 계약을 적용한다.', ['db', 'master', 'accuracy_manifest'], level=4),
        c('F2', '변경 판본과 고정 근거 참조', 3, '원천 변경 시 새 판본을 만들고 선택한 근거 판본을 고정하는 코드 및 회귀검증이 통과했다.', '기관 정정·취소도 사건 판본과 연결한다.', ['db', 'bridge', 'regression'], level=4),
        c('F3', '담당자 확정·해제와 감사 보존', 2, '재수집으로 확정·해제를 덮지 않고 동시 수정 충돌과 이전 판단 근거를 보존하는 검증을 통과했다.', '신규 사건 검증 결정에도 같은 보호를 적용한다.', ['identity', 'bridge', 'regression'], level=4),
        c('F4', '발생시각과 인지시각의 과거 재현', 2, 'recorded_at·superseded_at과 사건·기준일이 있다. 지연 신고·과거 정정 후 임의 시각의 전체 집계 재현은 완결 검수 대상이다.', '사건 유효기간과 시스템 기록기간으로 기준시각 집계를 재현한다.', ['db', 'master', 'plan'], level=2),
    ])
    category('G', '연속 갱신과 실시간 추적', 'operations', '일·주 단위 수집 기반에서 사건 중심 연속 갱신으로 전환해야 한다.', [
        c('G1', '변경 탐지 주기와 처리 분리', 4, '자동 순회는 있으나 기본 일·일부 주 단위다. 긴 수집을 전체 잠금·순차 처리하므로 최신 변경 탐지와 분리되지 않았다.', '원천별 잠금과 최신 변경 전용 작업을 분리한다.', ['scheduler'], level=2),
        c('G2', '완료 지역의 재방문과 변경 수집', 4, '미완료 법정동 이어받기는 있다. 완료 동의 갱신 기한·변경 재방문 정책은 확인되지 않는다.', '완료 동의 다음 확인시각과 변경 조회 체크포인트를 관리한다.', ['master', 'scheduler'], level=1),
        c('G3', '후속 연결·검증·집계의 재처리', 4, '원천별 후속 작업은 조건부로 실행된다. 별도 영속 작업 큐·단계별 재시도·정시 처리 보증은 미완결이다.', '수집 이후 실패 구간을 독립 재처리하는 영속 작업 큐를 구축한다.', ['scheduler', 'plan'], level=1),
        c('G4', '포착부터 집계까지 지연 실측', 3, '원천 공개→포착→검증→화면 반영 P95와 발표 선행 포착률의 관측 근거가 없다. 처리시간을 추정해 점수를 주지 않았다.', '단계별 시각을 계측하고 1주 이상 표본으로 지연과 자료 나이를 산출한다.', ['plan', 'master'], level=0),
    ])
    category('H', '품질 점검과 운영 복구', 'operations', '오류 기록과 보호 장치는 있으며 폐쇄 검증·복구 실증을 강화해야 한다.', [
        c('H1', '파싱·범위·집계 회귀검증', 2, '이번 9개 테스트 파일의 71개 테스트·하위검사 2개가 통과했다. 운영 데이터 전체 정확도 검증과는 구분한다.', '대표 운영 사업의 원문→사건→집계 검증을 추가한다.', ['regression'], level=3),
        c('H2', '실패 격리와 정상 자료 보존', 1, '배치 오류·마지막 성공을 보존하고 iH 504를 미수집으로 구분한다. 원천·연결 단계의 실패를 따로 읽어야 한다.', '실패 지속시간·후속 실패 경보와 담당 대응기한을 운영한다.', ['scheduler', 'quality', 'sources'], level=3),
        c('H3', '품질 조치의 완료 검증', 1, '64개 조치 중 APPLIED_REVIEW_PENDING 46개, OPEN 6개다. 조치 이력은 상세하지만 구현 적용과 검증 완료는 구분된다.', '검토 잔여와 열림 건에 재현·해결·재검수 근거를 연결한다.', ['quality'], level=2),
        c('H4', 'DB와 원문 동시 복구 실증', 1, '백업·복원 확인 스크립트는 있다. 이번 평가 근거에 완료된 격리 복구 훈련 결과는 포함돼 있지 않다.', '격리 환경에서 DB·raw·승인·조회까지 복구한 결과를 남긴다.', ['backup', 'master'], level=1),
    ])
    category('I', '기관 책임과 실제 공급 성과', 'operations', '계약·실입주·기관 확인을 연결하는 데이터 확보가 우선 과제다.', [
        c('I1', '실제 계약·실입주 집계 확보', 2, '모집·입주예정·입주개시와 구분된, 기관별 실제 계약·실입주 집계의 확보 실증이 확인되지 않는다. 실제 입주가 없다는 뜻은 아니다.', '개인정보 없는 기관별 계약·실입주 집계와 정정을 제공받는다.', ['master', 'plan'], level=0),
        c('I2', '사건 확인 책임과 제공 계약', 1, '기관·출처·담당자 입력 기반은 있으나 사건별 확정 책임과 제공 마감을 합의한 지속 연계 실증은 부족하다.', '원천별 제공·확인 책임, 마감·정정·재전송 계약을 정한다.', ['master', 'plan'], level=1),
        c('I3', '승인된 기관 배정 목표 확보', 1, '등록된 9·7 사업 197건 중 기관 배정 목표 자료를 승인 등록한 사업은 0건이다. 입력 기능의 부재를 뜻하지 않는다.', '기관별 배정 목표의 단위·기간·책임·승인 근거를 등록한다.', ['requirements'], ratio=q('F-08')),
        c('I4', '병목 사실과 기관 조치 데이터', 1, '원인·기관·조치 입력 기반은 있지만 병목 기록 분모가 0이므로 자료 확보율은 산정 불가다. 실제 병목 운영 실증은 확인되지 않는다.', '원인·발생일·영향물량·책임·조치기한을 갖춘 실제 병목을 등록한다.', ['requirements', 'plan'], level=1),
    ])
    category('J', '자체 집계와 발표 재현 준비', 'operations', '근거 조회·출력은 가능하며 발표 기준본 자동 생성은 구축 대상이다.', [
        c('J1', '사업 사건으로 실적 직접 산출', 2, '자체 원천·승인 사건에서 집계하지만 등록 범위가 부분이고 실제 단계 근거가 부족해 전체 수도권 실적 산출은 미완결이다.', '같은 모집단·사건·기간의 검증된 사건 원장으로 직접 합산한다.', ['delivery', 'requirements', 'plan'], level=2),
        c('J2', '숫자에서 원천까지 근거 조회', 1, '연계 다이어그램·원문·판본·매칭 사유를 조회한다. 각 발표 숫자의 구성 사건 목록까지 고정하는 기능은 보완 대상이다.', '집계 응답에 구성 사건·제외 사유·판본을 연결한다.', ['bridge', 'master', 'regression'], level=3),
        c('J3', '고정 자료와 결과 반출', 1, 'CSV·MD·점검 보고서·manifest가 있다. 고정 점검 자료와 일상 발표 기준본 자동 발행은 서로 다른 수준이다.', '같은 집계 기준본에서 표·CSV·설명자료를 생성한다.', ['accuracy_manifest', 'master'], level=2),
        c('J4', '발표 기준본과 정정판 운영', 1, '지표 정의·구성 사건·검증 책임을 고정하고 지연 신고를 정정판으로 발행하는 운영 근거는 확인되지 않는다.', '기준시각·사건 판본·검토 결정을 고정한 발표 기준본을 발행한다.', ['plan', 'db'], level=0),
    ])
    items = [i for cat in categories for i in cat['items']]
    assert len(items) == 40 and sum(i['weight'] for i in items) == 100
    total = sum(i['score'] for i in items)
    groups = []
    for key, label in [('foundation', '수집·식별·근거 기반'), ('facts', '자체 실적 자료 완결성'), ('operations', '연속 추적·운영·발표')]:
        selected = [cat for cat in categories if cat['group'] == key]
        weight = sum(cat['weight'] for cat in selected)
        score = sum(cat['score'] for cat in selected)
        groups.append(dict(id=key, name=label, weight=weight, score=score, percent=score / weight * 100))

    paths = {
        'sources': (folder + 'sources.json', '등록 원천 상태', '2026-10-16 수집 구축 동결본'),
        'requirements': (folder + 'requirements.json', '등록 사업 자료 확보 지표', '197건·985단계 셀, 추정 제외 기준'),
        'quality': (folder + 'quality.json', '품질 조치와 점검 기록', '64개 조치의 각 기록일·범위 기준'),
        'master': ('docs/HOME_COLLECTION_PIPELINE_MASTER_20261016.md', '수집·정형화·연계 마스터', '2026-10-16 20:54~20:55 KST 관측'),
        'accuracy': ('docs/OFFICIAL_ACCURACY_REVIEW_20261016.json', '공식 발표 대조 결과', '21:49~21:51 KST API 수집과 별도 DB 읽기; 단일 동시 스냅샷 아님'),
        'accuracy_manifest': ('docs/OFFICIAL_ACCURACY_REVIEW_20261016.manifest.json', '대조 근거 manifest', '동결 입력의 경로·SHA-256'),
        'difference': ('docs/OFFICIAL_DIFFERENCE_CAUSE_REPORT_20261016.md', '차이 원인분석', 'R01~R11·53행 분류와 조사 필요사항'),
        'plan': ('docs/HOME_TRUSTED_REALTIME_PLATFORM_PLAN_20261016.md', '실시간 데이터 플랫폼 개선 계획', '이번 평가의 목표·우선순위 기준'),
        'db': ('backend/db.py', 'DB·판본·감사 모델', '현재 작업 트리 코드'),
        'identity': ('backend/identity.py', '실사업 식별과 검토', '현재 작업 트리 코드'),
        'bridge': ('backend/evidence_bridge.py', '고정 근거·범위 연결', '현재 작업 트리 코드'),
        'collectors': ('backend/collectors.py', '원천별 수집과 정형화', '현재 작업 트리 코드'),
        'coverage': ('backend/source_coverage.py', '수집 범위 정규화', '페이지 완결·모집단 상태 구분'),
        'scheduler': ('backend/service.py', '수집·후속 연결 실행', 'app.py·sources.py와 함께 검토'),
        'delivery': ('backend/policy_delivery.py', '정책 사건·실적 집계', 'supply_dashboard.py·map_progress.py와 함께 검토'),
        'backup': ('scripts/backup_database.py', 'DB 백업·복원 확인 도구', '스크립트 존재와 복구 완료 실증을 구분'),
    }
    evidence = {}
    for key, (path, label, scope) in paths.items():
        blob = (ROOT / path).read_bytes()
        evidence[key] = dict(id=key, path=path, href=('../' + path if not path.startswith('docs/') else path[5:]),
                             label=label, scope=scope, sha256=hashlib.sha256(blob).hexdigest(), bytes=len(blob))
    tests = dict(status='NOT_RERUN', tests=None, failures=None, errors=None, skipped=None,
                 note='현재 실행한 테스트 결과 없음')
    if test_report:
        blob = Path(test_report).read_bytes()
        tree = ET.fromstring(blob)
        suites = [tree] if tree.tag == 'testsuite' else list(tree.findall('testsuite'))
        tests = {key: sum(int(s.get(key, 0)) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
        tests.update(status='PASS' if tests['failures'] + tests['errors'] == 0 else 'FAIL',
                     primary_tests=71, subtests=2, completed_at=suites[0].get('timestamp'),
                     junit_sha256=hashlib.sha256(blob).hexdigest(),
                     note='9개 파일 · 71개 테스트 및 하위검사 2개 통과. 기관 API 실호출·운영 DB 전수 검증은 아님.',
                     files=['test_identity.py', 'test_evidence_bridge.py', 'test_collection_lineage.py', 'test_source_coverage.py',
                            'test_supply_progress.py', 'test_policy_delivery_comparison.py', 'test_map_progress.py',
                            'test_projection_cache.py', 'test_collection_coverage.py'])
        assert tests['failures'] + tests['errors'] == 0
        assert tests['tests'] == tests['primary_tests'] + tests['subtests'] == 73
    test_path = Path(test_report).resolve()
    relative_test_path = str(test_path.relative_to(ROOT)) if test_path.is_relative_to(ROOT) else None
    evidence['regression'] = dict(id='regression', label='이번 회귀검증 실행', scope=tests['note'], tests=tests,
                                  href=relative_test_path[5:] if relative_test_path and relative_test_path.startswith('docs/') else None,
                                  path=relative_test_path or '격리 fixture 검증', sha256=tests.get('junit_sha256'))

    benchmark = []
    for kind, rows in [('지표', audit['metrics']), ('사업 발표', audit['sites'])]:
        for row in rows:
            numeric = row.get('official_value') is not None
            eligible = bool(row.get('accuracy_eligible'))
            state = 'matched' if eligible and row['status'] in ('MATCH_EXACT', 'MATCH_ROUNDED') else 'pending' if numeric else 'excluded'
            label = '공적주택 입주 추진 계획' if row['id'] == 'M22' else row['name']
            period = '기준시점 재확인 필요 · 8월 말/10월 둘째 주 표기 대사' if row['id'] == 'M14' else row.get('official_period')
            benchmark.append(dict(id=row['id'], name=label, original_name=row['name'], kind=kind, stage=row.get('stage'),
                                  official_value=row.get('official_value'), official_upper=row.get('official_upper'),
                                  unit=row.get('unit') or '호', official_period=period, original_period=row.get('official_period'),
                                  actual_value=row.get('actual_value'), actual_scope=row.get('actual_scope'),
                                  numeric=numeric, eligible=eligible, state=state, status=row['status'],
                                  explanation=row['explanation'], official_url=row.get('official_url')))
    counts = Counter(b['state'] for b in benchmark)
    numeric = sum(b['numeric'] for b in benchmark)
    assert len(benchmark) == 53 and numeric == 47
    assert counts == dict(matched=3, pending=44, excluded=6)
    exact = sum(b['eligible'] and b['status'] == 'MATCH_EXACT' for b in benchmark)
    comparable = sum(b['eligible'] for b in benchmark)
    assert exact == audit['summary']['exact_matches'] == 1
    assert comparable == audit['summary']['direct_numeric_count'] == 3
    assert counts['matched'] == audit['summary']['display_compatible'] == 3
    assert sources and summary['current']['sources'] == manifest['data_sources'] == success
    assert sum(g['rows'] for g in summary['groups']) == manifest['latest_rows']
    for file, digest in manifest['evidence_sha256'].items():
        assert hashlib.sha256((ROOT / folder / file).read_bytes()).hexdigest() == digest
    quantitative = [i for i in items if i['method'] == '관측 비율']
    return dict(title='HOME 데이터 수집 중간성적표', as_of_date='2026-10-16', timezone='Asia/Seoul',
                generated_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), total_score=total,
                display_score=rounded(total, 1), categories=categories, groups=groups, evidence=evidence,
                quantitative_items=len(quantitative), quantitative_weight=sum(i['weight'] for i in quantitative),
                judgment_items=len(items)-len(quantitative), judgment_weight=100-sum(i['weight'] for i in quantitative),
                source_snapshot_at=summary['generated_at'], categories_count=len(categories), criteria_count=len(items),
                metrics=dict(registered_sources=n_sources, successful_sources=success, automatic_sources=automatic,
                             manual_sources=n_sources-automatic, latest_rows=manifest['latest_rows'], linked_records=summary['current']['linked_records'],
                             project_records=quality['project_count'], policy_project_records=requirements['project_count'],
                             repairs=dict(Counter(r['status'] for r in quality['repairs'])), requirements=requirements['metrics']),
                agreement=dict(total_rows=len(benchmark), numeric_rows=numeric, confirmed_matches=counts['matched'],
                               pending=counts['pending'], excluded=counts['excluded'], comparable=comparable, exact=exact,
                               overall_confirmed_percent=rounded(counts['matched']/numeric*100),
                               comparable_match_percent=rounded(counts['matched']/comparable*100),
                               exact_among_comparable_percent=rounded(exact/comparable*100),
                               managed_site_rows=audit['summary']['managed_site_rows'], raw_site_rows=audit['summary']['raw_site_rows'],
                               rows=benchmark), tests=tests,
                scoring_version='HOME-COLLECTION-MIDTERM-1',
                evaluation_scope='자체 수집·구축과 실시간 발표 근거 생산 준비도. 통계적 정확도·공식 인증·기능 구현률과 구분한다.')


def render(data):
    h = escape
    number = lambda x: f'{x:,.2f}'.rstrip('0').rstrip('.')
    score = number(data['total_score'])
    ev = data['evidence']

    def links(keys):
        return ' · '.join(f'<a href="#evidence-{h(key)}">{h(ev[key]["label"])}</a>' for key in keys)

    categories = ''.join(f'''<a class="category-card" href="#cat-{cat['id']}" style="--pct:{cat['score']/cat['weight']*100:.4f}%">
      <div class="category-top"><span>{cat['id']}　{h(cat['name'])}</span><strong>{number(cat['score'])}<small> / {cat['weight']}</small></strong></div>
      <div class="bar"><i></i></div><p>{h(cat['verdict'])}</p></a>''' for cat in data['categories'])
    groups = ''.join(f'''<div class="group"><div><span>{h(g['name'])}</span><strong>{number(g['score'])}<small> / {g['weight']}점</small></strong></div>
      <div class="bar" style="--pct:{g['percent']:.4f}%"><i></i></div><small>영역 내 환산 {g['percent']:.1f}점</small></div>''' for g in data['groups'])
    detail = []
    for cat in data['categories']:
        rows = []
        for item in cat['items']:
            raw = f'{item["numerator"]:,}/{item["denominator"]:,} · {item["fraction"]*100:.1f}%' if item['method']=='관측 비율' else f'근거 {item["level"]}/4단계'
            tag = 'good' if item['fraction'] >= .75 else 'mid' if item['fraction'] >= .5 else 'low'
            search = h(' '.join([item['id'],item['name'],item['reason'],item['next_step']]), quote=True)
            rows.append(f'''<tr class="criterion" data-score="{item['fraction']}" data-search="{search}">
              <td><span class="row-id">{item['id']}</span><strong>{h(item['name'])}</strong><small>{h(raw)}</small></td>
              <td class="points"><strong class="{tag}">{number(item['score'])}</strong><span> / {item['weight']}점</span><small>{item['method']}</small></td>
              <td><p>{h(item['reason'])}</p><details><summary>근거와 다음 개선</summary><div class="evidence-inline">{links(item['evidence'])}</div><p class="next">{h(item['next_step'])}</p></details></td></tr>''')
        detail.append(f'''<section class="category-detail" id="cat-{cat['id']}" data-category="{cat['id']}">
          <div class="section-title"><div><span class="eyebrow">CATEGORY {cat['id']}</span><h3>{h(cat['name'])}</h3></div><strong>{number(cat['score'])}<small> / {cat['weight']}점</small></strong></div>
          <div class="table-wrap"><table><colgroup><col class="col-item"><col class="col-score"><col></colgroup><thead><tr><th scope="col">평가 항목</th><th scope="col">취득 / 배점</th><th scope="col">현재 상태와 채점 근거</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>''')
    benchmark_rows = []
    status_labels = dict(MATCH_EXACT='하한 기준 일치', MATCH_ROUNDED='표시 정밀도 부합', VERSION_MISSING='목표 판본 미등록',
                         VERSION_DIFFERENCE='목표 판본 차이', PERIOD_GAP='기간·연도 차이', NOT_REGISTERED='동일 범위 자료 미등록',
                         SCOPE_GAP='모집단·범위 차이', QUALITATIVE='정성 항목', PARTIAL_SCOPE='부분 범위', RAW_ONLY='참고 원천만 있음',
                         PLAN_SCOPE_GAP='계획 범위·기간 대기', CANDIDATE_ONLY='연결 후보', CANDIDATE_MATCH='범위 확인 대기', PLAN_CANDIDATE='입주계획 후보')
    for row in data['agreement']['rows']:
        state_label = {'matched':'일치 확인','pending':'비교 대기','excluded':'수치 평가 제외'}[row['state']]
        separator = ' → ' if row['id'] == 'M34' else ' ~ '
        official = '수치 없음' if row['official_value'] is None else number(row['official_value']) + (separator + number(row['official_upper']) if row['official_upper'] is not None else '') + ' ' + h(str(row['unit']))
        if row['id'] in ('M01','M02','M04','M20','M21') and row['official_value'] is not None:
            official = '≥ ' + official
        elif row['status']=='MATCH_ROUNDED' or row['id'] in ('M08','M09','M14','M15','M17','M18','M19','M22','M26','M30','M35','S02','S03','S04','S05','S06','S07','S11'):
            official = '약 ' + official
        if row['id'] == 'M05':
            official += ' · 전망'
        if row['id'] == 'M12':
            official += ' · 기간·빈도 표현 재확인'
        actual = '동일 기준 값 미확보' if row['actual_value'] is None else number(row['actual_value'])
        benchmark_rows.append(f'''<tr class="benchmark-row" data-state="{row['state']}"><td><span class="row-id">{row['id']}</span><strong>{h(row['name'])}</strong><small>{h(row['kind'])}</small></td>
          <td>{official}<small>{h(str(row['official_period'] or ''))}</small></td><td>{actual}<small>{h(str(row['actual_scope'] or ''))}</small></td>
          <td><span class="badge {row['state']}">{state_label}</span><small>{h(status_labels.get(row['status'],row['status']))}</small><details><summary>판정 이유</summary><p>{h(row['explanation'])}</p></details></td></tr>''')
    evidence_rows=[]
    for key, item in ev.items():
        anchor = f'<a href="{h(item["href"],quote=True)}">{h(item["label"])}</a>' if item.get('href') else h(item['label'])
        evidence_rows.append(f'''<li id="evidence-{h(key)}"><div><strong>{anchor}</strong><p>{h(item['scope'])}</p></div><details><summary>판본 정보</summary><code>{h(item['path'])}</code><code>SHA-256 {h(item.get('sha256') or '미기록')}</code></details></li>''')
    payload=json.dumps(data,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    return TEMPLATE.replace('__SCORE__',f'{data["display_score"]:.1f}').replace('__SCORE_EXACT__',score).replace('__GROUPS__',groups).replace('__CATEGORIES__',categories).replace('__DETAILS__',''.join(detail)).replace('__BENCHMARK_ROWS__',''.join(benchmark_rows)).replace('__EVIDENCE__',''.join(evidence_rows)).replace('__DATA__',payload).replace('__QUANT_ITEMS__',str(data['quantitative_items'])).replace('__QUANT_WEIGHT__',str(data['quantitative_weight'])).replace('__JUDGE_ITEMS__',str(data['judgment_items'])).replace('__JUDGE_WEIGHT__',str(data['judgment_weight']))


TEMPLATE = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>HOME 데이터 수집 중간성적표 · 2026.10.16</title>
<style>
:root{--ink:#172e37;--muted:#5c7076;--paper:#f4f5ef;--white:#fff;--line:#dce3de;--teal:#0b7363;--amber:#9a5b13;--rose:#a33d43;--blue:#245786;--sans:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",sans-serif}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:80px}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.75 var(--sans);word-break:keep-all;overflow-wrap:anywhere}a{color:var(--teal);text-underline-offset:3px}button,input,select{font:inherit}button{cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #cc8e31;outline-offset:4px}button,.button{border:1px solid var(--line);background:white;padding:8px 15px;border-radius:7px;color:var(--ink);text-decoration:none}button:hover,.button:hover{border-color:var(--teal)}p,h1,h2,h3{margin-top:0}p{margin-bottom:12px}small{font-size:12px;color:var(--muted)}header{position:sticky;top:0;z-index:10;background:#f4f5eff5;border-bottom:1px solid var(--line);backdrop-filter:blur(10px)}.top{max-width:1240px;margin:auto;min-height:65px;display:flex;align-items:center;justify-content:space-between;padding:12px 28px;gap:20px}.brand{font-weight:800;letter-spacing:.12em;color:var(--ink);text-decoration:none}.brand span{font-size:11px;color:var(--muted);font-weight:500;letter-spacing:.04em;margin-left:15px}.nav{display:flex;align-items:center;gap:20px}.nav>a:not(.button){font-size:13px;text-decoration:none;color:var(--muted)}main{max-width:1240px;margin:auto;padding:42px 28px 80px}.eyebrow{font-size:11px;font-weight:750;letter-spacing:.12em;color:var(--teal);text-transform:uppercase}.hero{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(300px,1fr);gap:35px;align-items:center;margin-bottom:28px}.hero h1{font-size:clamp(31px,3.8vw,49px);line-height:1.3;letter-spacing:-.055em;margin:16px 0 22px}.lead{font-size:17px;max-width:690px;line-height:1.9;color:#40585f}.meta{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0}.pill{display:inline-block;font-size:12px;background:#e8ede6;padding:4px 10px;border-radius:4px}.score-card{position:relative;background:var(--ink);color:#fff;border-radius:14px;padding:29px 32px;overflow:hidden}.score-card:after{content:"";position:absolute;width:210px;height:210px;border:35px solid #ffffff05;border-radius:50%;right:-100px;top:-80px;pointer-events:none}.score-card .eyebrow{color:#93d1b9}.score-number{font-size:84px;line-height:1.15;font-weight:760;letter-spacing:-.065em;margin:20px 0 10px}.score-number small{font-size:21px;color:#abc2c7;letter-spacing:0}.score-card h2{font-size:16px;font-weight:650;margin:0 0 18px}.score-card p{font-size:12px;color:#bfd1d4;margin:12px 0 0}.score-track{height:5px;background:#ffffff20;border-radius:9px;overflow:hidden}.score-track span{display:block;background:#9fd8b4;width:__SCORE__%;height:100%}.statement{padding:23px 26px;border-left:4px solid var(--teal);background:#e8efe8;border-radius:0 8px 8px 0;margin-bottom:22px}.statement strong{font-size:17px}.statement p{margin:8px 0 0;color:#42605a}.groups{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:18px}.group{background:white;border:1px solid var(--line);border-radius:9px;padding:18px 21px}.group>div:first-child{display:flex;align-items:center;justify-content:space-between;gap:12px}.group>div>span{font-size:13px}.group strong{font-size:23px}.group small{font-weight:400}.bar{height:6px;background:#e9eeeb;border-radius:10px;overflow:hidden;margin:13px 0 6px}.bar i{display:block;height:100%;width:var(--pct);background:var(--teal);border-radius:10px}.scope-note{font-size:12px;color:var(--muted)}.section{margin-top:54px}h2{font-size:26px;letter-spacing:-.045em;line-height:1.4;margin-bottom:11px}.section-intro{color:var(--muted);max-width:940px}.section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:20px}.section-head h2{margin-top:8px}.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin:22px 0}.kpi{border:1px solid var(--line);background:white;border-radius:9px;padding:19px 21px}.kpi .label{display:block;font-size:12px;color:var(--muted);font-weight:650}.kpi strong{display:block;font-size:35px;letter-spacing:-.05em;line-height:1.5;margin-top:5px}.kpi p{font-size:12px;color:var(--muted);line-height:1.7;margin:7px 0 0}.kpi.highlight{border-color:#b1c9bc;background:#eef5ed}.kpi.highlight strong{color:var(--teal)}.formula{background:#fff;border:1px solid var(--line);border-radius:9px;padding:22px 25px}.formula>p:last-child{margin-bottom:0}.stack{height:13px;display:flex;overflow:hidden;border-radius:20px;margin:15px 0 10px;background:#edf0ec}.stack span:nth-child(1){background:var(--teal);width:5.660377%}.stack span:nth-child(2){background:#c5ccbf;width:83.018868%}.stack span:nth-child(3){background:#e4d5b5;width:11.320755%}.legend{display:flex;flex-wrap:wrap;gap:8px 25px;font-size:12px;color:var(--muted)}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:var(--teal)}.dot.pending{background:#c5ccbf}.dot.excluded{background:#cbb480}.callout{padding:16px 20px;background:#fff3de;border:1px solid #ecdbb8;border-radius:8px;margin:17px 0;color:#72521d;font-size:13px}.category-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.category-card{text-decoration:none;color:var(--ink);background:white;border:1px solid var(--line);padding:18px 21px;border-radius:8px;transition:border-color .15s}.category-card:hover{border-color:var(--teal)}.category-top{display:flex;align-items:center;justify-content:space-between;gap:12px}.category-top>span{font-size:14px;font-weight:650}.category-top strong{font-size:22px;white-space:nowrap}.category-card p{font-size:12px;color:var(--muted);margin:8px 0 0}.method{border:1px solid var(--line);border-radius:9px;background:white;padding:21px 24px;margin:22px 0}.method-grid{display:grid;grid-template-columns:1fr 1fr;gap:25px}.method h3{font-size:16px;margin-bottom:9px}.method p,.method li{font-size:13px;color:var(--muted)}.method ol{margin:0;padding-left:22px}.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:15px 18px;border:1px solid var(--line);background:#eaf0e9;border-radius:8px;margin:22px 0}.toolbar label{display:flex;align-items:center;gap:7px;font-size:13px}.toolbar input[type=search],select{padding:8px 10px;border:1px solid #cbd7cf;border-radius:5px;background:white;min-width:160px;color:var(--ink)}.toolbar input[type=search]{flex:1;min-width:190px}.toolbar .count{font-size:12px;color:var(--muted);margin-left:auto}.category-detail{background:white;border:1px solid var(--line);border-radius:9px;margin-top:18px;overflow:hidden;scroll-margin-top:86px}.section-title{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:20px 22px;border-bottom:1px solid var(--line);background:#fafbf8}.section-title h3{font-size:18px;margin:5px 0 0}.section-title>strong{font-size:28px;white-space:nowrap}.section-title strong small{font-size:13px;font-weight:400}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th{font-weight:600;font-size:11px;color:var(--muted);padding:12px 18px;border-bottom:1px solid var(--line);background:#fbfcfa}td{padding:18px;vertical-align:top;border-bottom:1px solid #edf0eb}tbody tr:last-child td{border-bottom:0}td strong{display:block;font-size:13px;line-height:1.65}td small{display:block;line-height:1.65;margin-top:5px}td p{margin:0}.col-item{width:27%}.col-score{width:14%}.row-id{display:block;font-size:10px;letter-spacing:.07em;color:var(--muted);margin-bottom:5px}.points{white-space:nowrap}.points strong{font-size:23px;display:inline;letter-spacing:-.035em}.points>span{font-size:12px;color:var(--muted)}.good{color:var(--teal)}.mid{color:var(--amber)}.low{color:var(--rose)}details{margin-top:9px}summary{font-size:12px;color:var(--teal);cursor:pointer;width:fit-content}details[open] summary{margin-bottom:9px}.evidence-inline{font-size:11px;line-height:1.9}.next{margin-top:9px;color:#76541c;font-size:12px}.empty{padding:25px;background:white;text-align:center;color:var(--muted)}[hidden]{display:none!important}.benchmark-table{min-width:800px}.benchmark-table td:first-child{width:23%}.benchmark-table td:nth-child(2){width:23%}.benchmark-table td:nth-child(3){width:20%}.badge{display:inline-block;font-size:11px;padding:3px 9px;border-radius:4px;white-space:nowrap}.badge.matched{color:var(--teal);background:#e5f0e6}.badge.pending{color:#8a581f;background:#f6eedc}.badge.excluded{color:#596b75;background:#eaf0f1}.benchmark-help{font-size:12px;color:var(--muted);margin-top:14px}.priorities{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px}.priority{padding:23px;background:#fff;border:1px solid var(--line);border-radius:9px}.priority>span{font-size:11px;font-weight:700;letter-spacing:.09em;color:var(--teal)}.priority h3{font-size:18px;line-height:1.5;margin:10px 0}.priority p{font-size:13px;color:var(--muted);margin:0}.basis{padding:20px 24px;background:white;border:1px solid var(--line);border-radius:9px}.basis ul{list-style:none;margin:0;padding:0}.basis li{padding:17px 0;border-bottom:1px solid var(--line);scroll-margin-top:88px}.basis li:last-child{border:0}.basis p{font-size:12px;color:var(--muted);margin:5px 0 0}.basis strong{font-size:13px}.basis code{display:block;font-size:11px;white-space:normal;overflow-wrap:anywhere;color:var(--muted);margin:5px 0}footer{margin-top:40px;padding-top:22px;border-top:1px solid var(--line);font-size:12px;color:var(--muted);display:flex;justify-content:space-between;gap:20px}.skip{position:absolute;left:12px;top:-80px;background:white;padding:8px;z-index:30}.skip:focus{top:8px}noscript p{background:#fff3de;padding:18px}#back-top{font-size:12px}
@media(max-width:900px){.hero{grid-template-columns:1fr;gap:18px}.score-card{padding:24px}.score-number{font-size:72px;margin:14px 0}.hero h1{font-size:38px}.groups{gap:9px}.group{padding:15px}.group>div:first-child{display:block}.group strong{display:block;margin-top:6px}.nav>a:not(.button){display:none}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.priorities{grid-template-columns:1fr}.method-grid{grid-template-columns:1fr;gap:15px}.col-item{width:30%}.col-score{width:17%}}
@media(max-width:600px){body{font-size:14px}.top{padding:10px 17px;gap:8px}.brand span{display:none}.nav{gap:8px}.nav button,.button{padding:7px 10px;font-size:12px}main{padding:28px 17px 50px}.hero h1{font-size:33px}.lead{font-size:15px}.hero{margin-bottom:20px}.statement{padding:18px}.statement strong{font-size:16px}.groups,.category-grid{grid-template-columns:1fr}.group>div:first-child{display:flex}.group strong{margin:0}.section{margin-top:37px}h2{font-size:23px}.kpis{gap:9px}.kpi{padding:16px}.kpi strong{font-size:30px}.section-head{display:block}.category-top>span{font-size:13px}.method,.formula,.basis{padding:17px}.toolbar{padding:12px}.toolbar label{font-size:12px}.toolbar input[type=search]{width:100%;flex-basis:100%}.toolbar .count{margin-left:0}.section-title{padding:16px}.section-title h3{font-size:16px}.section-title>strong{font-size:23px}.category-detail table,.category-detail thead,.category-detail tbody,.category-detail tr,.category-detail td{display:block}.category-detail colgroup,.category-detail thead{display:none}.category-detail tr{position:relative;padding:16px;border-bottom:1px solid var(--line)}.category-detail td{border:0;padding:0}.category-detail td:first-child{padding-right:94px;min-height:63px}.category-detail .points{position:absolute;right:16px;top:22px}.category-detail td:last-child{margin-top:12px}.points strong{font-size:22px}.benchmark-table{min-width:760px}footer{display:block}.basis code{font-size:10px}}
@media(max-width:600px){table.benchmark-table{display:table}.benchmark-table thead{display:table-header-group}.benchmark-table tbody{display:table-row-group}.benchmark-table tr{display:table-row;position:static;padding:0}.benchmark-table td{display:table-cell;padding:14px;border-bottom:1px solid var(--line)}.benchmark-table td:first-child{padding-right:14px;min-height:0}.benchmark-table td:last-child{margin-top:0}}
@media print{@page{size:A4;margin:13mm}body{font-size:10pt;background:white;color:#14252c;print-color-adjust:exact;-webkit-print-color-adjust:exact}header,.toolbar,footer button,.no-print{display:none!important}main{padding:0;max-width:none}.hero{grid-template-columns:1.4fr 1fr;gap:20px}.hero h1{font-size:27pt}.lead{font-size:10pt}.score-card{padding:20px}.score-number{font-size:50pt}.score-card h2{font-size:11pt}.section{margin-top:22px}.section h2{font-size:18pt}.kpis{gap:8px}.kpi{padding:12px}.kpi strong{font-size:23pt}.category-grid{gap:8px}.category-card{padding:12px}.category-detail,.priority,.method,.kpi,.group,.formula,.statement{break-inside:avoid}.category-detail{break-inside:auto}.category-detail tr{break-inside:avoid}td{padding:10px;font-size:9pt}.section-title{padding:12px}.table-wrap{overflow:visible}.benchmark-table{min-width:0;font-size:9pt}.benchmark-table td{padding:8px}.basis li{break-inside:avoid}.category-card p,.scope-note,small{font-size:8pt}a{color:inherit}.hero,.groups,.kpis,.category-grid{break-inside:avoid}.basis details{display:block}footer{display:block;font-size:8pt}details[open] summary{display:none}}
</style></head><body>
<a class="skip" href="#main">본문으로 이동</a><header><div class="top"><a class="brand" href="#">HOME<span>DATA COLLECTION REVIEW</span></a><nav class="nav" aria-label="보고서 탐색"><a href="#agreement">전체 일치도</a><a href="#scores">세부 점수</a><a href="#next">우선 개선</a><button id="download-data" type="button">평가 JSON 저장</button><button id="print-report" type="button">인쇄 / PDF</button></nav></div></header>
<main id="main"><noscript><p>모든 점수와 근거는 JavaScript 없이도 읽을 수 있습니다. 검색·필터·JSON 저장은 JavaScript를 켜면 사용할 수 있습니다.</p></noscript>
<section class="hero"><div><span class="eyebrow">PoC 10 · MIDTERM REPORT · 2026.10.16</span><h1>데이터 수집<br>중간성적표</h1><p class="lead">제로베이스에서 구축한 HOME의 현재 성과를 평가합니다. 목표는 <strong>현장의 변화를 먼저 추적하고, 검증한 자체 데이터로 공식 발표의 근거를 만드는 것</strong>입니다.</p><div class="meta"><span class="pill">10개 영역 · 40개 세부 항목</span><span class="pill">종합 100점</span><span class="pill">공식 발표는 중간 검증 자료</span></div></div>
<div class="score-card"><span class="eyebrow">수집·구축 종합점수</span><div class="score-number">__SCORE__<small> / 100</small></div><h2>기반 구축 후 실적·갱신 보강 단계</h2><div class="score-track"><span></span></div><p>수집·구축과 목표 플랫폼까지의 준비도 점수입니다.<br>데이터 정확도나 공식 발표와의 일치율이 아닙니다.</p></div></section>
<div class="statement"><strong>원문·판본·연결 기반은 쌓였다. 다음 과제는 실적 근거의 완결성과 연속 갱신이다.</strong><p>62개 원천에 저장 자료가 있고, 최신 원천은 1,674,418행이다. 등록된 9·7 사업의 비추정 실적·진척 근거는 312/985단계 셀에 있으며, 원천 포착부터 집계까지의 지연은 아직 실측되지 않았다.</p></div>
<div class="groups">__GROUPS__</div><p class="scope-note">세 영역의 취득점수 합계는 __SCORE_EXACT__점이다. 영역별 환산점수는 비중을 이해하기 위한 값이며 전체 점수와 다시 합산하지 않는다.</p>

<section class="section" id="agreement"><span class="eyebrow">01 · AGREEMENT</span><h2>전체 일치도는 따로 본다</h2><p class="section-intro">2026년 10월 16일 공식 발표의 53행을 중간 검증에 사용했다. 수치가 있는 47행 중 같은 기준으로 비교한 3행에서 일치가 확인됐다. 나머지 44행은 기간·범위·판본·연결·자료 확보 조건을 더 확인해야 한다.</p>
<div class="kpis"><article class="kpi highlight"><span class="label">전체 수치 항목 중 확인된 일치</span><strong>6.38%</strong><p><b>3 / 47행</b> · 전체 확인 일치율<br>남은 44행을 불일치로 판정한 값이 아니다.</p></article><article class="kpi"><span class="label">비교 가능 항목의 일치도</span><strong>100%</strong><p><b>3 / 3행</b> · 하한·표시 정밀도 기준<br>전체 데이터 정확도 100%를 뜻하지 않는다.</p></article><article class="kpi"><span class="label">관리 사업명의 대응</span><strong>75%</strong><p><b>12 / 16개 발표행</b><br>같은 사건·호수까지 검증한 비율은 아니다.</p></article><article class="kpi"><span class="label">관련 원천명의 탐색</span><strong>100%</strong><p><b>16 / 16개 발표행</b><br>원천 존재와 관리사업 연결은 구분한다.</p></article></div>
<div class="formula"><strong>전체 확인 일치율 = 일치 확인 3행 ÷ 수치 평가 대상 47행 × 100 = 6.38%</strong><p class="scope-note">전체 53행 중 정성 지표 3행과 물량 없는 입주계획 3행은 수치 분모에서 제외했다. 호 단위 완전 일치는 비교 가능 3행 중 1행(33.33%)이다. 이번 표본만으로 전체 수치 정확도를 확정할 수 없다.</p><div class="stack" role="img" aria-label="전체 53행 중 일치 확인 3행, 비교 대기 44행, 수치 평가 제외 6행"><span></span><span></span><span></span></div><div class="legend"><span><i class="dot"></i>일치 확인 3행</span><span><i class="dot pending"></i>비교 대기 44행</span><span><i class="dot excluded"></i>수치 평가 제외 6행</span></div></div>
<div class="callout"><strong>이번 검증의 의미</strong>　135만 원목표는 발표 하한 기준이 일치했고, 서울 20,679/약 21,000호·창릉 2,306/약 2,300호는 분석자가 적용한 반올림 단위에서 부합했다. 창릉은 지구 집계 대조이며 공식 블록 ID 전체를 확정한 결과는 아니다. 앞으로의 목표는 HOME이 자체 사건 원장에서 같은 범위의 수치를 먼저 산출하는 것이다.</div></section>

<section class="section" id="scores"><div class="section-head"><div><span class="eyebrow">02 · SCORECARD</span><h2>10개 영역의 현재 점수</h2></div><a class="button no-print" href="#detailed">40개 항목 상세 보기 ↓</a></div><div class="category-grid">__CATEGORIES__</div>
<div class="method"><div class="method-grid"><div><h3>채점 방법</h3><p><b>관측 비율 __QUANT_ITEMS__개 · __QUANT_WEIGHT__점 배점</b><br>해당 항목의 배점 × 실제 분자/분모로 산출했다. 자료 존재율과 정확도를 구분하고 추정 제외 자료를 사용했다.</p><p><b>근거 등급 __JUDGE_ITEMS__개 · __JUDGE_WEIGHT__점 배점</b><br>배점 × 근거 등급/4로 산출했다. 외부 표준 인증 점수가 아닌 이번 개선 계획에 따른 평가자 판단이다. 각 항목에 이유와 다음 조치를 붙였다.</p><p>합계는 반올림 전 점수로 계산한다. 개별 항목은 소수 둘째 자리로 표시하며, 표시값의 합과 최대 수백분의 일 점 차이가 날 수 있다.</p></div><div><h3>근거 등급 0~4</h3><ol start="0"><li>확인된 구축·운영 근거 없음</li><li>설계·기초 자료·입력 기반 존재</li><li>일부 범위 구현·자료·연계 확인</li><li>운영 경로와 대표 사례·검증 근거 확보, 확대 검수 잔여</li><li>해당 세부 조건을 코드·고정 근거·재검증으로 확인</li></ol><p style="margin-top:12px">미확인 항목의 낮은 점수는 <b>자료 오류율</b>을 뜻하지 않는다. 담당자 확정값은 관리기준으로 인정하며, 승인된 추정도 추정이라는 성격을 유지한다.</p></div></div></div>
<p class="scope-note">평가 대상은 수집 결과·사업 연결·실적 근거·갱신·발표용 재현이다. 기존 화면 기능 충족률 95.9%와 다른 지표다. 같은 근거가 여러 조건을 설명할 수 있지만 관측 건수나 분모를 더해 확보량으로 해석하지 않는다.</p></section>

<section class="section" id="detailed"><span class="eyebrow">03 · DETAILED ASSESSMENT</span><h2>세부 항목별 배점과 감점 이유</h2><div class="toolbar no-print"><label for="category-filter">영역</label><select id="category-filter"><option value="all">전체 영역</option><option value="A">A 원천 확보</option><option value="B">B 모집단·범위</option><option value="C">C 사업 식별</option><option value="D">D 실적·일정</option><option value="E">E 집계 정합성</option><option value="F">F 판본·감사</option><option value="G">G 실시간 추적</option><option value="H">H 품질·복구</option><option value="I">I 기관·실제성과</option><option value="J">J 발표 준비</option></select><input id="criterion-search" type="search" placeholder="항목·근거·개선 내용 검색" aria-label="평가 항목 검색"><label><input type="checkbox" id="weak-only"> 취득률 50% 미만</label><button id="toggle-evidence" type="button">근거 모두 펼치기</button><span class="count" id="criterion-count" role="status" aria-live="polite">40개 항목</span></div><div id="criterion-list">__DETAILS__</div><p class="empty" id="criterion-empty" hidden>조건에 맞는 평가 항목이 없습니다.</p></section>

<section class="section" id="benchmark"><span class="eyebrow">04 · BENCHMARK LEDGER</span><h2>공식 발표 53행의 대조 상태</h2><p class="section-intro">수집·구축 점수와 분리한 외부 검증표다. 아래 HOME 값에는 기간·범위가 다른 참고값도 있다. 숫자가 보이더라도 ‘일치 확인’ 표시가 없으면 같은 조건의 비교를 통과한 값이 아니다.</p><div class="toolbar no-print"><label for="benchmark-filter">대조 상태</label><select id="benchmark-filter"><option value="all">전체 53행</option><option value="matched">일치 확인 3행</option><option value="pending">비교 대기 44행</option><option value="excluded">수치 평가 제외 6행</option></select><span class="count" id="benchmark-count" role="status" aria-live="polite">53개 행</span></div><div class="category-detail"><div class="table-wrap"><table class="benchmark-table"><thead><tr><th scope="col">항목</th><th scope="col">공식 발표의 대표값·기간</th><th scope="col">HOME 값·적용 범위</th><th scope="col">중간 판정</th></tr></thead><tbody>__BENCHMARK_ROWS__</tbody></table></div></div><p class="benchmark-help">발표 수치의 정확·약·이상·범위 표기는 원문과 대조 보고서의 한정을 함께 읽는다. M34의 132.5→130.8은 월별 지수 변화이며 구간 상하한이 아니다. 대표값·계산값·정성 항목은 원래 의미로 보존한다.</p></section>

<section class="section" id="next"><span class="eyebrow">05 · NEXT MILESTONES</span><h2>다음 성적을 올릴 세 가지 작업</h2><div class="priorities"><article class="priority"><span>01 · 실적 근거 완결</span><h3>원천이 실제 사건으로<br>이어지게 한다</h3><p>미연결 정비·허가 원천을 사업 후보로 만들고, 사건별 물량·일자·범위를 검증한다. 목표·실적 동시 확보 셀 241/985와 비추정 실적·진척 근거 312/985의 공백을 줄인다.</p></article><article class="priority"><span>02 · 연속 추적</span><h3>최신 변경을 따로 포착하고<br>반영 지연을 측정한다</h3><p>완료 지역 재방문, 원천별 작업 잠금과 증분 큐, 실패 구간 재처리를 도입한다. 포착→검증→조회 반영 P95를 측정해 실시간성을 확인한다.</p></article><article class="priority"><span>03 · 발표 근거 생산</span><h3>같은 원장에서<br>검증 가능한 숫자를 만든다</h3><p>대상 명부와 기관별 확정 책임을 정하고 계약·실입주 집계를 연계한다. 발표 기준시각과 구성 사건을 고정해 수치와 정정 사유를 재현한다.</p></article></div><p class="scope-note" style="margin-top:15px">다음 점검에서도 같은 100점 배점을 유지한다. 단순 수집 행 수나 외부 발표값 복사로 가점을 주지 않고, 실제 근거 확보·연결·갱신·검수 결과로 재채점한다.</p></section>

<section class="section" id="basis"><span class="eyebrow">06 · EVIDENCE</span><h2>평가 기준시각과 근거</h2><div class="method"><p><b>수집·구축 정량:</b> 2026-10-16 20:54~20:55 KST 동결 자료. 원천 63개·최신 1,674,418행·연결 원천 884건·사업 기록 311개. 정책별 확보율의 분모는 9·7 등록 사업 197개·985단계 셀이다.</p><p><b>발표 일치도:</b> 별도 공식 발표 대조 JSON과 그 동결 근거를 사용했다. API 수집과 DB 읽기 시각은 서로 다르며 하나의 동시 DB 스냅샷으로 간주하지 않는다.</p><p><b>코드 검토와 이번 검증:</b> 현재 작업 트리에서 관련 코드와 9개 테스트 파일을 확인했다. 71개 테스트·하위검사 2개가 통과했다. 기관 API 실호출·운영 DB 전수 재감사는 수행한 것으로 표기하지 않는다.</p><p><b>점수 해석:</b> 51점대는 평가자가 정한 100점 배점의 현재 준비도다. 수집된 개별 승인값이 절반만 정확하다는 뜻이 아니다. 모집단·실적·실시간성 등 목표에 필요한 증거 공백이 감점에 반영됐다.</p><p style="margin-bottom:0"><a href="HOME_TRUSTED_REALTIME_PLATFORM_PLAN_20261016.md">개선 계획</a> · <a href="HOME_DATA_COLLECTION_MIDTERM_20261016.json">평가 원본 JSON</a> · <a href="../scripts/build_collection_midterm.py">재생성 스크립트</a></p></div><div class="basis"><ul>__EVIDENCE__</ul></div></section>
<footer><div>HOME · Housing Operations Monitoring &amp; Execution<br>평가 버전 HOME-COLLECTION-MIDTERM-1 · 외부 의존성 없는 단일 HTML</div><a id="back-top" href="#">맨 위로 ↑</a></footer></main>
<script id="report-data" type="application/json">__DATA__</script><script>
'use strict';
const report=JSON.parse(document.getElementById('report-data').textContent);
const categoryFilter=document.getElementById('category-filter'),search=document.getElementById('criterion-search'),weak=document.getElementById('weak-only');
function filterCriteria(){let count=0;const term=search.value.trim().toLocaleLowerCase('ko');document.querySelectorAll('.category-detail[data-category]').forEach(section=>{let visible=0;section.querySelectorAll('.criterion').forEach(row=>{const show=(categoryFilter.value==='all'||categoryFilter.value===section.dataset.category)&&(!weak.checked||Number(row.dataset.score)<.5)&&(!term||row.dataset.search.toLocaleLowerCase('ko').includes(term));row.hidden=!show;if(show){visible++;count++;}});section.hidden=!visible;});document.getElementById('criterion-count').textContent=count+' / 40개 항목';document.getElementById('criterion-empty').hidden=count!==0;}
[categoryFilter,weak].forEach(x=>x.addEventListener('change',filterCriteria));search.addEventListener('input',filterCriteria);
document.querySelectorAll('.category-card').forEach(a=>a.addEventListener('click',()=>{categoryFilter.value='all';search.value='';weak.checked=false;filterCriteria();}));
document.getElementById('toggle-evidence').addEventListener('click',event=>{const details=[...document.querySelectorAll('#criterion-list details')];const open=details.some(x=>!x.open);details.forEach(x=>x.open=open);event.currentTarget.textContent=open?'근거 모두 접기':'근거 모두 펼치기';});
document.getElementById('benchmark-filter').addEventListener('change',event=>{let n=0;document.querySelectorAll('.benchmark-row').forEach(row=>{row.hidden=event.target.value!=='all'&&row.dataset.state!==event.target.value;if(!row.hidden)n++;});document.getElementById('benchmark-count').textContent=n+' / 53개 행';});
document.getElementById('download-data').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='HOME_DATA_COLLECTION_MIDTERM_20261016.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
let printState=null;window.addEventListener('beforeprint',()=>{if(printState)return;const nodes=[...document.querySelectorAll('.category-detail[data-category],.criterion,.benchmark-row')];const details=[...document.querySelectorAll('#criterion-list details')];printState={nodes:nodes.map(n=>[n,n.hidden]),details:details.map(n=>[n,n.open])};nodes.forEach(n=>n.hidden=false);details.forEach(n=>n.open=true);});window.addEventListener('afterprint',()=>{if(!printState)return;printState.nodes.forEach(([n,value])=>n.hidden=value);printState.details.forEach(([n,value])=>n.open=value);printState=null;});document.getElementById('print-report').addEventListener('click',()=>window.print());
</script></body></html>'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-report', type=Path, required=True)
    args = parser.parse_args()
    data = build_data(args.test_report)
    DOCS.mkdir(exist_ok=True)
    (DOCS / f'{STEM}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    (DOCS / f'{STEM}.html').write_text(render(data))
    print(json.dumps(dict(score=data['display_score'], criteria=data['criteria_count'],
                         quantitative_items=data['quantitative_items'], agreement=data['agreement']['overall_confirmed_percent'],
                         output=str(DOCS / f'{STEM}.html')), ensure_ascii=False))
