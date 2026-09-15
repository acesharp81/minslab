from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterable
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings


logger = logging.getLogger(__name__)

JSON_COLUMNS = {
    "raw_payload_json",
    "result_json",
    "possible_functions_json",
    "key_evidence_json",
    "check_questions_json",
    "caveats_json",
    "stats_json",
    "detail_json",
}
JSON_OBJECT_COLUMNS = {"raw_payload_json", "result_json", "stats_json", "detail_json"}
DATETIME_COLUMNS = {
    "posted_at",
    "deadline_at",
    "contacted_at",
    "created_at",
    "updated_at",
    "started_at",
    "finished_at",
}


class SupabaseStoreError(RuntimeError):
    pass


def model_tables() -> dict[type, str]:
    from ..models import ActionItem, AnalysisRun, Attachment, AuditLog, Notice, NoticeDecision, PipelineRun

    return {
        Notice: "poc08_notices",
        Attachment: "poc08_attachments",
        AnalysisRun: "poc08_analysis_runs",
        NoticeDecision: "poc08_notice_decisions",
        ActionItem: "poc08_action_items",
        PipelineRun: "poc08_pipeline_runs",
        AuditLog: "poc08_audit_logs",
    }


def sync_order() -> list[tuple[type, str]]:
    tables = model_tables()
    return list(tables.items())


def serialize_model(instance: Any) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for column in instance.__table__.columns:
        value = getattr(instance, column.name)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            value = value.isoformat()
        elif column.name in JSON_COLUMNS and isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = {} if column.name in JSON_OBJECT_COLUMNS else []
        row[column.name] = value
    return row


def deserialize_row(model: type, row: dict[str, Any]) -> dict[str, Any]:
    allowed = {column.name for column in model.__table__.columns}
    values: dict[str, Any] = {}
    for name, value in row.items():
        if name not in allowed:
            continue
        if name in JSON_COLUMNS and not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False, default=str)
        elif name in DATETIME_COLUMNS and isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                value = None
        values[name] = value
    return values


class SupabaseRestStore:
    """기존 SUPABASE2 URL/service-role 패턴을 사용하는 서버 전용 저장소."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_error = ""
        self.last_status = 0

    @property
    def enabled(self) -> bool:
        return self.settings.supabase_enabled

    @property
    def rest_url(self) -> str:
        base = self.settings.supabase_url.rstrip("/")
        return base if base.endswith("/rest/v1") else f"{base}/rest/v1"

    def _headers(self, prefer: str = "") -> dict[str, str]:
        headers = {
            "apikey": self.settings.supabase_service_role_key,
            "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    @staticmethod
    def _safe_error(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        detail = {
            "status": response.status_code,
            "code": str(body.get("code") or "")[:80],
            "message": str(body.get("message") or response.reason_phrase or "")[:500],
            "hint": str(body.get("hint") or "")[:300],
        }
        return json.dumps({key: value for key, value in detail.items() if value not in (None, "")}, ensure_ascii=False)

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Any = None,
        prefer: str = "",
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        if not self.enabled:
            raise SupabaseStoreError("Supabase REST가 설정되지 않았습니다.")
        headers = self._headers(prefer)
        headers.update(extra_headers or {})
        try:
            with httpx.Client(timeout=self.settings.supabase_timeout_seconds) as client:
                response = client.request(method, f"{self.rest_url}/{path}", headers=headers, json=payload)
            self.last_status = response.status_code
            if response.status_code >= 400:
                self.last_error = self._safe_error(response)
                raise SupabaseStoreError(f"Supabase REST 오류: {self.last_error}")
            self.last_error = ""
            return response.json() if response.content else None
        except httpx.RequestError as exc:
            self.last_status = 0
            self.last_error = type(exc).__name__
            raise SupabaseStoreError(f"Supabase REST 연결 실패: {type(exc).__name__}") from None

    def health(self) -> bool:
        if not self.enabled:
            return False
        try:
            self.request("GET", "poc08_notices?select=id&limit=1")
            return True
        except SupabaseStoreError:
            return False

    def fetch_all(self, table: str) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        page_size = 1_000
        for offset in range(0, 1_000_000, page_size):
            rows = self.request(
                "GET",
                f"{table}?select=*&order=id.asc",
                extra_headers={"Range": f"{offset}-{offset + page_size - 1}"},
            ) or []
            page = [dict(row) for row in rows if isinstance(row, dict)]
            collected.extend(page)
            if len(page) < page_size:
                break
        return collected

    def upsert(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        for offset in range(0, len(rows), 250):
            chunk = rows[offset:offset + 250]
            query = urlencode({"on_conflict": "id"})
            self.request(
                "POST",
                f"{table}?{query}",
                payload=chunk,
                prefer="resolution=merge-duplicates,return=minimal",
            )

    def delete_ids(self, table: str, ids: Iterable[int]) -> None:
        values = sorted({int(value) for value in ids})
        if not values:
            return
        joined = ",".join(str(value) for value in values)
        self.request("DELETE", f"{table}?id=in.({joined})", prefer="return=minimal")

    def push_changes(self, upserts: Iterable[Any], deletes: Iterable[Any]) -> bool:
        if not self.enabled:
            return False
        grouped_upserts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        grouped_deletes: dict[str, list[int]] = defaultdict(list)
        tables = model_tables()
        for instance in upserts:
            table = tables.get(type(instance))
            if table and getattr(instance, "id", None) is not None:
                grouped_upserts[table].append(serialize_model(instance))
        for instance in deletes:
            table = tables.get(type(instance))
            if table and getattr(instance, "id", None) is not None:
                grouped_deletes[table].append(int(instance.id))
        try:
            for _model, table in sync_order():
                self.upsert(table, grouped_upserts.get(table, []))
            for model, table in reversed(sync_order()):
                del model
                self.delete_ids(table, grouped_deletes.get(table, []))
            return True
        except SupabaseStoreError:
            logger.exception("Supabase 동기화 실패; 로컬 캐시에 보존합니다.")
            return False

    def push_all(self, db: Session) -> bool:
        """현재 로컬 캐시 전체를 테이블 순서대로 일괄 upsert한다."""
        if not self.enabled:
            return False
        try:
            for model, table in sync_order():
                rows = [serialize_model(item) for item in db.scalars(select(model)).all()]
                self.upsert(table, rows)
            return True
        except SupabaseStoreError:
            logger.exception("Supabase 일괄 동기화 실패; 로컬 캐시에 보존합니다.")
            return False

    def reconcile(self, db: Session) -> bool:
        """원격 우선 병합 후 로컬에만 남은 레코드를 다시 전송한다."""
        if not self.enabled:
            return False
        try:
            db.info["suppress_supabase_sync"] = True
            for model, table in sync_order():
                for remote in self.fetch_all(table):
                    values = deserialize_row(model, remote)
                    identity = values.get("id")
                    if identity is None:
                        continue
                    instance = db.get(model, identity)
                    if instance is None:
                        db.add(model(**values))
                    else:
                        for name, value in values.items():
                            setattr(instance, name, value)
            db.commit()
            return self.push_all(db)
        except Exception:
            db.rollback()
            logger.exception("Supabase 시작 동기화 실패; 로컬 캐시로 계속합니다.")
            return False
        finally:
            db.info.pop("suppress_supabase_sync", None)


@lru_cache(maxsize=1)
def get_supabase_store() -> SupabaseRestStore:
    return SupabaseRestStore(get_settings())
