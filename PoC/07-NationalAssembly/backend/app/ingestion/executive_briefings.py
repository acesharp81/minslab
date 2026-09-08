from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import requests
from bs4 import BeautifulSoup

from ..adapters.national_assembly.base import SourcePayload
from ..domain.ministry import canonical_ministry_name
from ..services.bill_official_document import extract_pdf_pages
from ..storage.raw_store import RawStore

LIST_URL = "https://www.korea.kr/briefing/stateCouncilList.do"
POLICY_BRIEFING_LIST_URL = "https://www.korea.kr/briefing/policyBriefingList.do"
PRESS_RELEASE_LIST_URL = "https://www.korea.kr/briefing/pressReleaseList.do"
PRESIDENT_LIST_URL = "https://www.president.go.kr/ajaxf/frBoard/bbsViewGalleryList.do"
PARSER_VERSION = "korea-state-council-html/1.7"
USER_AGENT = "POC-07 official-publication-monitor/1.0"
NEWS_ID = re.compile(r"stateCouncilView\.do\?newsId=(\d+)")
POLICY_NEWS_ID = re.compile(r"policyBriefingView\.do\?newsId=(\d+)")
PRESS_RELEASE_NEWS_ID = re.compile(r"pressReleaseView\.do\?newsId=(\d+)")
MEETING_NUMBER = re.compile(r"제(\d+)회")
QUOTED_POLICY_TITLE = re.compile(r"[「『]([^」』]{3,160})[」』]")
AGENDA = re.compile(r"<([^<>]{3,160})>\s*,?\s*(.*?)【소관\s*:\s*([^】]+)】", re.DOTALL)
REPORT_BULLET = re.compile(r"△\s*(.*?)(?=\s*△|$)", re.DOTALL)
REPORT_MINISTRY = re.compile(r"\s*(?:\(([^()]+)\)|<([^<>]+)>)\s*[,，]?\s*$")
NON_REPORT_COUNT = re.compile(
    r"^(?:법률공포안|법률안|대통령령안|총리령안|부령안|일반안건|보고안건)\s*\d+건$"
)
MESSAGE_SIGNAL = re.compile(r"(이 대통령|대통령은).*(당부|지시|강조|주문|언급|평가|제안|말했)", re.DOTALL)
GUIDANCE_SIGNAL = re.compile(
    r"(당부|지시|주문|제안|요청|강조|검토해\s*달라|마련해\s*달라|"
    r"개발해\s*달라|성과를\s*내\s*달라|대책도\s*검토)"
)
_REPORT_MATCH_STOP_WORDS = {
    "년도", "국가", "관련", "의의", "성과", "실현", "전략", "대책", "계획",
}


def _report_match_tokens(value: str) -> set[str]:
    tokens = {
        token.casefold()
        for token in re.findall(r"[가-힣a-zA-Z]{2,}", _clean(value))
        if token.casefold() not in _REPORT_MATCH_STOP_WORDS
    }
    compact = _compact_policy_title(value)
    for phrase in (
        "예산안", "민생안정", "인공지능", "ai", "고속철도",
        "독자ai",
        "주택신속공급", "중대범죄수사청", "중수청", "자살예방",
        "광복절", "비상국정운영", "경찰수사", "업무보고후속조치",
    ):
        if phrase in compact:
            tokens.add(phrase)
    return tokens

def fetch_html(source_key: str, url: str) -> SourcePayload:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(request, timeout=30) as response:
        return SourcePayload(
            source_key=source_key,
            content=response.read(),
            content_type=response.headers.get("Content-Type", "text/html"),
            retrieved_at=datetime.now(timezone.utc),
            source_url=response.geturl(),
            http_status=response.status,
        )


def fetch_binary(source_key: str, url: str) -> SourcePayload:
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"},
    )
    with urlopen(request, timeout=45) as response:
        return SourcePayload(
            source_key=source_key,
            content=response.read(),
            content_type=response.headers.get("Content-Type", "application/octet-stream"),
            retrieved_at=datetime.now(timezone.utc),
            source_url=response.geturl(),
            http_status=response.status,
        )


def fetch_president_list() -> SourcePayload:
    form = {
        "pageNo": "1", "pagePerCnt": "100", "MENU_CD": "nFSy219D",
        "CONTENTS_CD": "vqNUjDNc", "pSiteNo": "2", "pBoardSeq": "2",
        "SHORT_URL": "briefings", "sSearchGbn": "subject", "sSearchTxt": "국무회의",
    }
    response = requests.post(
        PRESIDENT_LIST_URL, data=form, timeout=30,
    )
    response.raise_for_status()
    return SourcePayload(
        source_key="president_state_council_list",
        content=response.content,
        content_type=response.headers.get("Content-Type", "application/json"),
        retrieved_at=datetime.now(timezone.utc),
        source_url=response.url,
        http_status=response.status_code,
    )


