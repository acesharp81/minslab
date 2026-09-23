from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

import httpx

from ..config import Settings, get_settings


KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class G2BAttachment:
    name: str
    url: str


@dataclass(frozen=True)
class G2BNotice:
    stage: str
    notice_no: str
    bid_no: str | None
    agency_name: str
    agency_code: str | None
    title: str
    budget_amount: int | None
    posted_at: datetime | None
    deadline_at: datetime | None
    url: str | None
    attachments: list[G2BAttachment] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


SAMPLE_NOTICES = [
    {
        "stage": "prenotice", "notice_no": "SAMPLE-PRE-001", "agency_name": "디지털행정지원청",
        "title": "생성형 AI 기반 업무지원 챗봇 구축", "budget_amount": 850_000_000,
        "text": "제안요청서 3. 과업내용\n생성형 AI 기반 업무지원 챗봇을 구축한다. RAG 기반 지식검색과 LLM API, 벡터DB를 활용한다. 범정부 AI 공통기반 활용 여부는 제안 단계에서 검토한다.",
    },
    {
        "stage": "prenotice", "notice_no": "SAMPLE-PRE-002", "agency_name": "국민서비스원",
        "title": "민원상담 지능형 서비스 개선", "budget_amount": 420_000_000,
        "text": "과업범위\n자연어 처리 및 질의응답 모델을 이용하여 민원 상담 정확도를 개선하고 별도 GPU 추론 서버 도입을 검토한다.",
    },
    {
        "stage": "bid_notice", "notice_no": "SAMPLE-BID-003-00", "bid_no": "SAMPLE-BID-003",
        "agency_name": "공공데이터연구원", "title": "데이터 분석 플랫폼 고도화", "budget_amount": 280_000_000,
        "text": "기능요건\n빅데이터 분석과 머신러닝 모델 서빙 기능을 고도화한다. 공통기반 적용 범위는 문서만으로 확인되지 않는다.",
    },
    {
        "stage": "bid_notice", "notice_no": "SAMPLE-BID-004-00", "bid_no": "SAMPLE-BID-004",
        "agency_name": "시설운영공단", "title": "청사 시설관리 및 경비 용역", "budget_amount": 72_000_000,
        "text": "청사 시설관리, 미화 및 경비 인력을 운영한다.",
    },
    {
        "stage": "prenotice", "notice_no": "SAMPLE-PRE-005", "agency_name": "지역정보원",
        "title": "업무관리시스템 유지관리", "budget_amount": 510_000_000,
        "text": "기존 업무관리시스템의 안정적 유지관리와 장애 대응을 수행한다. AI 적용 여부는 명시되지 않았다.",
    },
]


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response", payload)
    header = response.get("header", {})
    code = str(header.get("resultCode", "00"))
    if code not in {"00", "0"}:
        raise RuntimeError(f"G2B API 오류 {code}: {header.get('resultMsg', 'unknown')}")
    body = response.get("body", {})
    items = body.get("items", [])
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    item = items.get("item", []) if isinstance(items, dict) else []
    if isinstance(item, dict):
        return [item]
    return item or []


