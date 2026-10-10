"""Read the public Government Joint Civil Petition Center case board and attachments."""
from __future__ import annotations

import hashlib
import math
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

BOARD_URL = "https://counseling.go.kr/sub/notice/notice.do?boardGubun=cas"
DETAIL_URL = "https://counseling.go.kr/sub/notice/notice_view.do"
DOWNLOAD_URL = "https://counseling.go.kr/backoffice/download.do"
ORIGIN = "https://counseling.go.kr"
POSTS_PER_PAGE = 10
MAX_PAGES = 100
MAX_ATTACHMENT_BYTES = 50_000_000
REQUEST_DELAY_SECONDS = 0.8


def _text(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def list_page(markup: str, page: int) -> tuple[list[dict], int]:
    soup = BeautifulSoup(markup, "html.parser")
    result = soup.select_one(".search_result")
    count = re.search(r"([\d,]+)\s*건", result.get_text(" ", strip=True) if result else "")
    if not count:
        raise ValueError("게시판 검색결과 건수를 읽지 못했습니다.")
    total = int(count.group(1).replace(",", ""))
    posts = []
    for row in soup.select("table.notice_table tbody tr"):
        columns = row.find_all("td", recursive=False)
        if len(columns) < 4:
            continue
        link = columns[1].find("a", href=True)
        match = re.search(r"view_Board\(['\"]?(\d+)", link.get("href", "") if link else "")
        if match:
            posts.append({"board_seq": match.group(1), "title": link.get_text(" ", strip=True),
                          "department": columns[2].get_text(" ", strip=True),
                          "posted_at": columns[3].get_text(" ", strip=True), "page_index": page})
    if total and not posts:
        raise ValueError(f"게시판 {page}페이지에서 게시글을 읽지 못했습니다.")
    return posts, total


def detail_page(markup: str, post: dict) -> dict:
    soup = BeautifulSoup(markup, "html.parser")
    table = soup.select_one("table.noti_view")
    body = soup.select_one("table.noti_view td.notice_txt")
    if table is None or body is None:
        raise ValueError(f"게시글 {post['board_seq']}의 본문을 읽지 못했습니다.")
    title_cell = table.select_one("tr:first-child td")
    file_input = soup.select_one("input[name=fileName]")
    result = dict(post)
    result.update({"title": title_cell.get_text(" ", strip=True) if title_cell else post["title"],
                   "body": _text(body.get_text("\n", strip=True)),
                   "attachment_name": file_input.get("value", "").strip() if file_input else "",
                   "source_url": DETAIL_URL + "?" + urlencode({"boardGubun": "cas", "boardSeq": post["board_seq"],
                                                                  "pageIndex": post["page_index"]})})
    return result


def extract_attachment(content: bytes, name: str, path: Path) -> tuple[str, str]:
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"첨부파일이 {MAX_ATTACHMENT_BYTES}바이트 제한을 초과했습니다: {name}")
    if content.startswith(b"%PDF"):
        completed = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True,
                                   timeout=60, check=False)
        if completed.returncode != 0:
            raise ValueError(f"PDF 본문 추출 실패: {name}")
        extracted = _text(completed.stdout.decode("utf-8", errors="replace").replace("\f", "\n"))
        if not extracted:
            raise ValueError(f"PDF에 추출 가능한 텍스트가 없습니다: {name}")
        return extracted, "pdftotext-layout"
    if content.startswith(b"\xd0\xcf\x11\xe0") or content.startswith(b"PK\x03\x04"):
        from extract_hwp import extract_text_from_hwp
        extracted, error = extract_text_from_hwp(str(path))
        if error or not extracted:
            raise ValueError(f"한글 문서 본문 추출 실패: {name}: {error or '본문 없음'}")
        return _text(extracted), "extract-hwp"
    if name.lower().endswith((".txt", ".text")):
        for encoding in ("utf-8-sig", "cp949"):
            try:
                return _text(content.decode(encoding)), "plain-text"
            except UnicodeDecodeError:
                pass
    raise ValueError(f"지원하지 않는 첨부 형식: {name}")


def qa_sections(text: str, title: str) -> list[tuple[str, str, str, str]]:
    """Return actual Q&A pairs, or one clearly labeled topic/body pair."""
    normalized = _text(text)
    question_markers = list(re.finditer(r"(?m)^\s*\(내용\)\s*", normalized))
    pairs = []
    for index, match in enumerate(question_markers):
        end = question_markers[index + 1].start() if index + 1 < len(question_markers) else len(normalized)
        segment = normalized[match.end():end]
        answer_mark = re.search(r"(?m)^\s*\(답변\)\s*", segment)
        if not answer_mark:
            continue
        question = _text(segment[:answer_mark.start()])
        answer = _text(segment[answer_mark.end():])
        # A numbered case heading preceding the next (내용) belongs to the next case.
        next_heading = re.search(r"(?m)\n[①-⑳]\s+[^\n]+\s*$", answer)
        if next_heading:
            answer = answer[:next_heading.start()].strip()
        if question and answer:
            pairs.append((question, answer, "attachment_question", "attachment_answer"))
    if pairs:
        return pairs
    issue = re.search(r"(?ms)^[ \t]*[○□■]?[ \t]*안건내용[ \t]*\n(.+?)(?=^[ \t]*[○□■][ \t]*(?:관련기관|주요쟁점|조정협의내용|사실확인)\b|\Z)", normalized)
    resolution = re.search(r"(?ms)^[ \t]*[○□■]?[ \t]*조정협의내용[ \t]*\n(.+)\Z", normalized)
    if issue and resolution:
        return [(_text(issue.group(1)), _text(resolution.group(1)), "attachment_issue", "attachment_resolution")]
    if normalized:
        return [(f"[상담 주제] {title}", normalized, "post_title", "attachment_full_text")]
    return []


