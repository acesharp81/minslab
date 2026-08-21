from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .contracts import CONTRACTS


class SourceStatus(StrEnum):
    APPLICATION_REQUIRED = "APPLICATION_REQUIRED"
    KEY_READY = "KEY_READY"
    CONTRACT_VERIFIED = "CONTRACT_VERIFIED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    key: str
    official_name: str
    purpose: str
    data_go_kr_url: str
    portal_url: str
    status: SourceStatus = SourceStatus.APPLICATION_REQUIRED
    authentication_required: bool = True
    endpoint: str | None = None
    last_contract_verified_at: str | None = None

    @property
    def callable(self) -> bool:
        return self.status in {SourceStatus.CONTRACT_VERIFIED, SourceStatus.ACTIVE} and bool(self.endpoint)


SOURCE_CATALOG: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        key="assembly_schedule",
        official_name="국회 국회사무처_국회일정 통합 API",
        purpose="오늘 예정·개최 회의와 국회 일정 확인",
        data_go_kr_url="https://www.data.go.kr/data/15126132/openapi.do",
        portal_url="https://open.assembly.go.kr/portal/data/service/selectAPIServicePage.do/OOWY4R001216HX11437",
    ),
    SourceDefinition(
        key="members",
        official_name="국회 국회사무처_국회의원 정보 통합 API",
        purpose="의원 식별과 소속·활동 정보 정규화",
        data_go_kr_url="https://www.data.go.kr/data/15126133/openapi.do",
        portal_url="https://open.assembly.go.kr/portal/data/service/selectAPIServicePage.do/OOWY4R001216HX11439",
    ),
    SourceDefinition(
        key="bills",
        official_name="국회 국회사무처_의안정보 통합 API",
        purpose="의안 기본정보와 처리 흐름 확인",
        data_go_kr_url="https://www.data.go.kr/data/15126134/openapi.do",
        portal_url="https://open.assembly.go.kr/portal/data/service/selectAPIServicePage.do/OOWY4R001216HX11440",
    ),
    SourceDefinition(
        key="plenary_minutes",
        official_name="국회 국회사무처_본회의 회의록",
        purpose="본회의 발언·의사진행의 공식 원문 확보",
        data_go_kr_url="https://www.data.go.kr/data/15126007/openapi.do",
        portal_url="https://open.assembly.go.kr/portal/data/service/selectServicePage.do?infId=OO1X9P001017YF13038",
    ),
    SourceDefinition(
        key="committee_minutes",
        official_name="국회 국회사무처_위원회 회의록",
        purpose="위원회 질의·답변과 의사진행의 공식 원문 확보",
        data_go_kr_url="https://www.data.go.kr/data/15126038/openapi.do",
        portal_url="https://open.assembly.go.kr/portal/data/service/selectServicePage.do?infId=OR137O001023MZ19321",
    ),
    SourceDefinition(
        key="meeting_agendas",
        official_name="국회 국회사무처_회의별 의안목록",
        purpose="회의와 안건·의안 연결",
        data_go_kr_url="https://www.data.go.kr/data/15126161/openapi.do",
        portal_url="https://open.assembly.go.kr/portal/data/service/selectAPIServicePage.do/OOWY4R001216HX11525",
    ),
    SourceDefinition(
        key="plenary_votes",
        official_name="국회 국회사무처_국회의원 본회의 표결정보",
        purpose="본회의 의결과 의원별 표결의 공식 결과 확보",
        data_go_kr_url="https://www.data.go.kr/data/15125948/openapi.do",
        portal_url="https://open.assembly.go.kr/portal/data/service/selectServicePage.do?infId=OPR1MQ000998LC12535",
    ),
    SourceDefinition(
        key="committees",
        official_name="국회 국회사무처_위원회 현황 정보",
        purpose="위원회 조직과 명칭 정규화",
        data_go_kr_url="https://www.data.go.kr/data/15126037/openapi.do",
        portal_url="https://open.assembly.go.kr/portal/data/service/selectServicePage.do?infId=O2Q4ZT001004PV11014",
    ),
)


def public_catalog() -> list[dict[str, object]]:
    return [
        {
            "key": source.key,
            "official_name": source.official_name,
            "purpose": source.purpose,
            "data_go_kr_url": source.data_go_kr_url,
            "portal_url": source.portal_url,
            "status": SourceStatus.CONTRACT_VERIFIED.value if contract else source.status.value,
            "authentication_required": source.authentication_required,
            "endpoint_verified": bool(contract),
            "callable": bool(contract),
            "resource": contract.resource if contract else None,
            "required_parameters": list(contract.required_parameters) if contract else [],
            "last_contract_verified_at": contract.verified_at if contract else None,
        }
        for source in SOURCE_CATALOG
        for contract in [CONTRACTS.get(source.key)]
    ]