def fetch_policy_briefing_list(
    start_date: str, end_date: str | None = None, *, page_index: int = 1,
) -> SourcePayload:
    start_iso = start_date.replace(".", "-")
    end_iso = (end_date or start_date).replace(".", "-")
    response = requests.post(
        POLICY_BRIEFING_LIST_URL,
        data={
            "pageIndex": str(page_index),
            "startDate": start_iso,
            "endDate": end_iso,
            "srchType": "",
            "srchWord": "",
            "period": "",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    return SourcePayload(
        source_key="executive_ministry_briefing_list",
        content=response.content,
        content_type=response.headers.get("Content-Type", "text/html"),
        retrieved_at=datetime.now(timezone.utc),
        source_url=response.url,
        http_status=response.status_code,
    )


def fetch_press_release_list(
    start_date: str,
    end_date: str,
    query: str,
    *,
    page_index: int = 1,
) -> SourcePayload:
    response = requests.post(
        PRESS_RELEASE_LIST_URL,
        data={
            "pageIndex": str(page_index),
            "startDate": start_date.replace(".", "-"),
            "endDate": end_date.replace(".", "-"),
            "srchType": "title",
            "srchWord": query,
            "period": "",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    return SourcePayload(
        source_key="executive_ministry_press_release_list",
        content=response.content,
        content_type=response.headers.get("Content-Type", "text/html"),
        retrieved_at=datetime.now(timezone.utc),
        source_url=response.url,
        http_status=response.status_code,
    )


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _meeting_number(value: str) -> int | None:
    """Use the final numbered council in composite titles such as 을지국무회의."""
    matches = MEETING_NUMBER.findall(value)
    return int(matches[-1]) if matches else None


def parse_list(content: bytes, limit: int = 10) -> list[dict[str, str]]:
    soup = BeautifulSoup(content, "html.parser")
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.select("a[onclick*='stateCouncilView.do?newsId=']"):
        contract = anchor.get("onclick", "")
        match = NEWS_ID.search(contract)
        title = anchor.select_one("strong")
        if not match or not title or match.group(1) in seen:
            continue
        heading = _clean(title.get_text(" ", strip=True))
        if "국무회의 브리핑" not in heading:
            continue
        seen.add(match.group(1))
        container = anchor.find_parent(["li", "tr"])
        date_node = container.select_one(".source span, .date") if container else None
        found.append({
            "news_id": match.group(1),
            "title": heading,
            "published_date": _clean(date_node.get_text()) if date_node else "",
            "source_url": urljoin(LIST_URL, f"/briefing/stateCouncilView.do?newsId={match.group(1)}"),
        })
        if len(found) >= limit:
            break
    return found


def _ministry_label(raw: str) -> str:
    value = re.sub(r"\s+\d{2,4}-\d{3,4}-\d{4}.*$", "", _clean(raw))
    label = value.split()[0] if value else "소관 미상"
    return canonical_ministry_name(label)


def _report_ministries(raw: str) -> list[str]:
    values = re.split(r"\s*(?:·|/|,|및)\s*", _clean(raw))
    ministries = []
    for value in values:
        if not value:
            continue
        label = _ministry_label(value)
        if label not in ministries:
            ministries.append(label)
    return ministries or ["관계부처"]


def _extract_ministry_reports(text: str) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    for signal in re.finditer(r"부처보고", text):
        sentence_start = text.rfind(".", 0, signal.start()) + 1
        section = text[sentence_start:signal.start()]
        for marker in ("토의하였으며,", "토의하였고,", "또한,"):
            marker_end = section.rfind(marker)
            if marker_end >= 0:
                section = section[marker_end + len(marker):]
        for match in REPORT_BULLET.finditer(section):
            evidence = _clean(match.group(0)).rstrip(" ,，")
            value = _clean(match.group(1)).rstrip(" ,，")
            value = re.sub(
                r"\s*(?:(?:과|와|에)\s*)?(?:관련(?:하여)?|관하여)\s*$",
                "", value,
            ).rstrip(" ,，")
            ministry_match = REPORT_MINISTRY.search(value)
            if ministry_match:
                ministry_source = ministry_match.group(1) or ministry_match.group(2) or ""
                ministries = _report_ministries(ministry_source)
                title = _clean(value[:ministry_match.start()]).rstrip(" ,，")
            else:
                ministries = ["관계부처"]
                title = value
            if not title or NON_REPORT_COUNT.fullmatch(title):
                continue
            reports.append({
                "topic": title,
                "ministries": ministries,
                "ministry_evidence": evidence,
            })
    return reports


def parse_policy_briefing_list(content: bytes) -> list[dict[str, str]]:
    soup = BeautifulSoup(content, "html.parser")
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in soup.select("tbody tr"):
        cells = row.find_all("td", recursive=False)
        anchor = row.select_one("a[href*='policyBriefingView.do?newsId='] strong")
        if len(cells) < 3 or anchor is None or anchor.parent is None:
            continue
        match = POLICY_NEWS_ID.search(str(anchor.parent.get("href") or ""))
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        found.append({
            "briefing_id": match.group(1),
            "ministry": _ministry_label(cells[0].get_text(" ", strip=True)),
            "title": _clean(anchor.get_text(" ", strip=True)),
            "published_date": _clean(cells[2].get_text(" ", strip=True)),
            "presenter": _clean(cells[3].get_text(" ", strip=True)) if len(cells) > 3 else "",
            "source_url": urljoin(
                POLICY_BRIEFING_LIST_URL,
                f"/briefing/policyBriefingView.do?newsId={match.group(1)}",
            ),
        })
    return found


def parse_press_release_list(content: bytes) -> list[dict[str, str]]:
    soup = BeautifulSoup(content, "html.parser")
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in soup.select(".article_body .list_type li"):
        anchor = row.select_one("a[href*='pressReleaseView.do?newsId=']")
        title = anchor.select_one("strong") if anchor else None
        if anchor is None or title is None:
            continue
        match = PRESS_RELEASE_NEWS_ID.search(str(anchor.get("href") or ""))
        if not match or match.group(1) in seen:
            continue
        source = row.select(".source span")
        if len(source) < 2:
            continue
        seen.add(match.group(1))
        lead = row.select_one(".lead")
        found.append({
            "briefing_id": match.group(1),
            "ministry": _ministry_label(source[-1].get_text(" ", strip=True)),
            "title": _clean(title.get_text(" ", strip=True)),
            "published_date": _clean(source[0].get_text(" ", strip=True)).replace("-", "."),
            "presenter": "",
            "preview_summary": _clean(lead.get_text(" ", strip=True)) if lead else "",
            "source_kind": "PRESS_RELEASE",
            "source_url": urljoin(
                PRESS_RELEASE_LIST_URL,
                f"/briefing/pressReleaseView.do?newsId={match.group(1)}",
            ),
        })
    return found


def parse_policy_briefing_detail(
    listed: dict[str, str], payload: SourcePayload, content_hash: str,
) -> dict[str, object]:
    soup = BeautifulSoup(payload.content, "html.parser")
    body = soup.select_one(".article_body .view_cont")
    if body is None:
        raise ValueError("official ministry briefing body selector not found")
    text = _clean(body.get_text(" ", strip=True))
    relation_evidence = ""
    for sentence in re.split(r"(?<=[.!?다요])\s+", text):
        if "국무회의" in sentence and "보고" in sentence:
            relation_evidence = sentence[:320]
            break
    return {
        **listed,
        "source_kind": "POLICY_BRIEFING",
        "summary": text[:4000],
        "relation_evidence": relation_evidence,
        "content_hash": content_hash,
        "parser_version": PARSER_VERSION,
        "retrieved_at": payload.retrieved_at.isoformat(),
        "authority_status": "OFFICIAL",
    }


_PRESS_BOILERPLATE = re.compile(
    r"관련\s*보도자료\s*내용입니다|자세한\s*내용은\s*첨부파일|"
    r"정책브리핑의\s*자료는|무단\s*전재|재배포\s*금지"
)


def parse_press_release_detail(
    listed: dict[str, str], payload: SourcePayload, content_hash: str,
) -> dict[str, object]:
    soup = BeautifulSoup(payload.content, "html.parser")
    body = soup.select_one(".article_body .view_cont")
    body_text = _clean(body.get_text(" ", strip=True)) if body else ""
    if _PRESS_BOILERPLATE.search(body_text) or len(body_text) < 120:
        body_text = ""
    pdf_url = ""
    for anchor in soup.select(".filedown a[href*='download.do']"):
        label = _clean(anchor.get_text(" ", strip=True)).casefold()
        image = anchor.select_one("img[alt]")
        image_alt = str(image.get("alt") or "").casefold() if image else ""
        if label.endswith(".pdf") or "pdf" in image_alt:
            pdf_url = urljoin(payload.source_url, str(anchor.get("href") or ""))
            break
    return {
        **listed,
        "source_kind": "PRESS_RELEASE",
        "summary": body_text[:8000],
        "pdf_url": pdf_url,
        "relation_evidence": "",
        "content_hash": content_hash,
        "parser_version": PARSER_VERSION,
        "retrieved_at": payload.retrieved_at.isoformat(),
        "authority_status": "OFFICIAL",
    }


def _press_release_search_query(topic: str) -> str:
    compact = _compact_policy_title(topic)
    known = (
        ("주택신속공급", "주택 신속공급"),
        ("중대범죄수사청", "중대범죄수사청"),
        ("중수청", "중대범죄수사청"),
        ("추석민생안정", "추석 민생안정대책"),
        ("독자ai모델", "독자 AI 모델"),
        ("독자ai", "독자 AI 모델"),
        ("ai민주정부", "AI 민주정부"),
        ("인공지능민주정부", "AI 민주정부"),
        ("고속철도통합", "고속철도 통합"),
        ("자살예방", "자살예방"),
    )
    for marker, query in known:
        if marker in compact:
            return query
    tokens = sorted(_report_match_tokens(topic), key=lambda token: (-len(token), token))
    return " ".join(tokens[:2])


def _pdf_press_release_text(pages: list[str]) -> str:
    blocks: list[str] = []
    current: list[str] = []
    body_started = False

    def flush() -> None:
        if not current:
            return
        block = _clean(" ".join(current))
        block = re.sub(r"(?<=[가-힣A-Za-z0-9」)])\*", "", block)
        block = re.sub(r"·\s+", "·", block)
        block = re.sub(
            r"(?<=[가-힣])\s+(하고|하며|하여|할|해|으로|에서|되는|되도록)\b",
            r"\1",
            block,
        )
        current.clear()
        if block and not block.endswith((".", "다.", "요.", "함.", "임.")):
            block += "."
        if block:
            blocks.append(block)

    for page in pages:
        for raw_line in page.splitlines():
            line = _clean(raw_line)
            if not line or re.fullmatch(r"-?\s*\d+\s*-?", line):
                flush()
                continue
            if line.startswith(("담당 부서", "<국토부>", "문의")):
                flush()
                return " ".join(blocks)[:12000]
            is_lead = line.startswith("-") and not re.match(r"-\s*\d+\s*-", line)
            is_body = line.startswith(("□", "ㅇ", "○", "◇", "△"))
            if not body_started and not (is_lead or is_body):
                continue
            if is_body:
                body_started = True
            if is_lead or is_body:
                flush()
                line = re.sub(r"^(?:-|□|ㅇ|○|◇|△)\s*", "", line)
            if line.startswith("*"):
                continue
            current.append(line)
    flush()
    return " ".join(blocks)[:12000]


def _compact_policy_title(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", _clean(value).casefold())


def report_matches_policy_briefing(
    report: dict[str, object], briefing: dict[str, str],
) -> bool:
    report_ministries = {
        _ministry_label(str(value)) for value in report.get("ministries", [])
    }
    known_ministries = report_ministries - {"관계부처", "소관 미상"}
    if (
        known_ministries
        and _ministry_label(briefing.get("ministry", "")) not in known_ministries
    ):
        return False
    report_date = str(report.get("published_date") or "")
    briefing_date = str(briefing.get("published_date") or "")
    if report_date and briefing_date:
        try:
            report_day = datetime.strptime(report_date.replace("-", "."), "%Y.%m.%d")
            briefing_day = datetime.strptime(briefing_date.replace("-", "."), "%Y.%m.%d")
        except ValueError:
            return False
        age = (report_day - briefing_day).days
        if age < 0 or age > 21:
            return False
    report_title = _compact_policy_title(str(report.get("topic") or ""))
    briefing_title = _compact_policy_title(str(briefing.get("title") or ""))
    if min(len(report_title), len(briefing_title)) < 8:
        return False
    if report_title in briefing_title or briefing_title in report_title:
        return True
    report_tokens = _report_match_tokens(str(report.get("topic") or ""))
    briefing_tokens = _report_match_tokens(str(briefing.get("title") or ""))
    shared = report_tokens & briefing_tokens
    if any(len(token) >= 6 for token in shared):
        return True
    coverage = len(shared) / max(1, min(len(report_tokens), len(briefing_tokens)))
    return len(shared) >= 2 and coverage >= 0.5


def parse_detail(item: dict[str, str], payload: SourcePayload, content_hash: str) -> dict[str, object]:
    soup = BeautifulSoup(payload.content, "html.parser")
    body = soup.select_one(".article_body .view_cont")
    if body is None:
        raise ValueError("official state-council body selector not found")
    text = _clean(body.get_text("\n", strip=True))
    meeting_number = _meeting_number(item["title"])
    agendas: list[dict[str, object]] = []
    for index, report in enumerate(_extract_ministry_reports(text), start=1):
        ministries = list(report["ministries"])
        has_explicit_ministry = ministries != ["관계부처"]
        agendas.append({
            "source_span_id": f"report-{index}",
            "agenda_type": "REPORT",
            "topic": report["topic"],
            "summary": (
                f"{'·'.join(ministries)}가 「{report['topic']}」을(를) 보고했습니다. "
                "공식 결과문에서 보고 제목과 담당 부처가 확인됐습니다."
                if has_explicit_ministry else
                f"관계부처가 「{report['topic']}」을(를) 보고했습니다. "
                "공식 결과문에는 담당 부처가 별도로 명시되지 않았습니다."
            ),
            "ministries": ministries,
            "ministry_evidence": report["ministry_evidence"],
            "authority_status": "OFFICIAL",
            "related_ministry_briefings": [],
        })
    for index, match in enumerate(AGENDA.finditer(text), start=1):
        title = _clean(match.group(1))
        description = _clean(match.group(2))
        if not title or not description or title in {"관계부처 합동", "부처 협조사항"}:
            continue
        agendas.append({
            "source_span_id": f"agenda-{index}",
            "agenda_type": "DELIBERATION",
            "topic": title,
            "summary": description[:420],
            "ministries": [_ministry_label(match.group(3))],
            "ministry_evidence": _clean(match.group(3)),
            "authority_status": "OFFICIAL",
        })
    return {
        **item,
        "meeting_number": meeting_number,
        "chair": "대통령",
        "agenda_count": len(agendas),
        "agendas": agendas,
        "content_hash": content_hash,
        "parser_version": PARSER_VERSION,
        "retrieved_at": payload.retrieved_at.isoformat(),
    }


def attach_related_ministry_briefings(
    meeting: dict[str, object],
    policy_rows: list[dict[str, str]],
    *,
    fetch_detail: object,
) -> int:
    linked_count = 0
    detail_cache: dict[str, dict[str, object]] = {}
    for agenda in meeting.get("agendas", []):
        if agenda.get("agenda_type") != "REPORT":
            continue
        agenda["published_date"] = meeting.get("published_date")
        candidates = [
            row for row in policy_rows if report_matches_policy_briefing(agenda, row)
        ]
        linked: list[dict[str, object]] = []
        for row in candidates:
            briefing_id = row["briefing_id"]
            cache_key = f"{row.get('source_kind') or 'POLICY_BRIEFING'}:{briefing_id}"
            if cache_key not in detail_cache:
                detail_cache[cache_key] = fetch_detail(row)
            same_day = str(row.get("published_date") or "") == str(
                meeting.get("published_date") or ""
            )
            is_press_release = row.get("source_kind") == "PRESS_RELEASE"
            detail = {
                **detail_cache[cache_key],
                "relation": {
                    "relation_type": (
                        ("SAME_DAY_MINISTRY_PRESS_RELEASE" if same_day
                         else "RELATED_MINISTRY_PRESS_RELEASE")
                        if is_press_release else
                        ("SAME_DAY_MINISTRY_REPORT_BRIEFING" if same_day
                         else "RELATED_MINISTRY_POLICY_BRIEFING")
                    ),
                    "label": (
                        ("같은 날·동일 부처·동일 주제의 공식 보도자료" if same_day
                         else "회의 전 공개된 동일 부처·동일 정책의 공식 보도자료")
                        if is_press_release else
                        ("같은 날·동일 부처·동일 주제의 공식 브리핑" if same_day
                         else "회의 전 공개된 동일 부처·동일 정책의 공식 브리핑")
                    ),
                    "authority_status": "VERIFIED",
                    "evidence": detail_cache[cache_key].get("relation_evidence") or (
                        f"회의일 {meeting.get('published_date')} 기준 21일 이내, "
                        f"{row.get('ministry')} 동일 부처, 제목 핵심 문구 일치"
                    ),
                },
            }
            linked.append(detail)
            linked_count += 1
        agenda["related_ministry_briefings"] = linked
    return linked_count


def parse_president_list(content: bytes) -> list[dict[str, object]]:
    payload = json.loads(content)
    rows = payload.get("data", {}).get("list", [])
    result = []
    for row in rows:
        title = _clean(str(row.get("SUBJECT") or ""))
        meeting_number = _meeting_number(title)
        published_date = str(row.get("WRITE_DATE") or "")
        code = str(row.get("BBS_CD") or "")
        if meeting_number is None or not published_date or not code:
            continue
        result.append({
            "meeting_number": meeting_number,
            "published_date": published_date,
            "briefing_id": code,
            "title": title,
            "source_url": f"https://www.president.go.kr/briefings/{code}",
        })
    return result


def _presidential_report_ministries(
    title: str, paragraphs: list[dict[str, object]],
) -> list[str]:
    escaped = re.escape(title)
    patterns = (
        re.compile(
            rf"([가-힣A-Za-z]+(?:부|처|청|위원회|실))(?:가|이)\s*"
            rf"(?:준비한|마련한)\s*[「『]?{escaped}"
        ),
        re.compile(
            rf"([가-힣A-Za-z]+(?:부|처|청|위원회|실))로부터\s*"
            rf"[「『]?{escaped}"
        ),
    )
    for paragraph in paragraphs:
        text = _clean(str(paragraph.get("text") or ""))
        if _compact_policy_title(title) not in _compact_policy_title(text):
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return [_ministry_label(match.group(1))]
    return ["관계부처"]


def attach_presidential_ministry_reports(meeting: dict[str, object]) -> int:
    """Recover report titles absent from a short state-council result notice.

    Some Korea.kr result pages list only deliberated agendas while the same-day
    presidential briefing carries the verified ministry-report list. The source
    paragraph is kept as evidence and no ministry is guessed when it is absent.
    """
    paragraphs = list(
        (meeting.get("presidential_briefing") or {}).get("paragraphs") or []
    )
    existing = {
        _compact_policy_title(str(agenda.get("topic") or ""))
        for agenda in meeting.get("agendas", [])
        if agenda.get("agenda_type") == "REPORT"
    }
    recovered: list[dict[str, object]] = []
    for paragraph in paragraphs:
        text = _clean(str(paragraph.get("text") or ""))
        signal = re.search(r"부처\s*보고", text)
        if not signal:
            continue
        section = text[:signal.start()]
        if "이어" in section:
            section = section.rsplit("이어", 1)[-1]
        titles = [_clean(value) for value in QUOTED_POLICY_TITLE.findall(section)]
        count_match = re.search(r"등\s*(\d+)건의?\s*$", section)
        if count_match:
            titles = titles[-int(count_match.group(1)):]
        for index, title in enumerate(titles, start=1):
            compact = _compact_policy_title(title)
            if not compact or compact in existing:
                continue
            ministries = _presidential_report_ministries(title, paragraphs)
            owner = "·".join(ministries)
            recovered.append({
                "source_span_id": (
                    f"president-report-{paragraph.get('source_span_id') or index}-{index}"
                ),
                "agenda_type": "REPORT",
                "topic": title,
                "summary": (
                    f"{owner}의 「{title}」 보고 사실이 청와대 공식 브리핑에서 "
                    "확인됐습니다."
                ),
                "ministries": ministries,
                "ministry_evidence": text,
                "authority_status": "OFFICIAL",
                "related_ministry_briefings": [],
                "source_origin": "PRESIDENTIAL_BRIEFING",
            })
            existing.add(compact)
    if recovered:
        meeting["agendas"] = recovered + list(meeting.get("agendas") or [])
        meeting["agenda_count"] = len(meeting["agendas"])
    return len(recovered)


def parse_president_detail(
    listed: dict[str, object], payload: SourcePayload, content_hash: str,
) -> dict[str, object]:
    soup = BeautifulSoup(payload.content, "html.parser")
    body = soup.select_one(".view_txt.ck-content")
    if body is None:
        raise ValueError("official presidential briefing body selector not found")
    messages = []
    paragraphs = []
    for index, paragraph in enumerate(body.select("p"), start=1):
        text = _clean(paragraph.get_text(" ", strip=True))
        if len(text) >= 10:
            paragraphs.append({
                "source_span_id": f"president-paragraph-{index}",
                "text": text,
                "authority_status": "OFFICIAL",
            })
        if len(text) < 20 or not MESSAGE_SIGNAL.search(text):
            continue
        messages.append({
            "source_span_id": f"president-paragraph-{index}",
            "speaker": "대통령",
            "text": text,
            "authority_status": "OFFICIAL",
        })
    return {
        **listed,
        "paragraphs": paragraphs,
        "paragraph_count": len(paragraphs),
        "messages": messages,
        "message_count": len(messages),
        "content_hash": content_hash,
        "parser_version": PARSER_VERSION,
        "retrieved_at": payload.retrieved_at.isoformat(),
    }


def attach_presidential_guidance(meeting: dict[str, object]) -> int:
    reports = [
        agenda for agenda in meeting.get("agendas", [])
        if agenda.get("agenda_type") == "REPORT"
    ]
    presidential = meeting.get("presidential_briefing") or {}
    paragraphs = list(presidential.get("paragraphs") or [])
    if not reports or not paragraphs:
        return 0
    linked = 0
    for report in reports:
        report["presidential_guidance"] = []
        report_title = _compact_policy_title(str(report.get("topic") or ""))
        report_tokens = _report_match_tokens(str(report.get("topic") or ""))
        candidates: list[tuple[float, int]] = []
        for index, paragraph in enumerate(paragraphs):
            raw_text = str(paragraph.get("text") or "")
            paragraph_text = _compact_policy_title(raw_text)
            paragraph_tokens = _report_match_tokens(raw_text)
            exact = report_title in paragraph_text
            overlap = len(report_tokens & paragraph_tokens) / max(1, len(report_tokens))
            if not exact and overlap < 0.34:
                continue
            matching_reports = sum(
                1 for candidate in reports
                if _compact_policy_title(str(candidate.get("topic") or ""))
                in paragraph_text
            )
            boilerplate = bool(re.search(
                r"오늘 회의에서는|부처\s*보고가 있었습니다|심의[․·]?의결했습니다",
                raw_text,
            ))
            score = (
                overlap * 5 + (2 if exact else 0)
                + (3 if GUIDANCE_SIGNAL.search(raw_text) else 0)
                - (4 if boilerplate else 0)
                - max(0, matching_reports - 1) * 2
            )
            if score > 0:
                candidates.append((score, index))
        if not candidates:
            continue
        start_index = max(candidates)[1]
        block = [paragraphs[start_index]]
        for paragraph in paragraphs[start_index + 1:start_index + 3]:
            text = str(paragraph.get("text") or "")
            compact = _compact_policy_title(text)
            if any(
                _compact_policy_title(str(candidate.get("topic") or "")) in compact
                for candidate in reports if candidate is not report
            ):
                break
            if "비공개 회의" in text or text.startswith("끝으로"):
                break
            if not (_report_match_tokens(text) & report_tokens):
                break
            block.append(paragraph)
        discussion = _clean(" ".join(str(row.get("text") or "") for row in block))
        report["discussion_summary"] = discussion[:900]
        directives = [
            row for row in block
            if GUIDANCE_SIGNAL.search(str(row.get("text") or ""))
        ]
        if not directives:
            continue
        report["presidential_guidance"].append({
            "guidance_type": "DIRECTIVE",
            "label": "대통령 지시",
            "text": _clean(" ".join(str(row.get("text") or "") for row in directives)),
            "target_ministries": list(report.get("ministries") or []),
            "source_span_ids": [
                row.get("source_span_id") for row in directives
                if row.get("source_span_id")
            ],
            "authority_status": "OFFICIAL",
        })
        linked += 1
    return linked


def collect(settings: object, limit: int = 10) -> dict[str, object]:
    store = RawStore(settings.raw_data_dir)
    listing = fetch_html("executive_state_council_list", LIST_URL)
    list_artifact = store.save(listing, parser_version=PARSER_VERSION)
    president_listing = fetch_president_list()
    president_list_artifact = store.save(president_listing, parser_version=PARSER_VERSION)
    president_rows = parse_president_list(president_listing.content)
    president_by_meeting = {
        (row["meeting_number"], row["published_date"]): row for row in president_rows
    }
    items = []
    for listed in parse_list(listing.content, limit=limit):
        detail = fetch_html("executive_state_council_detail", listed["source_url"])
        artifact = store.save(detail, parser_version=PARSER_VERSION)
        meeting = parse_detail(listed, detail, artifact.content_hash)
        president = president_by_meeting.get((meeting["meeting_number"], meeting["published_date"]))
        if president:
            president_detail = fetch_html("president_state_council_detail", str(president["source_url"]))
            president_artifact = store.save(president_detail, parser_version=PARSER_VERSION)
            meeting["presidential_briefing"] = parse_president_detail(
                president, president_detail, president_artifact.content_hash,
            )
        else:
            meeting["presidential_briefing"] = None
        meeting["presidential_report_count"] = attach_presidential_ministry_reports(
            meeting
        )
        meeting["presidential_guidance_count"] = attach_presidential_guidance(meeting)
        items.append(meeting)
    ministry_list_hashes: dict[str, str] = {}
    press_release_list_hashes: dict[str, str] = {}
    ministry_briefing_count = 0
    meeting_days = [
        datetime.strptime(str(item["published_date"]).replace("-", "."), "%Y.%m.%d")
        for item in items if item.get("published_date")
    ]
    policy_rows: list[dict[str, str]] = []
    press_rows: list[dict[str, str]] = []
    if meeting_days:
        start_date = (min(meeting_days) - timedelta(days=21)).strftime("%Y-%m-%d")
        end_date = max(meeting_days).strftime("%Y-%m-%d")
        seen_policy_ids: set[str] = set()
        for page_index in range(1, 21):
            policy_listing = fetch_policy_briefing_list(
                start_date, end_date, page_index=page_index,
            )
            policy_list_artifact = store.save(
                policy_listing, parser_version=PARSER_VERSION,
            )
            ministry_list_hashes[
                f"{start_date}:{end_date}:page-{page_index}"
            ] = policy_list_artifact.content_hash
            page_rows = parse_policy_briefing_list(policy_listing.content)
            new_rows = [
                row for row in page_rows
                if row["briefing_id"] not in seen_policy_ids
            ]
            policy_rows.extend(new_rows)
            seen_policy_ids.update(row["briefing_id"] for row in new_rows)
            if len(page_rows) < 30 or not new_rows:
                break

        press_queries = sorted({
            query
            for meeting in items
            for agenda in meeting.get("agendas", [])
            if agenda.get("agenda_type") == "REPORT"
            if (query := _press_release_search_query(str(agenda.get("topic") or "")))
        })
        seen_press_ids: set[str] = set()
        for query in press_queries:
            for page_index in range(1, 4):
                press_listing = fetch_press_release_list(
                    start_date, end_date, query, page_index=page_index,
                )
                press_list_artifact = store.save(
                    press_listing, parser_version=PARSER_VERSION,
                )
                press_release_list_hashes[
                    f"{query}:{start_date}:{end_date}:page-{page_index}"
                ] = press_list_artifact.content_hash
                page_rows = parse_press_release_list(press_listing.content)
                new_rows = [
                    row for row in page_rows
                    if row["briefing_id"] not in seen_press_ids
                ]
                press_rows.extend(new_rows)
                seen_press_ids.update(row["briefing_id"] for row in new_rows)
                if len(page_rows) < 30 or not new_rows:
                    break

    detail_cache: dict[str, dict[str, object]] = {}
    for meeting in items:
        if not any(
            agenda.get("agenda_type") == "REPORT"
            for agenda in meeting.get("agendas", [])
        ):
            continue
        def fetch_policy_detail(row: dict[str, str]) -> dict[str, object]:
            cache_key = f"{row.get('source_kind') or 'POLICY_BRIEFING'}:{row['briefing_id']}"
            if cache_key in detail_cache:
                return detail_cache[cache_key]
            if row.get("source_kind") == "PRESS_RELEASE":
                detail = fetch_html(
                    "executive_ministry_press_release_detail", str(row["source_url"]),
                )
                detail_artifact = store.save(detail, parser_version=PARSER_VERSION)
                parsed = parse_press_release_detail(
                    row, detail, detail_artifact.content_hash,
                )
                if not parsed.get("summary") and parsed.get("pdf_url"):
                    pdf = fetch_binary(
                        "executive_ministry_press_release_pdf",
                        str(parsed["pdf_url"]),
                    )
                    pdf_artifact = store.save(pdf, parser_version=PARSER_VERSION)
                    parsed["summary"] = _pdf_press_release_text(
                        extract_pdf_pages(pdf_artifact.content_path)
                    )
                    parsed["pdf_content_hash"] = pdf_artifact.content_hash
                if not parsed.get("summary"):
                    preview = str(row.get("preview_summary") or "")
                    if not _PRESS_BOILERPLATE.search(preview):
                        parsed["summary"] = preview[:4000]
                detail_cache[cache_key] = parsed
                return parsed
            detail = fetch_html(
                "executive_ministry_briefing_detail", str(row["source_url"]),
            )
            detail_artifact = store.save(detail, parser_version=PARSER_VERSION)
            parsed = parse_policy_briefing_detail(
                row, detail, detail_artifact.content_hash,
            )
            detail_cache[cache_key] = parsed
            return parsed

        ministry_briefing_count += attach_related_ministry_briefings(
            meeting, policy_rows + press_rows, fetch_detail=fetch_policy_detail,
        )
    snapshot = {
        "schema_version": "executive-briefings.v1",
        "source_status": "OFFICIAL",
        "source": {
            "publisher": "대한민국 정책브리핑",
            "list_url": LIST_URL,
            "list_content_hash": list_artifact.content_hash,
            "president_list_url": PRESIDENT_LIST_URL,
            "president_list_content_hash": president_list_artifact.content_hash,
            "ministry_briefing_list_url": POLICY_BRIEFING_LIST_URL,
            "ministry_briefing_list_content_hashes": ministry_list_hashes,
            "ministry_press_release_list_url": PRESS_RELEASE_LIST_URL,
            "ministry_press_release_list_content_hashes": press_release_list_hashes,
            "parser_version": PARSER_VERSION,
        },
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
        "count": len(items),
        "presidential_briefing_count": sum(bool(item["presidential_briefing"]) for item in items),
        "official_message_count": sum(
            item["presidential_briefing"]["message_count"]
            for item in items if item["presidential_briefing"]
        ),
        "presidential_guidance_count": sum(
            int(item.get("presidential_guidance_count") or 0) for item in items
        ),
        "ministry_briefing_count": ministry_briefing_count,
    }
    target = Path(settings.processed_data_dir) / "executive_briefings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as output:
        json.dump(snapshot, output, ensure_ascii=False, indent=2)
        temporary = Path(output.name)
    temporary.replace(target)
    return snapshot


def main() -> None:
    from ..config import get_settings

    snapshot = collect(get_settings())
    print(json.dumps({"event": "executive.official.completed", "count": snapshot["count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
