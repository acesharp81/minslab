from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
import requests

from ..adapters.national_assembly.base import SourcePayload
from ..storage.raw_store import RawStore


LIST_URL = "https://www.korea.kr/briefing/stateCouncilList.do"
POLICY_BRIEFING_LIST_URL = "https://www.korea.kr/briefing/policyBriefingList.do"
PRESIDENT_LIST_URL = "https://www.president.go.kr/ajaxf/frBoard/bbsViewGalleryList.do"
PARSER_VERSION = "korea-state-council-html/1.2"
USER_AGENT = "POC-07 official-publication-monitor/1.0"
NEWS_ID = re.compile(r"stateCouncilView\.do\?newsId=(\d+)")
POLICY_NEWS_ID = re.compile(r"policyBriefingView\.do\?newsId=(\d+)")
MEETING_NUMBER = re.compile(r"제(\d+)회")
AGENDA = re.compile(r"<([^<>]{3,160})>\s*,?\s*(.*?)【소관\s*:\s*([^】]+)】", re.S)
REPORT_BULLET = re.compile(r"△\s*(.*?)(?=\s*△|$)", re.S)
REPORT_MINISTRY = re.compile(r"\s*(?:\(([^()]+)\)|<([^<>]+)>)\s*[,，]?\s*$")
NON_REPORT_COUNT = re.compile(
    r"^(?:법률공포안|법률안|대통령령안|총리령안|부령안|일반안건|보고안건)\s*\d+건$"
)
MESSAGE_SIGNAL = re.compile(r"(이 대통령|대통령은).*(당부|지시|강조|주문|언급|평가|제안|말했)", re.S)
GUIDANCE_SIGNAL = re.compile(
    r"(당부|지시|주문|제안|요청|검토해\s*달라|마련해\s*달라|"
    r"개발해\s*달라|성과를\s*내\s*달라|대책도\s*검토)"
)
MINISTRY_ALIASES = {
    "재경부": "재정경제부",
    "과기정통부": "과학기술정보통신부",
    "과기통신부": "과학기술정보통신부",
    "행안부": "행정안전부",
    "국토부": "국토교통부",
    "국조실": "국무조정실",
    "산업부": "산업통상부",
    "복지부": "보건복지부",
    "행복청": "행정중심복합도시건설청",
    "중기부": "중소벤처기업부",
    "공정위": "공정거래위원회",
    "금융위": "금융위원회",
    "질병청": "질병관리청",
}


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


