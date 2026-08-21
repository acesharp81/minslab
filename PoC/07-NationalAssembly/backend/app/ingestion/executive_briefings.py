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
PRESIDENT_LIST_URL = "https://www.president.go.kr/ajaxf/frBoard/bbsViewGalleryList.do"
PARSER_VERSION = "korea-state-council-html/1.0"
USER_AGENT = "POC-07 official-publication-monitor/1.0"
NEWS_ID = re.compile(r"stateCouncilView\.do\?newsId=(\d+)")
MEETING_NUMBER = re.compile(r"제(\d+)회")
AGENDA = re.compile(r"<([^<>]{3,160})>\s*,?\s*(.*?)【소관\s*:\s*([^】]+)】", re.S)
MESSAGE_SIGNAL = re.compile(r"(이 대통령|대통령은).*(당부|지시|강조|주문|언급|평가|제안|말했)", re.S)


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
    return value.split()[0] if value else "소관 미상"


def parse_detail(item: dict[str, str], payload: SourcePayload, content_hash: str) -> dict[str, object]:
    soup = BeautifulSoup(payload.content, "html.parser")
    body = soup.select_one(".article_body .view_cont")
    if body is None:
        raise ValueError("official state-council body selector not found")
    text = _clean(body.get_text("\n", strip=True))
    meeting = MEETING_NUMBER.search(item["title"])
    agendas: list[dict[str, object]] = []
    for index, match in enumerate(AGENDA.finditer(text), start=1):
        title = _clean(match.group(1))
        description = _clean(match.group(2))
        if not title or not description or title in {"관계부처 합동", "부처 협조사항"}:
            continue
        agendas.append({
            "source_span_id": f"agenda-{index}",
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
    for index, paragraph in enumerate(body.select("p"), start=1):
        text = _clean(paragraph.get_text(" ", strip=True))
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
        "messages": messages,
        "message_count": len(messages),
        "content_hash": content_hash,
        "parser_version": PARSER_VERSION,
        "retrieved_at": payload.retrieved_at.isoformat(),
    }


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
        items.append(meeting)
    snapshot = {
        "schema_version": "executive-briefings.v1",
        "source_status": "OFFICIAL",
        "source": {
            "publisher": "대한민국 정책브리핑",
            "list_url": LIST_URL,
            "list_content_hash": list_artifact.content_hash,
            "president_list_url": PRESIDENT_LIST_URL,
            "president_list_content_hash": president_list_artifact.content_hash,
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
