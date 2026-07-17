from __future__ import annotations

import threading
import urllib.parse
from datetime import datetime, timedelta

from .collectors import NewsCollector, quick_candidate_match
from .config import Settings
from .kakao import KakaoClient
from .scoring import RelevanceEngine
from .storage import KST, Store, now_iso
from .supabase_mirror import SupabaseMirror


RUN_LOCK = threading.Lock()


def parse_clock(value: str) -> tuple[int, int] | None:
    try:
        hour_text, minute_text = str(value).strip().split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (ValueError, TypeError):
        pass
    return None


def next_time_slot(values: list[str], now: datetime | None = None) -> datetime:
    current = now or datetime.now(KST)
    slots = [slot for value in values if (slot := parse_clock(value))]
    if not slots:
        return current
    candidates = [current.replace(hour=hour, minute=minute, second=0, microsecond=0) for hour, minute in slots]
    future = [candidate for candidate in candidates if candidate > current]
    return min(future) if future else min(candidates) + timedelta(days=1)


def next_collection_at(case: dict, now: datetime | None = None) -> str:
    current = now or datetime.now(KST)
    if case.get("collection_mode") == "times":
        return next_time_slot(case.get("collection_times", []), current).isoformat(timespec="seconds")
    minutes = max(5, int(case.get("collection_interval_minutes", 30)))
    return (current + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def delivery_at(case: dict, urgent: bool, now: datetime | None = None) -> str:
    current = now or datetime.now(KST)
    if urgent or case.get("delivery_mode") == "immediate":
        return current.isoformat(timespec="seconds")
    return next_time_slot(case.get("delivery_times", []), current).isoformat(timespec="seconds")


def publisher_allowed(case: dict, publisher: str) -> bool:
    target = str(publisher or "").casefold()
    included = [str(value).casefold() for value in case.get("include_publishers", []) if str(value).strip()]
    excluded = [str(value).casefold() for value in case.get("exclude_publishers", []) if str(value).strip()]
    if excluded and any(value in target for value in excluded):
        return False
    return not included or any(value in target for value in included)


class MasterPressService:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store
        self.collector = NewsCollector(settings)
        self.scoring = RelevanceEngine(settings)
        self.mirror = SupabaseMirror(settings)
        self.kakao = KakaoClient(settings, store)

    def run_case(self, case_id: str) -> dict:
        case = self.store.get_case(case_id)
        if not case:
            raise ValueError("케이스를 찾지 못했습니다.")
        if not RUN_LOCK.acquire(blocking=False):
            raise RuntimeError("다른 마스터언론 수집 작업이 진행 중입니다.")
        run_id = self.store.start_run(case_id)
        counts = {"collected": 0, "new": 0, "scored": 0, "queued": 0, "skipped": 0}
        errors: list[str] = []
        try:
            candidates = self.collector.collect(case)
            counts["collected"] = len(candidates)
            selected = []
            for candidate in candidates:
                if not publisher_allowed(case, candidate.get("publisher", "")):
                    counts["skipped"] += 1
                    continue
                if not quick_candidate_match(case, candidate):
                    counts["skipped"] += 1
                    continue
                selected.append(candidate)
                if len(selected) >= self.settings.per_run_article_limit:
                    break

            for candidate in selected:
                try:
                    article, created = self.store.upsert_article(candidate)
                    counts["new"] += int(created)
                    if self.store.score_exists(article["id"], case_id):
                        counts["skipped"] += 1
                        continue
                    fetched = self.collector.fetch_body(article["original_url"])
                    candidate.update(fetched)
                    article, _created = self.store.upsert_article(candidate)
                    result = self.scoring.evaluate(case, article)
                    saved_score = self.store.save_score(article["id"], case_id, int(case.get("version", 1)), result)
                    self.mirror.article_score(article, saved_score)
                    counts["scored"] += 1
                    if result["decision"] == "send":
                        scheduled = delivery_at(case, result.get("urgent", False))
                        for recipient_id in self.store.case_recipient_ids(case_id):
                            self.store.queue_delivery(article["id"], case_id, recipient_id, scheduled)
                            counts["queued"] += 1
                except Exception as error:
                    errors.append(f"{candidate.get('title', '기사')[:80]}: {error}")
            self.store.set_case_schedule(case_id, next_collection_at(case), collected=True)
            self.mirror.case(self.store.get_case(case_id) or case)
            self.store.finish_run(run_id, "completed_with_errors" if errors else "completed", counts, "\n".join(errors))
            return {"run_id": run_id, "case_id": case_id, "counts": counts, "errors": errors}
        except Exception as error:
            self.store.set_case_schedule(case_id, next_collection_at(case), collected=False)
            self.store.finish_run(run_id, "failed", counts, str(error))
            raise
        finally:
            RUN_LOCK.release()

    @staticmethod
    def message_text(delivery: dict) -> str:
        case_name = str(delivery.get("case_name") or "마스터언론")[:20]
        title = str(delivery.get("title") or "")[:70]
        summary = str(delivery.get("summary") or "")[:85]
        text = f"[{case_name}] 관련도 {float(delivery.get('final_score') or 0):.0f}%\n{title}\n\n{summary}"
        return text[:200]

    def article_link(self, article_id: str, fallback: str) -> str:
        redirect = urllib.parse.urlsplit(self.settings.kakao_redirect_uri)
        if redirect.scheme in {"http", "https"} and redirect.netloc:
            article_id = urllib.parse.quote(str(article_id), safe="")
            return f"{redirect.scheme}://{redirect.netloc}/poc/master-press/article/{article_id}"
        return fallback

    def send_due(self, limit: int = 20) -> dict:
        sent = failed = 0
        errors = []
        for delivery in self.store.due_deliveries(limit):
            try:
                status, _response = self.kakao.send_to_me(
                    delivery["recipient_id"],
                    self.message_text(delivery),
                    self.article_link(delivery["article_id"], delivery["original_url"]),
                )
                self.store.finish_delivery(delivery["id"], True, status)
                sent += 1
            except Exception as error:
                code = int(getattr(error, "status", 502))
                self.store.finish_delivery(delivery["id"], False, code, str(error))
                failed += 1
                errors.append(str(error))
        return {"sent": sent, "failed": failed, "errors": errors}

    def tick(self) -> dict:
        results = {"cases": [], "delivery": {}, "cleanup": {}}
        for case in self.store.list_due_cases():
            try:
                results["cases"].append(self.run_case(case["id"]))
            except RuntimeError as error:
                results["cases"].append({"case_id": case["id"], "error": str(error)})
                break
            except Exception as error:
                results["cases"].append({"case_id": case["id"], "error": str(error)})
        results["delivery"] = self.send_due()
        now = datetime.now(KST)
        if now.hour == 3 and now.minute < 2:
            results["cleanup"] = self.store.cleanup(self.settings.raw_retention_days, self.settings.metadata_retention_days)
        return results


_SERVICE: MasterPressService | None = None
_SERVICE_KEY: tuple | None = None


def get_service() -> MasterPressService:
    global _SERVICE, _SERVICE_KEY
    settings = Settings.from_env()
    settings.ensure_directories()
    key = (str(settings.database_path), settings.naver_client_id, settings.kakao_redirect_uri, settings.llm_model, settings.embedding_model)
    if _SERVICE is None or _SERVICE_KEY != key:
        _SERVICE = MasterPressService(settings, Store(settings.database_path))
        _SERVICE_KEY = key
    return _SERVICE


def worker_tick() -> dict:
    return get_service().tick()