def fetch_policy_briefing_list(published_date: str) -> SourcePayload:
    iso_date = published_date.replace(".", "-")
    response = requests.post(
        POLICY_BRIEFING_LIST_URL,
        data={
            "pageIndex": "1",
            "startDate": iso_date,
            "endDate": iso_date,
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


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


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
    return MINISTRY_ALIASES.get(label, label)


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
        "summary": text[:700],
        "relation_evidence": relation_evidence,
        "content_hash": content_hash,
        "parser_version": PARSER_VERSION,
        "retrieved_at": payload.retrieved_at.isoformat(),
        "authority_status": "OFFICIAL",
    }


def _compact_policy_title(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", _clean(value).casefold())


def report_matches_policy_briefing(
    report: dict[str, object], briefing: dict[str, str],
) -> bool:
    report_ministries = {
        _ministry_label(str(value)) for value in report.get("ministries", [])
    }
    if _ministry_label(briefing.get("ministry", "")) not in report_ministries:
        return False
    report_date = str(report.get("published_date") or "")
    if report_date and report_date != str(briefing.get("published_date") or ""):
        return False
    report_title = _compact_policy_title(str(report.get("topic") or ""))
    briefing_title = _compact_policy_title(str(briefing.get("title") or ""))
    if min(len(report_title), len(briefing_title)) < 8:
        return False
    return report_title in briefing_title or briefing_title in report_title


def parse_detail(item: dict[str, str], payload: SourcePayload, content_hash: str) -> dict[str, object]:
    soup = BeautifulSoup(payload.content, "html.parser")
    body = soup.select_one(".article_body .view_cont")
    if body is None:
        raise ValueError("official state-council body selector not found")
    text = _clean(body.get_text("\n", strip=True))
    meeting = MEETING_NUMBER.search(item["title"])
    agendas: list[dict[str, object]] = []
    for index, report in enumerate(_extract_ministry_reports(text), start=1):
        ministries = list(report["ministries"])
        has_explicit_ministry = ministries != ["관계부처"]
        agendas.append({
            "source_span_id": f"report-{index}",
            "agenda_type": "REPORT",
            "topic": report["topic"],
            "summary": (
                "공식 결과문에서 보고 제목과 담당 부처가 확인됐으며 "
                "상세 핵심 내용은 연결 자료를 확인 중입니다."
                if has_explicit_ministry else
                "공식 결과문에서 보고 주제가 확인됐으며 담당 부처는 관계부처로 표기합니다."
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
        "meeting_number": int(meeting.group(1)) if meeting else None,
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
            if briefing_id not in detail_cache:
                detail_cache[briefing_id] = fetch_detail(row)
            detail = {
                **detail_cache[briefing_id],
                "relation": {
                    "relation_type": "SAME_DAY_MINISTRY_REPORT_BRIEFING",
                    "label": "같은 날·동일 부처·동일 주제의 공식 브리핑",
                    "authority_status": "VERIFIED",
                    "evidence": detail_cache[briefing_id].get("relation_evidence") or (
                        f"{meeting.get('published_date')} 동일 날짜, "
                        f"{row.get('ministry')} 동일 부처, 제목 핵심 문구 일치"
                    ),
                },
            }
            linked.append(detail)
            linked_count += 1
        agenda["related_ministry_briefings"] = linked
        if linked and not agenda.get("discussion_summary"):
            agenda["summary"] = linked[0].get("summary") or agenda["summary"]
    return linked_count


def parse_president_list(content: bytes) -> list[dict[str, object]]:
    payload = json.loads(content)
    rows = payload.get("data", {}).get("list", [])
    result = []
    for row in rows:
        title = _clean(str(row.get("SUBJECT") or ""))
        meeting = MEETING_NUMBER.search(title)
        published_date = str(row.get("WRITE_DATE") or "")
        code = str(row.get("BBS_CD") or "")
        if not meeting or not published_date or not code:
            continue
        result.append({
            "meeting_number": int(meeting.group(1)),
            "published_date": published_date,
            "briefing_id": code,
            "title": title,
            "source_url": f"https://www.president.go.kr/briefings/{code}",
        })
    return result


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
        start_index = None
        for index, paragraph in enumerate(paragraphs):
            paragraph_text = _compact_policy_title(str(paragraph.get("text") or ""))
            matching_reports = [
                candidate for candidate in reports
                if _compact_policy_title(str(candidate.get("topic") or ""))
                in paragraph_text
            ]
            if (
                report_title in paragraph_text
                and len(matching_reports) == 1
            ):
                start_index = index
                break
        if start_index is None:
            continue
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
            block.append(paragraph)
        discussion = _clean(" ".join(str(row.get("text") or "") for row in block))
        report["discussion_summary"] = discussion[:900]
        if not (report.get("related_ministry_briefings") or []):
            report["summary"] = discussion[:700]
        directives = [
            row for row in block
            if GUIDANCE_SIGNAL.search(str(row.get("text") or ""))
        ]
        if not directives:
            continue
        report["presidential_guidance"].append({
            "guidance_type": "DIRECTIVE",
            "label": "대통령 지시사항",
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
        meeting["presidential_guidance_count"] = attach_presidential_guidance(meeting)
        items.append(meeting)
    ministry_list_hashes: dict[str, str] = {}
    ministry_briefing_count = 0
    for meeting in items:
        if not any(
            agenda.get("agenda_type") == "REPORT"
            for agenda in meeting.get("agendas", [])
        ):
            continue
        published_date = str(meeting.get("published_date") or "")
        policy_listing = fetch_policy_briefing_list(published_date)
        policy_list_artifact = store.save(policy_listing, parser_version=PARSER_VERSION)
        ministry_list_hashes[published_date] = policy_list_artifact.content_hash
        policy_rows = parse_policy_briefing_list(policy_listing.content)

        def fetch_policy_detail(row: dict[str, str]) -> dict[str, object]:
            detail = fetch_html(
                "executive_ministry_briefing_detail", str(row["source_url"]),
            )
            detail_artifact = store.save(detail, parser_version=PARSER_VERSION)
            return parse_policy_briefing_detail(
                row, detail, detail_artifact.content_hash,
            )

        ministry_briefing_count += attach_related_ministry_briefings(
            meeting, policy_rows, fetch_detail=fetch_policy_detail,
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
