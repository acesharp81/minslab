"""Daily, resumable collection of the ACRC integrated call center examples."""

from __future__ import annotations

import asyncio
import fcntl
import html
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import time as clocktime
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo

import httpx


BASE = Path(__file__).resolve().parent


def _load_local_env() -> None:
    """Read this PoC's .env once, keeping process-provided settings authoritative."""
    try:
        lines = (BASE / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name.startswith("POC11_") and value and name not in os.environ:
            os.environ[name] = value


_load_local_env()
DATA = Path(os.environ.get("POC11_DATA_DIR", BASE / "data"))
ENDPOINT = "https://apis.data.go.kr/1140100/IntegratedGovernmentCall110/searchCounsExmp"
SOURCE = "https://www.data.go.kr/data/15141798/openapi.do"
BOARD_SOURCE = "https://counseling.go.kr/sub/notice/notice.do?boardGubun=cas"
KST = ZoneInfo("Asia/Seoul")
PAGE_SIZE = 100
API_CALL_LIMIT = 1000  # Public Data Portal development-key daily call allowance.
MAX_FILE_BYTES = 10_000_000
PART_TARGET_BYTES = 9_000_000
POLICY_REVISION = 2
REQUEST_DELAY_SECONDS = 3.2  # Stay below short-window gateway throttles.


def now() -> datetime:
    return datetime.now(KST)


def settings() -> dict:
    first = os.environ.get("POC11_START_DATE", "2019-01-01")
    date.fromisoformat(first)
    lookback = max(1, min(90, int(os.environ.get("POC11_LOOKBACK_DAYS", "7"))))
    institution = os.environ.get("POC11_INTT_CODE", "").strip()
    query = os.environ.get("POC11_QUERY", "").strip()
    return {"start_date": first, "lookback_days": lookback, "page_size": PAGE_SIZE,
            "api_call_limit": API_CALL_LIMIT, "max_download_bytes": MAX_FILE_BYTES,
            "inttCode": institution or None, "q": query or None}


def _read_json(path: Path, default: dict) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except (OSError, ValueError):
        return default


def _write_json(path: Path, value: dict) -> None:
    _atomic(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _month_end(day: date) -> date:
    next_month = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def _next_month(day: date) -> date:
    return _month_end(day) + timedelta(days=1)


def _items(payload: dict) -> tuple[list[dict], int]:
    if not isinstance(payload, dict):
        raise ValueError("API 응답은 JSON 객체여야 합니다.")
    if isinstance(payload.get("response"), dict):
        payload = payload["response"]
    header = payload.get("header") or {}
    code = str(header.get("resultCode", "")).strip()
    if code == "03":
        return [], 0
    if code not in {"00", "0"}:
        raise ValueError(f"API 결과 오류: {code or '코드 없음'} {str(header.get('resultMsg', ''))[:160]}")
    body = payload.get("body")
    if not isinstance(body, dict):
        raise ValueError("API 응답에 body가 없습니다.")
    raw = body.get("items", [])
    if isinstance(raw, dict):
        raw = raw.get("item", raw)
    if raw in (None, ""):
        raw = []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise ValueError("API items 형식이 예상과 다릅니다.")
    return raw, int(body.get("totalCount") or 0)


def fetch_page(params: dict, key: str) -> tuple[list[dict], int]:
    # The portal displays both decoded and percent-encoded keys. httpx encodes once.
    request_params = {"serviceKey": unquote(key), **params}
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            response = client.get(ENDPOINT, params=request_params, headers={"accept": "application/json"})
    except httpx.RequestError as error:
        raise ValueError(f"API 요청 실패: {type(error).__name__}") from error
    if response.status_code != 200:
        raise ValueError(f"API HTTP {response.status_code}")
    try:
        return _items(response.json())
    except (ValueError, TypeError) as error:
        raise ValueError(f"API JSON 응답을 해석하지 못했습니다: {error}") from error


def _plain_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</(?:p|div|li|tr|h[1-6])\s*>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()


def _record(raw: dict, params: dict, timestamp: str) -> dict | None:
    question = _plain_text(str(raw.get("consQustCntn") or raw.get("nobdNm") or ""))
    answer = _plain_text(str(raw.get("nobdAnsrCntn") or ""))
    if not question or not answer:
        return None
    digest = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {"id": digest[:24], "question": question, "answer": answer,
            "source_name": str(raw.get("datSourceNm") or "").strip(),
            "institution_code": str(raw.get("inttCode") or "").strip(),
            "keywords": str(raw.get("kywdNm") or "").strip(),
            "raw": raw, "request_params": dict(params), "first_collected_at": timestamp}


def _clean_markdown(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _md_inline(value: str) -> str:
    return " ".join(_clean_markdown(value).split())


def _md_quote(value: str) -> str:
    return "\n".join("> " + line if line else ">" for line in value.split("\n"))


def _answer_chunks(answer: str, limit: int = 2200) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", _clean_markdown(answer))
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        while len(paragraph) > limit:
            split = paragraph.rfind(" ", 0, limit)
            split = split if split > limit // 2 else limit
            piece, paragraph = paragraph[:split].strip(), paragraph[split:].strip()
            if current:
                chunks.append(current)
                current = ""
            chunks.append(piece)
        if paragraph:
            candidate = f"{current}\n\n{paragraph}" if current else paragraph
            if len(candidate) > limit and current:
                chunks.append(current)
                current = paragraph
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks or [""]


def render_markdown(dataset: dict) -> str:
    # Each H2 block can be split by a Markdown-aware RAG loader independently.
    source_urls = sorted({BOARD_SOURCE if r.get("raw", {}).get("source_type") == "counseling_board" else SOURCE
                          for r in dataset["records"]})
    lines = ["# 통합콜센터·정부합동민원센터 상담사례", "",
             "원천: " + " · ".join(source_urls or [SOURCE]),
             f"데이터 버전: {dataset['version']}", f"수집 사례: {len(dataset['records'])}건", "",
             "각 `##` 구간은 독립적인 검색 청크입니다. 질문과 출처를 모든 구간에 반복합니다.", ""]
    for record in dataset["records"]:
        chunks = _answer_chunks(record["answer"])
        for index, chunk in enumerate(chunks, 1):
            lines += [f"## 사례 {record['id']} · {index}/{len(chunks)}", "",
                      f"**질문:** {_md_inline(record['question'])}", "",
                      f"**기관코드:** {record['institution_code'] or '미제공'}  ",
                      f"**출처:** {_md_inline(record['source_name']) or '미제공'}  ",
                      f"**연관 키워드:** {_md_inline(record['keywords']) or '미제공'}  ",
                      f"**원문:** {record.get('raw', {}).get('source_url', SOURCE)}", "",
                      "**답변:**", "", _md_quote(chunk), "", "---", ""]
    return "\n".join(lines)


def _initial_dataset(timestamp: str, config: dict) -> dict:
    return {"schema_version": 2, "source": SOURCE, "sources": [SOURCE], "endpoint": ENDPOINT,
            "version": 0, "created_at": timestamp, "updated_at": None,
            "collection_params": config, "last_request_params": None,
            "record_count": 0, "parts": []}


def _database(folder: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(folder / "records.sqlite3")
    connection.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, payload TEXT NOT NULL, exported INTEGER NOT NULL DEFAULT 0)")
    connection.execute("CREATE INDEX IF NOT EXISTS records_exported ON records(exported)")
    return connection


def _part_path(folder: Path, name: str) -> Path:
    if not re.fullmatch(r"part-\d{6}\.(?:json|md)", name):
        raise ValueError("잘못된 분할 파일 이름입니다.")
    return folder / "parts" / name


def _manifest_markdown(manifest: dict) -> bytes:
    lines = ["# 통합콜센터·정부합동민원센터 상담사례 다운로드 목록", "",
             "원천: " + " · ".join(manifest.get("sources", [SOURCE])),
             f"데이터 버전: {manifest['version']}", f"누적 사례: {manifest['record_count']}건", "",
             "각 분할 Markdown 파일은 완전한 사례 청크를 담고 있습니다.", ""]
    for part in manifest["parts"]:
        lines.append(f"- {part['md_file']} ({part['count']}건, {part['md_bytes']}바이트)")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _publish_manifest(folder: Path, manifest: dict) -> None:
    json_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    md_bytes = _manifest_markdown(manifest)
    if max(len(json_bytes), len(md_bytes)) > MAX_FILE_BYTES:
        raise ValueError("다운로드 목록 파일이 10MB를 초과했습니다.")
    version_name = f"v{manifest['version']:06d}"
    _atomic(folder / "versions" / f"{version_name}.json", json_bytes)
    _atomic(folder / "versions" / f"{version_name}.md", md_bytes)
    _atomic(folder / "current.md", md_bytes)
    _atomic(folder / "current.json", json_bytes)


def _reconcile_records(connection: sqlite3.Connection, folder: Path, manifest: dict) -> None:
    expected = int(manifest.get("record_count", 0))
    count = connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    if count < expected:
        for part in manifest["parts"]:
            payload = _read_json(_part_path(folder, part["json_file"]), {})
            records = payload.get("records")
            if not isinstance(records, list) or len(records) != part["count"]:
                raise ValueError("분할 JSON 파일이 없거나 손상되었습니다.")
            connection.executemany("INSERT OR IGNORE INTO records(id,payload,exported) VALUES (?,?,1)",
                                   ((record["id"], json.dumps(record, ensure_ascii=False, separators=(",", ":"))) for record in records))
        connection.commit()
    # A crash after manifest publication can leave exported flags behind. Rebuild them from the published parts.
    connection.execute("UPDATE records SET exported=0")
    for part in manifest["parts"]:
        path = _part_path(folder, part["json_file"])
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("분할 JSON 파일이 없거나 10MB를 초과했습니다.")
        payload = _read_json(path, {})
        records = payload.get("records")
        if not isinstance(records, list) or len(records) != part["count"]:
            raise ValueError("분할 JSON 파일이 손상되었습니다.")
        connection.executemany("UPDATE records SET exported=1 WHERE id=?", ((record["id"],) for record in records))
    connection.commit()


def _export_records(connection: sqlite3.Connection, folder: Path, manifest: dict,
                    version: int, timestamp: str, config: dict, last_params: dict | None) -> int:
    pending = connection.execute("SELECT id,payload FROM records WHERE exported=0 ORDER BY rowid")
    parts = list(manifest["parts"])
    exported_ids: list[str] = []
    batch: list[dict] = []
    batch_ids: list[str] = []
    json_estimate = 0
    md_estimate = 0

    def flush() -> None:
        nonlocal batch, batch_ids, json_estimate, md_estimate
        if not batch:
            return
        number = len(parts) + 1
        base = f"part-{number:06d}"
        source_urls = sorted({BOARD_SOURCE if r.get("raw", {}).get("source_type") == "counseling_board" else SOURCE for r in batch})
        payload = {"schema_version": 2, "source": source_urls[0] if len(source_urls) == 1 else "mixed",
                   "sources": source_urls, "part": number,
                   "created_in_version": version, "records": batch}
        json_bytes = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        md_bytes = render_markdown({"version": version, "records": batch}).encode("utf-8")
        if max(len(json_bytes), len(md_bytes)) > MAX_FILE_BYTES:
            raise ValueError("상담사례 분할 파일이 10MB를 초과했습니다.")
        _atomic(_part_path(folder, base + ".json"), json_bytes)
        _atomic(_part_path(folder, base + ".md"), md_bytes)
        parts.append({"json_file": base + ".json", "md_file": base + ".md",
                      "count": len(batch), "json_bytes": len(json_bytes), "md_bytes": len(md_bytes)})
        exported_ids.extend(batch_ids)
        batch, batch_ids, json_estimate, md_estimate = [], [], 0, 0

    for record_id, raw_json in pending:
        record = json.loads(raw_json)
        json_size = len(raw_json.encode("utf-8")) + 1
        # Rendering one record overestimates the final Markdown size because the header is repeated.
        md_size = len(render_markdown({"version": version, "records": [record]}).encode("utf-8"))
        if max(json_size, md_size) > PART_TARGET_BYTES:
            raise ValueError("한 상담사례가 분할 파일 크기 제한을 초과했습니다.")
        if batch and (json_estimate + json_size > PART_TARGET_BYTES or
                      md_estimate + md_size > PART_TARGET_BYTES):
            flush()
        batch.append(record)
        batch_ids.append(record_id)
        json_estimate += json_size
        md_estimate += md_size
    flush()
    if not exported_ids:
        return 0
    manifest.update({"schema_version": 2, "version": version, "updated_at": timestamp,
                     "collection_params": config, "last_request_params": last_params,
                     "record_count": connection.execute("SELECT COUNT(*) FROM records").fetchone()[0],
                     "parts": parts})
    _publish_manifest(folder, manifest)
    connection.executemany("UPDATE records SET exported=1 WHERE id=?", ((record_id,) for record_id in exported_ids))
    connection.commit()
    return len(exported_ids)


def _load_manifest(connection: sqlite3.Connection, folder: Path, timestamp: str, config: dict) -> dict:
    current = _read_json(folder / "current.json", {})
    if isinstance(current.get("records"), list):
        # Upgrade the old single-file snapshot. It remains untouched until every part is written.
        legacy = current.pop("records")
        connection.executemany("INSERT OR IGNORE INTO records(id,payload) VALUES (?,?)",
                               ((record["id"], json.dumps(record, ensure_ascii=False, separators=(",", ":"))) for record in legacy))
        connection.commit()
        manifest = {"schema_version": 2, "source": current.get("source", SOURCE),
                    "endpoint": current.get("endpoint", ENDPOINT), "version": current.get("version", 1),
                    "created_at": current.get("created_at", timestamp), "updated_at": current.get("updated_at"),
                    "collection_params": current.get("collection_params", config),
                    "last_request_params": current.get("last_request_params"), "record_count": 0, "parts": []}
        _export_records(connection, folder, manifest, max(1, int(manifest["version"])),
                        current.get("updated_at") or timestamp, manifest["collection_params"],
                        manifest["last_request_params"])
        return manifest
    if current and (not isinstance(current.get("parts"), list) or current.get("schema_version") != 2):
        raise ValueError("현재 JSON 목록의 구조가 잘못되었습니다.")
    return current or _initial_dataset(timestamp, config)


def collect_once(*, key: str | None = None, today: date | None = None,
                 fetcher=None, data_dir: Path | None = None, retry: bool = False) -> dict:
    """Collect until the API call allowance is spent, checkpointing each page."""
    folder = data_dir or DATA
    folder.mkdir(parents=True, exist_ok=True)
    key = key if key is not None else os.environ.get("POC11_SERVICE_KEY", "").strip()
    config = settings()
    today = today or now().date()
    timestamp = now().isoformat(timespec="seconds")
    with (folder / ".collect.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_path = folder / "state.json"
        state = _read_json(state_path, {})
        same_day = state.get("last_attempt_date") == today.isoformat()
        prior_fetched = int(state.get("day_fetched", state.get("last_fetched", 0))) if same_day else 0
        prior_calls = int(state.get("day_api_calls", state.get("last_api_calls", 0))) if same_day else 0
        prior_added = int(state.get("today_collected", 0)) if same_day else 0
        can_retry = bool(state.get("last_error") and retry)
        key_just_added = state.get("last_error") == "POC11_SERVICE_KEY가 설정되지 않았습니다." and bool(key)
        policy_changed = state.get("policy_revision") != POLICY_REVISION
        if same_day and not (can_retry or key_just_added or policy_changed or state.get("in_progress")):
            return status(folder)
        if prior_calls >= API_CALL_LIMIT:
            return status(folder)
        if not key:
            state.update({"last_attempt_date": today.isoformat(), "last_run_at": timestamp,
                          "last_error": "POC11_SERVICE_KEY가 설정되지 않았습니다.",
                          "today_collected": prior_added, "day_fetched": prior_fetched,
                          "day_api_calls": prior_calls, "in_progress": False})
            _write_json(state_path, state)
            return status(folder)

        connection = _database(folder)
        fetched = 0
        added = 0
        calls = 0
        last_params = None
        error = None
        manifest = None
        try:
            manifest = _load_manifest(connection, folder, timestamp, config)
            _reconcile_records(connection, folder, manifest)
            start = date.fromisoformat(config["start_date"])
            if state.get("caught_up"):
                cursor = max(start, today - timedelta(days=config["lookback_days"]))
                page = 1
                cursor_end_date = None
            else:
                cursor = date.fromisoformat(state.get("cursor_date", config["start_date"]))
                page = int(state.get("cursor_page", 1))
                cursor_end_date = state.get("cursor_end_date")
            state.update({"last_attempt_date": today.isoformat(), "last_run_at": timestamp,
                          "last_error": None, "in_progress": True,
                          "policy_revision": POLICY_REVISION, "today_collected": prior_added,
                          "day_fetched": prior_fetched, "day_api_calls": prior_calls})
            _write_json(state_path, state)
            fetch = fetcher or fetch_page
            while cursor <= today and prior_calls + calls < API_CALL_LIMIT:
                end = date.fromisoformat(cursor_end_date) if page > 1 and cursor_end_date else min(_month_end(cursor), today)
                params = {"pageNo": page, "numOfRows": PAGE_SIZE,
                          "basDt": cursor.strftime("%Y%m%d"), "endDt": end.strftime("%Y%m%d")}
                if config["inttCode"]:
                    params["inttCode"] = config["inttCode"]
                if config["q"]:
                    params["q"] = config["q"]
                for attempt in range(3):
                    if prior_calls + calls >= API_CALL_LIMIT:
                        raise ValueError("오늘 API 호출 한도에 도달했습니다.")
                    if fetcher is None and prior_calls + calls:
                        clocktime.sleep(REQUEST_DELAY_SECONDS)
                    calls += 1
                    state["day_api_calls"] = prior_calls + calls
                    _write_json(state_path, state)  # An interrupted request still uses a quota call.
                    try:
                        raw_items, total = fetch(params, key)
                        break
                    except ValueError as exc:
                        if str(exc) != "API HTTP 429" or attempt == 2:
                            raise
                        clocktime.sleep(2 * (attempt + 1))
                if len(raw_items) > PAGE_SIZE:
                    raise ValueError("API가 요청한 페이지 크기보다 많은 사례를 반환했습니다.")
                last_params = params
                fetched += len(raw_items)
                for raw in raw_items:
                    item = _record(raw, params, timestamp)
                    if item:
                        result = connection.execute("INSERT OR IGNORE INTO records(id,payload) VALUES (?,?)",
                                                    (item["id"], json.dumps(item, ensure_ascii=False, separators=(",", ":"))))
                        added += result.rowcount
                connection.commit()
                if page * PAGE_SIZE >= total:
                    cursor = end + timedelta(days=1) if end < _month_end(cursor) else _next_month(cursor)
                    page = 1
                    cursor_end_date = None
                else:
                    page += 1
                    cursor_end_date = end.isoformat()
                state.update({"cursor_date": cursor.isoformat(), "cursor_page": page,
                              "caught_up": cursor > today, "day_fetched": prior_fetched + fetched,
                              "today_collected": prior_added + added,
                              "last_request_params": last_params, "last_fetched": fetched,
                              "last_api_calls": calls})
                if cursor_end_date:
                    state["cursor_end_date"] = cursor_end_date
                else:
                    state.pop("cursor_end_date", None)
                _write_json(state_path, state)
        except Exception as exc:
            error = str(exc)[:300]
            for secret in {key, unquote(key), quote(unquote(key), safe="")} - {""}:
                error = error.replace(secret, "[redacted]")
        try:
            if manifest is not None:
                published = _export_records(connection, folder, manifest,
                                            int(manifest["version"]) + 1, timestamp, config, last_params)
            else:
                published = 0
        except Exception as exc:
            error = (str(exc) or type(exc).__name__)[:300]
            published = 0
        finally:
            connection.close()
        state.update({"last_attempt_date": today.isoformat(), "last_run_at": timestamp,
                      "last_error": error, "in_progress": False,
                      "policy_revision": POLICY_REVISION,
                      "today_collected": prior_added + added,
                      "day_fetched": prior_fetched + fetched, "day_api_calls": prior_calls + calls,
                      "last_fetched": fetched, "last_api_calls": calls,
                      "last_request_params": last_params,
                      "total_collected": manifest["record_count"] if manifest else state.get("total_collected", 0),
                      "current_version": manifest["version"] if manifest else state.get("current_version", 0)})
        if not error:
            state["last_success_at"] = timestamp
        _write_json(state_path, state)
        return status(folder)



def _board_module():
    module_path = BASE / "board_collector.py"
    spec = importlib.util.spec_from_file_location("poc11_board_collector", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("게시판 수집 모듈을 불러오지 못했습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect_board_once(*, data_dir: Path | None = None, today: date | None = None,
                       force: bool = False) -> dict:
    """Collect board posts into the same records table and versioned JSON/Markdown parts."""
    folder = data_dir or DATA
    folder.mkdir(parents=True, exist_ok=True)
    today = today or now().date()
    timestamp = now().isoformat(timespec="seconds")
    state_path = folder / "board_state.json"
    with (folder / ".collect.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _read_json(state_path, {})
        same_day = state.get("last_attempt_date") == today.isoformat()
        if same_day and not force and not state.get("in_progress"):
            return status(folder)
        prior_added = int(state.get("today_collected", 0)) if same_day else 0
        seen = state.get("seen", {})
        if not isinstance(seen, dict):
            seen = {}
        state.update({"last_attempt_date": today.isoformat(), "last_run_at": timestamp,
                      "in_progress": True, "last_error": None,
                      "today_collected": prior_added, "seen": seen})
        _write_json(state_path, state)
        connection = _database(folder)
        added = 0
        inspected = 0
        errors = {}
        all_count = 0
        manifest = None
        board = _board_module()
        full_scan = not state.get("last_full_scan_date") or (
            today - date.fromisoformat(state["last_full_scan_date"])).days >= 7
        try:
            manifest = _load_manifest(connection, folder, timestamp, settings())
            _reconcile_records(connection, folder, manifest)
            with httpx.Client(timeout=40, follow_redirects=True,
                              headers={"User-Agent": "PoC11-ConsultationArchive/1.0 (public case archive)"}) as client:
                posts = board.all_posts(client)
                all_count = len(posts)
                for item in posts:
                    seq = item["board_seq"]
                    if not full_scan and seq in seen:
                        continue
                    try:
                        post, extracted, digest, method = board.fetch_post(client, item, folder)
                        fingerprint = digest or hashlib.sha256(post["body"].encode("utf-8")).hexdigest()
                        if seen.get(seq) != fingerprint:
                            for record in board.records_for_post(post, extracted, digest, method, timestamp):
                                result = connection.execute(
                                    "INSERT OR IGNORE INTO records(id,payload) VALUES (?,?)",
                                    (record["id"], json.dumps(record, ensure_ascii=False, separators=(",", ":"))))
                                added += result.rowcount
                            connection.commit()
                        seen[seq] = fingerprint
                        inspected += 1
                        state.update({"today_collected": prior_added + added,
                                      "last_inspected": inspected, "last_post_count": all_count})
                        _write_json(state_path, state)
                    except Exception as exc:
                        errors[seq] = f"{type(exc).__name__}: {str(exc)[:160]}"
        except Exception as exc:
            errors["board"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        try:
            if manifest is not None:
                manifest["sources"] = sorted(set(manifest.get("sources", [SOURCE])) | {BOARD_SOURCE})
                manifest["board_collection_params"] = {"boardGubun": "cas", "schedule": "03:00 Asia/Seoul",
                                                       "full_scan_days": 7}
                _export_records(connection, folder, manifest, int(manifest["version"]) + 1,
                                timestamp, manifest.get("collection_params", settings()),
                                manifest.get("last_request_params"))
            board_total = connection.execute(
                "SELECT COUNT(*) FROM records WHERE json_extract(payload, '$.raw.source_type') = 'counseling_board'").fetchone()[0]
        except Exception as exc:
            errors["export"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            board_total = int(state.get("total_collected", 0))
        finally:
            connection.close()
        state.update({"in_progress": False, "today_collected": prior_added + added,
                      "last_inspected": inspected, "last_post_count": all_count,
                      "total_collected": board_total, "errors": errors,
                      "last_error": f"{len(errors)}개 게시글 처리 실패" if errors else None})
        if not errors:
            state["last_success_at"] = timestamp
        if full_scan and "board" not in errors:
            state["last_full_scan_date"] = today.isoformat()
        _write_json(state_path, state)
        return status(folder)


def status(data_dir: Path | None = None) -> dict:
    folder = data_dir or DATA
    state = _read_json(folder / "state.json", {})
    board_state = _read_json(folder / "board_state.json", {})
    manifest = _read_json(folder / "current.json", {})
    today = now().date().isoformat()
    parts = manifest.get("parts", [])
    if not isinstance(parts, list):
        parts = []
    downloads = [{"json_file": part["json_file"], "md_file": part["md_file"],
                  "count": part["count"], "json_bytes": part["json_bytes"],
                  "md_bytes": part["md_bytes"]} for part in parts]
    total = manifest.get("record_count", len(manifest.get("records", [])))
    board_total = board_state.get("total_collected", 0)
    api_today = state.get("today_collected", 0) if state.get("last_attempt_date") == today else 0
    board_today = board_state.get("today_collected", 0) if board_state.get("last_attempt_date") == today else 0
    return {"total_collected": total, "today_collected": api_today + board_today,
            "api_collected": max(0, total - board_total), "board_collected": board_total,
            "api_today_collected": api_today, "board_today_collected": board_today,
            "board_last_run_at": board_state.get("last_run_at"),
            "board_last_success_at": board_state.get("last_success_at"),
            "board_last_error": board_state.get("last_error"),
            "board_last_post_count": board_state.get("last_post_count", 0),
            "board_last_inspected": board_state.get("last_inspected", 0),
            "board_collecting": bool(board_state.get("in_progress")),
            "current_version": manifest.get("version"), "updated_at": manifest.get("updated_at"),
            "last_run_at": state.get("last_run_at"), "last_success_at": state.get("last_success_at"),
            "last_error": state.get("last_error"), "last_fetched": state.get("last_fetched", 0),
            "last_api_calls": state.get("last_api_calls", 0),
            "today_api_calls": state.get("day_api_calls", 0) if state.get("last_attempt_date") == today else 0,
            "api_call_limit": API_CALL_LIMIT, "max_download_bytes": MAX_FILE_BYTES,
            "collecting": bool(state.get("in_progress")),
            "caught_up": bool(state.get("caught_up")), "cursor_date": state.get("cursor_date"),
            "next_run": "매일 03:00 Asia/Seoul", "key_configured": bool(os.environ.get("POC11_SERVICE_KEY")),
            "source": SOURCE, "board_source": BOARD_SOURCE, "parts": downloads,
            "has_downloads": (folder / "current.json").is_file() and (folder / "current.md").is_file()}


async def scheduler_loop() -> None:
    while True:
        current = now()
        target = datetime.combine(current.date(), time(3, 0), KST)
        if current < target:
            await asyncio.sleep((target - current).total_seconds())
            current = now()
        api_state = _read_json(DATA / "state.json", {})
        board_state = _read_json(DATA / "board_state.json", {})
        day = current.date().isoformat()
        can_retry_key = (api_state.get("last_error") == "POC11_SERVICE_KEY가 설정되지 않았습니다."
                         and bool(os.environ.get("POC11_SERVICE_KEY")))
        api_due = (api_state.get("last_attempt_date") != day or can_retry_key or
                   api_state.get("policy_revision") != POLICY_REVISION or api_state.get("in_progress"))
        board_due = board_state.get("last_attempt_date") != day or board_state.get("in_progress")
        if not api_due and not board_due:
            next_target = datetime.combine(current.date() + timedelta(days=1), time(3, 0), KST)
            await asyncio.sleep((next_target - current).total_seconds())
            continue
        if api_due:
            try:
                await asyncio.to_thread(collect_once)
            except Exception as exc:
                print(f"PoC 11 API collection failed: {type(exc).__name__}: {str(exc)[:200]}")
        if board_due:
            try:
                await asyncio.to_thread(collect_board_once)
            except Exception as exc:
                print(f"PoC 11 board collection failed: {type(exc).__name__}: {str(exc)[:200]}")
        await asyncio.sleep(1)


async def handle_http(scope, receive, send, *, is_admin: bool = False) -> None:
    path = scope.get("path", "")
    method = scope.get("method", "GET").upper()
    prefix = "/poc/consultation-cases"

    async def reply(code: int, content: bytes, content_type: str, filename: str = "") -> None:
        headers = [(b"content-type", content_type.encode("ascii")),
                   (b"content-length", str(len(content)).encode("ascii")),
                   (b"cache-control", b"no-store"),
                   (b"x-content-type-options", b"nosniff")]
        if filename:
            headers.append((b"content-disposition", f'attachment; filename="{filename}"'.encode("ascii")))
        await send({"type": "http.response.start", "status": code, "headers": headers})
        await send({"type": "http.response.body", "body": b"" if method == "HEAD" else content})

    if method not in {"GET", "HEAD", "POST"}:
        return await reply(405, b"Method not allowed", "text/plain; charset=utf-8")
    if method == "POST" and path == prefix + "/api/collect":
        if not is_admin:
            return await reply(401, b'{"detail":"administrator login required"}', "application/json; charset=utf-8")
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
        from urllib.parse import urlparse
        origin = urlparse(headers.get("origin", ""))
        if origin.scheme not in {"http", "https"} or origin.netloc != headers.get("host"):
            return await reply(403, b'{"detail":"same origin required"}', "application/json; charset=utf-8")
        result = await asyncio.to_thread(collect_once, retry=True)
        return await reply(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
    if method == "POST":
        return await reply(405, b"Method not allowed", "text/plain; charset=utf-8")
    if path in {prefix, prefix + "/"}:
        return await reply(200, (BASE / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
    if path == prefix + "/api/status":
        data = status()
        data["can_collect"] = is_admin
        return await reply(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
    if path in {prefix + "/download/current.json", prefix + "/download/current.md"}:
        extension = path.rsplit(".", 1)[1]
        target = DATA / f"current.{extension}"
        if not target.is_file():
            return await reply(404, b"No collected version yet", "text/plain; charset=utf-8")
        if target.stat().st_size > MAX_FILE_BYTES:
            return await reply(409, b"File exceeds 10 MB", "text/plain; charset=utf-8")
        mime = "application/json; charset=utf-8" if extension == "json" else "text/markdown; charset=utf-8"
        return await reply(200, target.read_bytes(), mime, f"poc11-current.{extension}")
    if path.startswith(prefix + "/download/parts/"):
        name = path.removeprefix(prefix + "/download/parts/")
        if not re.fullmatch(r"part-\d{6}\.(?:json|md)", name):
            return await reply(404, b"Not found", "text/plain; charset=utf-8")
        manifest = _read_json(DATA / "current.json", {})
        allowed = {part.get("json_file") for part in manifest.get("parts", [])} | {part.get("md_file") for part in manifest.get("parts", [])}
        if name not in allowed:
            return await reply(404, b"Not found", "text/plain; charset=utf-8")
        target = _part_path(DATA, name)
        if not target.is_file():
            return await reply(404, b"Not found", "text/plain; charset=utf-8")
        if target.stat().st_size > MAX_FILE_BYTES:
            return await reply(409, b"File exceeds 10 MB", "text/plain; charset=utf-8")
        mime = "application/json; charset=utf-8" if name.endswith(".json") else "text/markdown; charset=utf-8"
        return await reply(200, target.read_bytes(), mime, f"poc11-{name}")
    return await reply(404, b"Not found", "text/plain; charset=utf-8")