def records_for_post(post: dict, attachment_text: str, attachment_sha: str,
                     extraction_method: str, timestamp: str) -> list[dict]:
    body = post.get("body", "")
    source_text = attachment_text or body
    sections = qa_sections(source_text, post["title"])
    if not sections:
        raise ValueError(f"게시글 {post['board_seq']}에 저장할 본문이 없습니다.")
    result = []
    for index, (question, answer, question_origin, answer_origin) in enumerate(sections, 1):
        digest = hashlib.sha256((f"counseling-board:{post['board_seq']}:{attachment_sha}:{index}:" +
                                 question + "\n" + answer).encode("utf-8")).hexdigest()
        raw = {"source_type": "counseling_board", "board_seq": post["board_seq"],
               "title": post["title"], "department": post.get("department", ""),
               "posted_at": post.get("posted_at", ""), "source_url": post["source_url"],
               "body": body, "attachment_name": post.get("attachment_name", ""),
               "attachment_sha256": attachment_sha, "extraction_method": extraction_method,
               "section_index": index, "section_count": len(sections),
               "question_origin": question_origin, "answer_origin": answer_origin}
        if index == 1 and attachment_text:
            raw["attachment_text"] = attachment_text
        result.append({"id": digest[:24], "question": question, "answer": answer,
                       "source_name": "정부합동민원센터 민원상담 사례", "institution_code": "",
                       "keywords": post["title"], "raw": raw,
                       "request_params": {"boardGubun": "cas", "pageIndex": post["page_index"],
                                          "boardSeq": post["board_seq"]},
                       "first_collected_at": timestamp})
    return result


def request(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    time.sleep(REQUEST_DELAY_SECONDS)
    for attempt in range(3):
        response = client.request(method, url, **kwargs)
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(2 ** (attempt + 1))
            continue
        response.raise_for_status()
        return response
    raise RuntimeError("reachable")


def all_posts(client: httpx.Client) -> list[dict]:
    first = request(client, "GET", BOARD_URL).text
    posts, total = list_page(first, 1)
    pages = math.ceil(total / POSTS_PER_PAGE)
    if pages > MAX_PAGES:
        raise ValueError(f"게시판 페이지 수가 예상 범위를 벗어났습니다: {pages}")
    for page in range(2, pages + 1):
        response = request(client, "GET", BOARD_URL, params={"boardGubun": "cas", "pageIndex": page})
        items, other_total = list_page(response.text, page)
        if other_total != total:
            raise ValueError("게시판 조회 중 총 게시글 수가 변경되었습니다. 다음 실행에서 재시도합니다.")
        posts.extend(items)
    if len(posts) != total:
        raise ValueError(f"게시판 목록 누락: {len(posts)}/{total}")
    return posts


def fetch_post(client: httpx.Client, item: dict, folder: Path) -> tuple[dict, str, str, str]:
    response = request(client, "GET", DETAIL_URL,
                       params={"boardGubun": "cas", "boardSeq": item["board_seq"], "pageIndex": item["page_index"]})
    post = detail_page(response.text, item)
    name = post["attachment_name"]
    if not name:
        return post, "", "", "html-body"
    response = request(client, "POST", DOWNLOAD_URL,
                       data={"boardSeq": item["board_seq"], "boardGubun": "cas", "fileName": name},
                       headers={"Referer": post["source_url"]})
    content = response.content
    if not content or len(content) > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"게시글 {item['board_seq']} 첨부파일이 비어 있거나 너무 큽니다.")
    digest = hashlib.sha256(content).hexdigest()
    extension = Path(name).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,6}", extension):
        extension = ".bin"
    attachment = folder / "board" / "attachments" / f"{item['board_seq']}-{digest[:16]}{extension}"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    if not attachment.exists():
        attachment.write_bytes(content)
    extracted, method = extract_attachment(content, name, attachment)
    if extracted:
        text_path = folder / "board" / "text" / f"{item['board_seq']}-{digest[:16]}.txt"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        if not text_path.exists():
            text_path.write_text(extracted, encoding="utf-8")
    return post, extracted, digest, method