def _integer(value: Any) -> int | None:
    try:
        return int(float(str(value).replace(",", ""))) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip().replace("-", "").replace(":", "").replace(" ", "")
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d"):
        try:
            return datetime.strptime(raw[:len(datetime.now().strftime(fmt))], fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    return None


class G2BClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def _request(self, base_url: str, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        # 포털의 Encoding 키가 입력되어도 한 번만 URL 인코딩되도록 원문 형태로 정규화한다.
        service_key = unquote(self.settings.g2b_service_key)
        request_params = {"serviceKey": service_key, "type": "json", **params}
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.settings.g2b_timeout_seconds, follow_redirects=False) as client:
            for attempt in range(3):
                try:
                    response = await client.get(f"{base_url}/{operation}", params=request_params)
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError as exc:
                    # httpx 예외 문자열에는 serviceKey가 든 전체 URL이 포함되므로 보존하지 않는다.
                    last_error = RuntimeError(f"HTTP {exc.response.status_code}")
                    if exc.response.status_code not in {429, 500, 502, 503, 504}:
                        break
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (2 ** attempt))
                except (httpx.RequestError, ValueError) as exc:
                    last_error = RuntimeError(type(exc).__name__)
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (2 ** attempt))
        detail = str(last_error) if last_error else "unknown"
        raise RuntimeError(f"G2B 호출 실패: {detail}") from None

    async def _paged(self, base_url: str, operation: str, common: dict[str, Any]) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for page in range(1, self.settings.g2b_max_pages + 1):
            payload = await self._request(base_url, operation, {**common, "pageNo": page, "numOfRows": self.settings.g2b_page_size})
            batch = _items(payload)
            collected.extend(batch)
            body = payload.get("response", payload).get("body", {})
            total = _integer(body.get("totalCount")) or len(collected)
            if not batch or len(collected) >= total:
                break
        return collected

    async def collect(self, lookback_days: int) -> list[G2BNotice]:
        if self.settings.g2b_mode == "mock":
            return self._mock_notices()
        if not self.settings.g2b_service_key:
            raise RuntimeError("실데이터 수집에는 G2B_SERVICE_KEY가 필요합니다.")
        now = datetime.now(KST)
        start = now - timedelta(days=max(1, lookback_days))
        period = {"inqryDiv": "1", "inqryBgnDt": start.strftime("%Y%m%d%H%M"), "inqryEndDt": now.strftime("%Y%m%d%H%M")}
        pre_items, bid_items = await asyncio.gather(
            self._paged(self.settings.g2b_base_url_prenotice, self.settings.g2b_operation_prenotice, period),
            self._paged(self.settings.g2b_base_url_bid, self.settings.g2b_operation_bid, period),
        )
        notices = [self._map_prenotice(item) for item in pre_items]
        notices.extend(self._map_bid(item) for item in bid_items)
        return notices

    async def bid_attachments(self, bid_no: str, bid_order: str = "00") -> list[G2BAttachment]:
        """e발주 첨부정보 어댑터. 후보 공고에만 호출해 개발계정 트래픽을 보호한다."""
        if self.settings.g2b_mode == "mock":
            return []
        payload = await self._request(
            self.settings.g2b_base_url_bid,
            self.settings.g2b_operation_bid_attach,
            {"pageNo": 1, "numOfRows": self.settings.max_files_per_notice, "bidNtceNo": bid_no, "bidNtceOrd": bid_order},
        )
        results: list[G2BAttachment] = []
        for item in _items(payload):
            url = str(item.get("atchFileUrl") or item.get("eorderAtchFileUrl") or item.get("downloadUrl") or "").strip()
            if not url:
                continue
            name = str(item.get("atchFileNm") or item.get("fileNm") or PathLike.name(url)).strip()
            results.append(G2BAttachment(name=name, url=url))
        return results[:self.settings.max_files_per_notice]

    async def prenotice_opinions(self, registration_no: str) -> list[dict[str, Any]]:
        """Return public opinion threads and institution replies for one pre-notice."""
        if self.settings.g2b_mode == "mock":
            raise RuntimeError("모의 모드에서는 실제 나라장터 의견을 조회할 수 없습니다. G2B_MODE=live로 설정해 주세요.")
        if not self.settings.g2b_service_key:
            raise RuntimeError("의견 답변 확인에는 G2B_SERVICE_KEY가 필요합니다.")
        return await self._paged(
            self.settings.g2b_base_url_prenotice,
            self.settings.g2b_operation_prenotice_opinion,
            {"inqryDiv": "2", "bfSpecRgstNo": registration_no},
        )

    def _mock_notices(self) -> list[G2BNotice]:
        now = datetime.now(KST)
        return [G2BNotice(
            stage=item["stage"], notice_no=item["notice_no"], bid_no=item.get("bid_no"),
            agency_name=item["agency_name"], agency_code=None, title=item["title"],
            budget_amount=item["budget_amount"], posted_at=now, deadline_at=now + timedelta(days=10),
            url=None, attachments=[G2BAttachment(f"{item['notice_no']}_제안요청서.txt", f"sample://{item['notice_no']}")], raw=item,
        ) for item in SAMPLE_NOTICES]

    def _map_prenotice(self, item: dict[str, Any]) -> G2BNotice:
        attachments = [G2BAttachment(PathLike.name(url), url) for index in range(1, 6) if (url := str(item.get(f"specDocFileUrl{index}") or "").strip())]
        notice_no = str(item.get("bfSpecRgstNo") or item.get("refNo") or "").strip()
        return G2BNotice(
            "prenotice", notice_no, None, str(item.get("rlDminsttNm") or item.get("orderInsttNm") or ""),
            str(item.get("rlDminsttCd") or item.get("orderInsttCd") or "") or None, str(item.get("prdctClsfcNoNm") or item.get("prdctNm") or "제목 없음"),
            _integer(item.get("asignBdgtAmt")), _datetime(item.get("rgstDt") or item.get("rcptDt")),
            _datetime(item.get("opninRgstClseDt")), None, attachments, item,
        )

    def _map_bid(self, item: dict[str, Any]) -> G2BNotice:
        bid_no = str(item.get("bidNtceNo") or "").strip()
        order = str(item.get("bidNtceOrd") or "00").strip()
        attachment_urls = []
        for index in range(1, 11):
            if url := str(item.get(f"ntceSpecDocUrl{index}") or "").strip():
                name = str(item.get(f"ntceSpecFileNm{index}") or PathLike.name(url)).strip()
                attachment_urls.append(G2BAttachment(name, url))
        if url := str(item.get("eorderAtchFileUrl") or "").strip():
            attachment_urls.append(G2BAttachment(PathLike.name(url), url))
        return G2BNotice(
            "bid_notice", f"{bid_no}-{order}", bid_no, str(item.get("dminsttNm") or item.get("ntceInsttNm") or ""),
            str(item.get("dminsttCd") or item.get("ntceInsttCd") or "") or None,
            str(item.get("bidNtceNm") or "제목 없음"), _integer(item.get("asignBdgtAmt") or item.get("presmptPrce")),
            _datetime(item.get("bidNtceDt") or item.get("rgstDt")), _datetime(item.get("bidClseDt")),
            str(item.get("bidNtceDtlUrl") or "") or None, attachment_urls, item,
        )


class PathLike:
    @staticmethod
    def name(url: str) -> str:
        from pathlib import PurePosixPath
        from urllib.parse import unquote, urlparse

        return unquote(PurePosixPath(urlparse(url).path).name) or "attachment"
