from __future__ import annotations

from typing import Any


def _insight(
    topic_id: str,
    topic: str,
    role: str,
    ministries: list[str],
    *,
    task: str | None = None,
) -> dict[str, Any]:
    return {
        "topic_id": topic_id,
        "topic_key": topic_id,
        "topic": topic,
        "role": role,
        "ministries": ministries,
        "task": task,
        "task_id": f"{topic_id}-task" if task else None,
        "task_status": "OPEN" if task else None,
        "resolution": False,
        "derived": True,
    }


def build_watch_test_script(keyword: str) -> list[dict[str, Any]]:
    topic = keyword.strip() or "인공지능 민주정부"
    return [
        {"speaker": "위원", "text": "오늘은 디지털 행정 혁신과 국민 편익 개선 방안을 질의하겠습니다.", "insight": _insight("ai-democracy", f"{topic} 추진과 국민 편익", "QUESTION", ["행정안전부"])},
        {"speaker": "위원", "text": f"특히 {topic} 정책이 실제 현장 서비스에 어떤 변화를 만드는지 설명해 주십시오.", "insight": _insight("ai-democracy", f"{topic} 추진과 국민 편익", "QUESTION", ["행정안전부"])},
        {"speaker": "행정안전부", "text": f"행정안전부는 {topic} 추진계획에 따라 공공서비스를 선제적으로 안내하도록 개편하고 있습니다.", "insight": _insight("ai-democracy", f"{topic} 추진과 국민 편익", "ANSWER", ["행정안전부"])},
        {"speaker": "행정안전부", "text": "올해는 민원 안내 품질과 데이터 연계를 우선 점검하겠습니다.", "insight": _insight("ai-democracy", f"{topic} 추진과 국민 편익", "ANSWER", ["행정안전부"], task="민원 안내 품질과 공공데이터 연계 점검")},
        {"speaker": "위원", "text": "개인정보 보호와 알고리즘 책임성에 관한 점검도 함께 진행해야 합니다.", "insight": _insight("privacy", "개인정보 보호와 알고리즘 책임성", "QUESTION", ["개인정보보호위원회"])},
        {"speaker": "개인정보보호위원회", "text": f"{topic} 적용 과정에서 개인정보 영향평가와 안전조치를 병행하겠습니다.", "insight": _insight("privacy", "개인정보 보호와 알고리즘 책임성", "ANSWER", ["개인정보보호위원회"], task="개인정보 영향평가와 안전조치 병행")},
        {"speaker": "위원", "text": "부처 간 추진 일정이 달라 국민이 혼란을 겪지 않도록 공통 기준이 필요합니다.", "insight": _insight("coordination", "부처별 추진 일정과 공통 기준", "QUESTION", ["국무조정실"])},
        {"speaker": "국무조정실", "text": f"국무조정실이 {topic} 부처별 과제를 취합하고 분기별 이행 상황을 점검하겠습니다.", "insight": _insight("coordination", "부처별 추진 일정과 공통 기준", "ANSWER", ["국무조정실"], task="부처별 과제 취합과 분기별 이행점검")},
        {"speaker": "위원", "text": "다음 회의에는 예산 집행 계획과 성과지표를 함께 보고해 주십시오.", "insight": _insight("budget", "예산 집행 계획과 성과지표", "QUESTION", ["기획재정부"])},
        {"speaker": "기획재정부", "text": "관련 예산은 기존 사업과의 중복 여부를 검토한 뒤 단계적으로 반영하겠습니다.", "insight": _insight("budget", "예산 집행 계획과 성과지표", "ANSWER", ["기획재정부"], task="기존 사업 중복 검토 후 예산 단계적 반영")},
        {"speaker": "위원", "text": f"정리하면 {topic} 추진계획, 개인정보 보호, 부처별 이행점검이 후속 과제입니다.", "insight": _insight("coordination", "부처별 추진 일정과 공통 기준", "QUESTION", ["국무조정실"])},
        {"speaker": "위원장", "text": "요청한 자료와 세부 일정은 다음 회의 전까지 제출해 주시기 바랍니다.", "insight": _insight("coordination", "부처별 추진 일정과 공통 기준", "STATEMENT", ["국무조정실"], task="요청 자료와 세부 일정 제출")},
    ]
