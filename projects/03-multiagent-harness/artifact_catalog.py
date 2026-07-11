"""결정적 데모에서 열람할 수 있는 산출물 문서 카탈로그."""

from __future__ import annotations

from typing import Any


def _document(
    artifact_id: str,
    title: str,
    agent_id: str,
    summary: str,
    content: str,
    *,
    sources: tuple[str, ...] = (),
    depends_on: tuple[str, ...] = (),
    revisions: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    return {
        "id": artifact_id,
        "title": title,
        "agent_id": agent_id,
        "summary": summary,
        "content": content.strip(),
        "format": "markdown",
        "sources": list(sources),
        "depends_on": list(depends_on),
        "revisions": list(revisions),
    }


def build_artifact_catalog(prompt: str) -> list[dict[str, Any]]:
    """데모 이벤트에서 생성되는 산출물의 열람 가능한 본문을 반환한다."""

    request = " ".join(str(prompt or "").split())
    return [
        _document(
            "00_issue_intake.md",
            "현안 접수서",
            "mission-manager",
            "요청의 목적, 제약조건, 필요한 산출물을 구조화했습니다.",
            f"""
# 현안 접수서

## 접수 요청
{request}

## 대응 목표
- 확인된 사실과 미확인 정보를 구분한다.
- 언론 문의와 국회 질의에 재사용할 수 있는 보고자료를 만든다.
- 모든 판단과 수정 이력을 하네스 이벤트로 남긴다.

## 완료 기준
- 근거, 분석, 초안, 독립검증 Quality Gate 통과
- 최종 대응 패키지 Filing Cabinet 보관
""",
        ),
        _document(
            "01_fact_timeline.md",
            "사실관계·타임라인",
            "collector-1",
            "가상 장애의 확인 시각과 조치 흐름을 사실 중심으로 정리했습니다.",
            """
# 사실관계·타임라인

| 시각 | 확인 내용 | 상태 |
|---|---|---|
| 09:00 | 예약 서비스 접속 지연 민원 최초 접수 | 확인 |
| 09:12 | 운영 모니터링에서 오류율 상승 확인 | 확인 |
| 10:05 | 우회 조치 적용 및 오류율 감소 | 확인 |
| 11:00 | 정상 범위 복귀 관찰 | 확인 |

> 정확한 장애 원인은 기술 분석 완료 전까지 미확인으로 관리한다.
""",
            sources=("가상 운영 모니터링 로그", "가상 고객센터 민원 요약"),
        ),
        _document(
            "04_public_sentiment.md",
            "민원·언론 쟁점",
            "collector-2",
            "이용자 불편과 대외 문의에서 반복되는 쟁점을 분류했습니다.",
            """
# 민원·언론 쟁점

## 주요 질문
- 장애 영향 범위와 실제 이용 불가 시간은 얼마인가?
- 사전 탐지와 이용자 안내가 늦어진 이유는 무엇인가?
- 재발 방지 조치와 후속 안내 일정은 언제인가?

## 커뮤니케이션 원칙
- 확인되지 않은 원인을 단정하지 않는다.
- 피해 규모는 집계 기준과 기준 시각을 함께 제시한다.
- 복구와 원인 조사를 구분해 설명한다.
""",
            sources=("가상 민원 키워드 집계", "가상 언론 질의 목록"),
        ),
        _document(
            "evidence_summary.md",
            "공용 근거 요약",
            "summarizer-1",
            "수집된 사실과 대외 쟁점을 모든 전문 에이전트가 재사용하도록 통합했습니다.",
            """
# 공용 근거 요약

## 확인된 사실
- 09:00~11:00 사이 예약 서비스 접속 장애 민원이 발생했다.
- 09:12 오류율 상승이 확인됐고 10:05 우회 조치가 적용됐다.
- 11:00 정상 범위 복귀가 관찰됐다.

## 미확인·추가 조사
- 최초 장애를 유발한 직접 원인
- 전체 이용자 대비 실제 실패 요청 비율

## 공통 표현
`현재 원인을 조사 중이며 확인되는 내용은 기준 시각과 함께 갱신한다.`
""",
            sources=("01_fact_timeline.md", "04_public_sentiment.md"),
            depends_on=("01_fact_timeline.md", "04_public_sentiment.md"),
        ),
        _document(
            "02_technical_analysis.md",
            "기술 분석",
            "technical-analyst",
            "관찰 사실에서 가능한 원인과 재발방지 조치를 분리해 분석했습니다.",
            """
# 기술 분석

## 관찰
- 동시간대 오류율과 응답 지연이 함께 증가했다.
- 우회 조치 이후 오류율이 감소했다.

## 분석 가설
1. 특정 진입 구간의 처리 용량 부족
2. 의존 서비스 지연의 연쇄 전파

## 권고 조치
- 구간별 포화 지표와 경보 임계치 보강
- 장애 격리와 우회 절차 자동화
- 원인 확정 전까지 가설을 사실처럼 사용하지 않음
""",
            sources=("evidence_summary.md", "가상 시스템 지표"),
            depends_on=("evidence_summary.md",),
        ),
        _document(
            "03_legal_policy_review.md",
            "법령·제도 검토",
            "legal-reviewer",
            "대외 설명 시 확인할 제도적 의무와 표현상 주의사항을 정리했습니다.",
            """
# 법령·제도 검토

## 검토 항목
- 서비스 중단 및 복구 사실의 적시 안내 여부
- 개인정보 침해 징후와 단순 접속 장애의 구분
- 피해 수치와 원인 표현의 근거 보유 여부

## 유의사항
- 본 문서는 법률 자문이 아닌 내부 검토 초안이다.
- 실제 통지 의무는 사실관계와 적용 법령을 담당 부서가 최종 확인한다.
""",
            sources=("evidence_summary.md", "가상 내부 장애대응 지침"),
            depends_on=("evidence_summary.md",),
        ),
        _document(
            "07_executive_brief.md",
            "실장급 보고자료",
            "briefing-writer",
            "현황, 영향, 조치, 의사결정 요청을 한 장의 보고 구조로 통합했습니다.",
            """
# 공공서비스 예약시스템 장애 현안 보고

## 한 줄 현황
09:00~11:00 접속 장애 민원이 발생했으며 서비스는 정상 범위로 복귀했고 원인은 조사 중이다.

## 현재 조치
- 우회 조치 적용 및 서비스 지표 관찰
- 영향 범위와 실패 요청 비율 추가 집계
- 언론·국회 질의용 공통 답변 정리

## 의사결정 요청
1. 추가 기술 점검 시간 승인
2. 이용자 후속 안내 기준 시각 확정
3. 재발방지 대책 보고 일정 지정
""",
            sources=("02_technical_analysis.md", "03_legal_policy_review.md"),
            depends_on=("02_technical_analysis.md", "03_legal_policy_review.md"),
            revisions=(
                {"version": 1, "label": "초안", "note": "원인 단정 표현 1건이 독립검증에서 반송됨"},
                {"version": 2, "label": "수정본", "note": "원인을 조사 중으로 수정하고 검수 통과"},
            ),
        ),
        _document(
            "09_risk_check.md",
            "리스크 검토 결과",
            "risk-checker",
            "사실·법령·표현 체크리스트와 재검수 결과를 기록했습니다.",
            """
# 리스크 검토 결과

| 검수 항목 | 결과 |
|---|---|
| 수치·시각·출처 일치 | 통과 |
| 법령 인용과 면책 문구 | 통과 |
| 미확정 원인 단정 제거 | 수정 후 통과 |
| 필수 수정 이력 추적 | 통과 |

**최종 판정: APPROVED**
""",
            sources=("07_executive_brief.md v2",),
            depends_on=("07_executive_brief.md",),
        ),
        _document(
            "10_final_package.md",
            "현안 대응 패키지",
            "final-synthesizer",
            "검증을 통과한 보고자료와 근거·분석·검수 결과를 하나의 제출 패키지로 묶었습니다.",
            """
# 현안 대응 패키지

## 패키지 구성
1. 사실관계·타임라인
2. 민원·언론 쟁점
3. 공용 근거 요약
4. 기술 분석 및 법령·제도 검토
5. 실장급 보고자료 v2
6. 리스크 검토 결과

## 최종 상태
- Quality Gate 1~4 통과
- 필수 수정 1건 반영 및 재검수 완료
- Filing Cabinet 보관 완료
""",
            sources=("01_fact_timeline.md", "04_public_sentiment.md", "09_risk_check.md"),
            depends_on=("07_executive_brief.md", "09_risk_check.md"),
        ),
    ]


__all__ = ["build_artifact_catalog"]
