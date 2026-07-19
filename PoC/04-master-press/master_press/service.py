from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from datetime import datetime, timedelta

from .collectors import NewsCollector, organization_candidate_match, quick_candidate_match
from .config import Settings
from .kakao import KakaoClient
from .press_releases import PressReleaseManager
from .scoring import OpenRouterError, RelevanceEngine
from .storage import KST, Store, now_iso
from .supabase_mirror import SupabaseMirror


COLLECTION_LOCK = threading.Lock()
LOCAL_LLM_LOCK = threading.Lock()
REMOTE_CASE_SEMAPHORE = threading.BoundedSemaphore(2)
DELIVERY_LOCK = threading.Lock()


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
    minutes = max(1, int(case.get("collection_interval_minutes", 30)))
    return (current + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def delivery_at(case: dict, urgent: bool, now: datetime | None = None) -> str:
    current = now or datetime.now(KST)
    if urgent or case.get("send_relevant_immediately", True) or case.get("delivery_mode") == "immediate":
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
        self.scoring = RelevanceEngine(settings, store)
        self.mirror = SupabaseMirror(settings)
        self.press_releases = PressReleaseManager(settings, store, self.scoring.ollama, self.mirror)
        self.kakao = KakaoClient(settings, store)
        self.recovered_llm_jobs = self.store.activate_worker_session(str(os.getpid()))

    def selected_llm_model(self) -> str:
        return self.store.get_setting("llm_model", getattr(getattr(self, "settings", None), "llm_model", ""))

    def selected_case_llm_model(self) -> str:
        return self.store.get_setting("case_llm_model", getattr(getattr(self, "settings", None), "openrouter_case_model", ""))

    def available_case_llm_models(self) -> list[str]:
        try:
            return self.scoring.case_llm.models()
        except Exception:
            return [self.selected_case_llm_model()] if self.selected_case_llm_model() else []

    def openrouter_status(self, probe: bool = False) -> dict:
        usage = self.store.openrouter_usage_today(self.settings.openrouter_daily_soft_limit)
        status = self.scoring.case_llm.key_status() if probe else {"connected": bool(self.settings.openrouter_api_key)}
        return {**status, **usage, "model": self.selected_case_llm_model(), "provider": "openrouter"}

    def pipeline_provider_status(self) -> dict:
        return {"common": {"provider": "ollama", "model": self.selected_llm_model(), "concurrency": 1},
                "case": {**self.openrouter_status(False), "concurrency": 1, "burst_concurrency": 2, "burst_threshold": 10}}

    def analysis_case(self, case: dict) -> tuple[dict, dict | None]:
        organization = self.store.get_organization(str(case.get("organization_id"))) if case.get("organization_id") else None
        values = [str((organization or {}).get("name") or "")]
        for key in ("abbreviations", "former_names", "people"):
            values.extend(str(value) for value in (organization or {}).get(key, []) if str(value).strip())
        enriched = dict(case)
        enriched["organization_terms"] = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        return enriched, organization

    def recipients_with_connection_status(self) -> list[dict]:
        recipients = self.store.list_recipients()
        for recipient in recipients:
            checked = self.kakao.connection_status(recipient["id"])
            recipient["connection_status"] = "connected" if checked["connected"] else "failed"
            recipient["connection_label"] = checked["label"]
            recipient["connection_error"] = checked["error"]
        return recipients

    def available_llm_models(self) -> list[str]:
        try:
            return self.scoring.ollama.models()
        except Exception:
            return []

    def analysis_report(self, article_id: str, case_id: str) -> dict:
        report = self.store.analysis_report(article_id, case_id)
        article, case = self.store.get_article(article_id), self.store.get_case(case_id)
        if not article or not case:
            return report
        evaluation_case, _organization = self.analysis_case(case)
        current = dict(report.get("current") or {})
        system_prompt, user_prompt, input_content = self.scoring.ollama.build_analysis_prompts(evaluation_case, article)
        if not current.get("user_prompt"):
            current.update({
                "system_prompt": system_prompt, "user_prompt": user_prompt, "prompt": user_prompt,
                "input_content": input_content, "reconstructed": True,
            })
        else:
            current.setdefault("input_content", input_content)
        report["current"] = current
        return report

    def process_next_reanalysis(self) -> dict | None:
        if not LOCAL_LLM_LOCK.acquire(blocking=False):
            return None
        try:
            job = self.store.next_reanalysis_job()
            if not job:
                return None
            article, case = self.store.get_article(job["article_id"]), self.store.get_case(job["case_id"])
            if not article or not case:
                self.store.finish_reanalysis(job["id"], None, 0, "article_or_case_missing")
                return {"id": job["id"], "status": "failed"}
            started = time.monotonic()
            self.store.start_reanalysis(job["id"])
            try:
                evaluation_case, organization = self.analysis_case(case)
                result = self.scoring.evaluate(evaluation_case, article, job["model"])
                result["organization_tag"] = str((organization or {}).get("name") or "")
                self.store.finish_reanalysis(job["id"], result, round((time.monotonic() - started) * 1000))
                return {"id": job["id"], "status": "completed", "decision": result.get("decision")}
            except Exception as error:
                self.store.finish_reanalysis(job["id"], None, round((time.monotonic() - started) * 1000), str(error))
                return {"id": job["id"], "status": "failed", "error": str(error)}
        finally:
            LOCAL_LLM_LOCK.release()

    def _route_article_analysis(self, analysis: dict, article: dict, organization_id: str | None) -> dict:
        """Create independent case rows after the shared article analysis is complete."""
        cases = self.store.list_cases_for_organization(organization_id, active_only=True) if organization_id else []
        counts = {"case_candidates": 0, "case_excluded": 0, "case_queued": 0}
        for case in cases:
            candidate = publisher_allowed(case, article.get("publisher", "")) and quick_candidate_match(case, article)
            evaluation, created = self.store.create_case_evaluation(analysis["id"], article["id"], case, candidate)
            if candidate:
                counts["case_candidates"] += int(created)
                if created and self.store.queue_case_evaluation(evaluation["id"]):
                    counts["case_queued"] += 1
            else:
                counts["case_excluded"] += int(created)
        return counts

    def _embed_article_analysis(self, analysis: dict, article: dict) -> bool:
        embedding_model = str(getattr(getattr(self, "settings", None), "embedding_model", ""))
        if not embedding_model or not getattr(getattr(self, "scoring", None), "ollama", None):
            return False
        text = " ".join([
            str(article.get("title") or ""), str(analysis.get("summary") or ""),
            " ".join(str(value) for value in analysis.get("classification_tags", [])),
            str(article.get("body") or "")[:5000],
        ]).strip()
        if not text:
            self.store.save_article_embedding(analysis["id"], embedding_model, [], "article_text_missing")
            return False
        try:
            vectors = self.scoring.ollama.embeddings([f"search_document: {text}"])
            vector = vectors[0] if vectors else []
            if not vector:
                raise ValueError("embedding_empty")
            self.store.save_article_embedding(analysis["id"], embedding_model, vector)
            self.press_releases.queue_for_article(analysis["id"])
            return True
        except Exception as error:
            self.store.save_article_embedding(analysis["id"], embedding_model, [], type(error).__name__)
            return False

    def process_next_embedding(self) -> dict | None:
        """Backfill one historical article only when no LLM analysis work is waiting."""
        if not LOCAL_LLM_LOCK.acquire(blocking=False):
            return None
        try:
            analysis = self.store.next_embedding_analysis()
            if not analysis:
                return None
            article = self.store.get_article(analysis["article_id"])
            if not article:
                return None
            return {"analysis_id": analysis["id"], "embedded": self._embed_article_analysis(analysis, article)}
        finally:
            LOCAL_LLM_LOCK.release()

    def process_next_article_analysis(self) -> dict | None:
        if not LOCAL_LLM_LOCK.acquire(blocking=False):
            return None
        try:
            job = self.store.next_article_analysis_job()
            if not job or not self.store.start_article_analysis_job(job["id"]):
                return None
            analysis = self.store.get_article_analysis(job["article_analysis_id"])
            article = self.store.get_article(analysis["article_id"]) if analysis else None
            if not analysis or not article:
                self.store.finish_article_analysis_job(job["id"], False, 0, "article_or_analysis_missing")
                return {"id": job["id"], "status": "failed"}
            started = time.monotonic()
            try:
                fallback = False
                try:
                    result = self.scoring.analyze_article_common(article, self.selected_llm_model())
                except json.JSONDecodeError as error:
                    # Preserve pipeline flow when a small local model finishes with malformed JSON.
                    result = self.scoring.fallback_article_common(article, self.selected_llm_model(), str(error))
                    fallback = True
                saved = self.store.save_article_analysis(analysis["id"], result, self.selected_llm_model())
                embedded = self._embed_article_analysis(saved, article)
                self.store.finish_article_analysis_job(job["id"], True, round((time.monotonic() - started) * 1000))
                routed = self._route_article_analysis(saved, article, job.get("organization_id") or analysis.get("organization_id"))
                routed["embedded"] = int(embedded)
                routed["fallback"] = int(fallback)
                return {"id": job["id"], "status": "completed", "stage": "article", "counts": routed}
            except Exception as error:
                self.store.finish_article_analysis_job(job["id"], False, round((time.monotonic() - started) * 1000), str(error))
                return {"id": job["id"], "status": "failed", "stage": "article", "error": str(error)}
        finally:
            LOCAL_LLM_LOCK.release()

    def process_next_case_evaluation(self) -> dict | None:
        if not REMOTE_CASE_SEMAPHORE.acquire(blocking=False):
            return None
        try:
            job = self.store.next_case_evaluation_job()
            if not job or not self.store.start_case_evaluation_job(job["id"], "openrouter"):
                return None
            evaluation = self.store.get_case_evaluation(job["case_evaluation_id"])
            article = self.store.get_article(evaluation["article_id"]) if evaluation else None
            case = self.store.get_case(evaluation["case_id"]) if evaluation else None
            analysis = self.store.get_article_analysis(evaluation["article_analysis_id"]) if evaluation else None
            if not evaluation or not article or not case or not analysis or not case.get("is_active"):
                self.store.finish_case_evaluation_job(job["id"], False, 0, "article_case_or_common_analysis_missing")
                return {"id": job["id"], "status": "failed", "stage": "case"}
            started = time.monotonic()
            try:
                evaluation_case, _organization = self.analysis_case(case)
                case_model = self.selected_case_llm_model()
                result = self.scoring.evaluate_case_with_common(evaluation_case, article, analysis, case_model)
                saved = self.store.save_case_evaluation(evaluation["id"], result, case_model)
                self.store.finish_case_evaluation_job(job["id"], True, round((time.monotonic() - started) * 1000))
                counts = {"scored": 1, "queued": 0, "sent": 0, "delivery_failed": 0}
                if saved.get("decision") == "send":
                    scheduled = delivery_at(case, result.get("urgent", False))
                    recipient_ids = self.store.case_recipient_ids(case["id"])
                    for recipient_id in recipient_ids:
                        self.store.queue_delivery(article["id"], case["id"], recipient_id, scheduled)
                        counts["queued"] += 1
                    immediate = result.get("urgent", False) or case.get("send_relevant_immediately", True) or case.get("delivery_mode") == "immediate"
                    if recipient_ids and immediate:
                        sent = self.send_due(max(20, len(recipient_ids)))
                        counts["sent"], counts["delivery_failed"] = sent["sent"], sent["failed"]
                return {"id": job["id"], "status": "completed", "stage": "case", "counts": counts}
            except OpenRouterError as error:
                self.store.finish_case_evaluation_job(job["id"], False, round((time.monotonic() - started) * 1000), str(error), retryable=error.retryable, retry_after=error.retry_after, keep_pending=error.deferred)
                return {"id": job["id"], "status": "pending" if error.retryable else "failed", "stage": "case", "provider": "openrouter", "http_status": error.status, "error": str(error)}
            except Exception as error:
                self.store.finish_case_evaluation_job(job["id"], False, round((time.monotonic() - started) * 1000), str(error))
                return {"id": job["id"], "status": "failed", "stage": "case", "provider": "openrouter", "error": str(error)}
        finally:
            REMOTE_CASE_SEMAPHORE.release()

    def _evaluate_queued(self, job_id: str, case: dict, article: dict, counts: dict) -> bool:
        started = time.monotonic()
        if not self.store.start_llm_job(job_id):
            return False
        try:
            evaluation_case, organization = self.analysis_case(case)
            try:
                result = self.scoring.evaluate(evaluation_case, article, self.selected_llm_model())
            except TypeError:
                result = self.scoring.evaluate(evaluation_case, article)
            result["organization_tag"] = str((organization or {}).get("name") or "")
            duration_ms = round((time.monotonic() - started) * 1000)
            llm_error = str(result.get("llm_error") or "")
            self.store.finish_llm_job(job_id, not llm_error, duration_ms, llm_error)
            saved_score = self.store.save_score(article["id"], case["id"], int(case.get("version", 1)), result)
            self.mirror.article_score(article, saved_score)
            counts["scored"] += 1
            if result["decision"] != "send":
                return True
            scheduled = delivery_at(case, result.get("urgent", False))
            recipient_ids = self.store.case_recipient_ids(case["id"])
            for recipient_id in recipient_ids:
                self.store.queue_delivery(article["id"], case["id"], recipient_id, scheduled)
                counts["queued"] += 1
            immediate = result.get("urgent", False) or case.get("send_relevant_immediately", True) or case.get("delivery_mode") == "immediate"
            if recipient_ids and immediate:
                delivery_result = self.send_due(max(20, len(recipient_ids)))
                counts["sent"] += delivery_result["sent"]
                counts["delivery_failed"] += delivery_result["failed"]
            return True
        except Exception as error:
            self.store.finish_llm_job(job_id, False, round((time.monotonic() - started) * 1000), str(error))
            raise


    def process_next_llm_job(self) -> dict | None:
        """Process one persistent analysis job so collection never blocks the full LLM queue."""
        if not LOCAL_LLM_LOCK.acquire(blocking=False):
            return None
        try:
            job = self.store.next_llm_job()
            if not job:
                return None
            article, case = self.store.get_article(job["article_id"]), self.store.get_case(job["case_id"])
            if not article or not case or not case.get("is_active"):
                self.store.finish_llm_job(job["id"], False, 0, "article_or_active_case_missing")
                return {"id": job["id"], "status": "failed"}
            counts = {"scored": 0, "queued": 0, "sent": 0, "delivery_failed": 0}
            try:
                processed = self._evaluate_queued(job["id"], case, article, counts)
                return {"id": job["id"], "status": "completed" if processed else "skipped", "counts": counts}
            except Exception as error:
                return {"id": job["id"], "status": "failed", "error": str(error), "counts": counts}
        finally:
            LOCAL_LLM_LOCK.release()


    def run_case(self, case_id: str) -> dict:
        case = self.store.get_case(case_id)
        if not case:
            raise ValueError("케이스를 찾지 못했습니다.")
        if case.get("organization_id"):
            return self.run_organization(str(case["organization_id"]))
        if not COLLECTION_LOCK.acquire(blocking=False):
            raise RuntimeError("다른 AI 언론동향 비서 수집 작업이 진행 중입니다.")
        run_id = self.store.start_run(case_id)
        counts = {"collected": 0, "new": 0, "analysis_queued": 0, "scored": 0, "queued": 0, "sent": 0, "delivery_failed": 0, "skipped": 0}
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
                    case_version = int(case.get("version", 1))
                    if self.store.score_exists(article["id"], case_id):
                        counts["skipped"] += 1
                        continue
                    fetched = self.collector.fetch_body(article["original_url"])
                    candidate.update(fetched)
                    article, _created = self.store.upsert_article(candidate)
                    self.store.queue_llm_job(article["id"], case_id, case_version, case.get("organization_id"))
                    counts["analysis_queued"] += 1
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
            COLLECTION_LOCK.release()

    def run_organization(self, organization_id: str) -> dict:
        organization = self.store.get_organization(organization_id)
        if not organization:
            raise ValueError("기관을 찾지 못했습니다.")
        cases = self.store.list_cases_for_organization(organization_id, active_only=True)
        if not COLLECTION_LOCK.acquire(blocking=False):
            raise RuntimeError("다른 AI 언론동향 비서 수집 작업이 진행 중입니다.")
        run_id = self.store.start_run(organization_id=organization_id)
        counts = {"collected": 0, "new": 0, "analysis_queued": 0, "scored": 0, "queued": 0, "sent": 0, "delivery_failed": 0, "skipped": 0}
        errors: list[str] = []
        try:
            if not cases:
                self.store.set_organization_schedule(organization_id, next_collection_at(organization), collected=True)
                self.mirror.organization(self.store.get_organization(organization_id) or organization)
                self.store.finish_run(run_id, "completed", counts)
                return {"run_id": run_id, "organization_id": organization_id, "counts": counts, "errors": []}
            candidates = self.collector.collect_organization(organization)
            counts["collected"] = len(candidates)
            prepared: list[dict] = []
            for candidate in candidates:
                if not organization_candidate_match(organization, candidate):
                    counts["skipped"] += 1
                    continue
                try:
                    article, created = self.store.upsert_article(candidate)
                    counts["new"] += int(created)
                    if not article.get("body"):
                        candidate.update(self.collector.fetch_body(article["original_url"]))
                        article, _created = self.store.upsert_article(candidate)
                    if not organization_candidate_match(organization, article):
                        counts["skipped"] += 1
                        continue
                    prepared.append(article)
                    if len(prepared) >= int(organization.get("max_articles_per_run", 50)):
                        break
                except Exception as error:
                    errors.append(f"{candidate.get('title', '기사')[:80]}: {error}")

            for article in prepared:
                analysis, created_analysis = self.store.ensure_article_analysis(article, organization_id)
                if analysis.get("status") == "completed":
                    routed = self._route_article_analysis(analysis, article, organization_id)
                    counts["analysis_queued"] += routed["case_queued"]
                elif self.store.queue_article_analysis(analysis["id"], organization_id):
                    counts["analysis_queued"] += int(created_analysis)
            self.store.set_organization_schedule(organization_id, next_collection_at(organization), collected=True)
            self.mirror.organization(self.store.get_organization(organization_id) or organization)
            self.store.finish_run(run_id, "completed_with_errors" if errors else "completed", counts, "\n".join(errors))
            return {"run_id": run_id, "organization_id": organization_id, "counts": counts, "errors": errors}
        except Exception as error:
            self.store.set_organization_schedule(organization_id, next_collection_at(organization), collected=False)
            self.mirror.organization(self.store.get_organization(organization_id) or organization)
            self.store.finish_run(run_id, "failed", counts, str(error))
            raise
        finally:
            COLLECTION_LOCK.release()


    @staticmethod
    def message_text(delivery: dict) -> str:
        case_name = str(delivery.get("case_name") or "AI 언론동향 비서")[:20]
        raw_tags = delivery.get("classification_tags") or []
        if isinstance(raw_tags, str):
            try:
                raw_tags = json.loads(raw_tags)
            except (json.JSONDecodeError, TypeError):
                raw_tags = []
        tags = [str(delivery.get("organization_tag") or "").strip()[:20]]
        tags.extend(str(value).strip()[:20] for value in raw_tags if str(value).strip())
        tags = list(dict.fromkeys(tag for tag in tags if tag))[:3]
        tags = tags or [str(delivery.get("article_type") or "기타")[:20]]
        tag_line = " ".join(f"[{tag}]" for tag in tags)
        title = str(delivery.get("title") or "")[:58]
        summary = str(delivery.get("summary") or "")[:62]
        similarity = delivery.get("similarity_score", delivery.get("llm_score", delivery.get("final_score", 0)))
        text = f"{tag_line}\n[{case_name}] 유사도 {float(similarity or 0):.0f}%\n{title}\n\n{summary}"
        return text[:200]

    def article_link(self, article_id: str, fallback: str) -> str:
        redirect = urllib.parse.urlsplit(self.settings.kakao_redirect_uri)
        if redirect.scheme in {"http", "https"} and redirect.netloc:
            article_id = urllib.parse.quote(str(article_id), safe="")
            return f"{redirect.scheme}://{redirect.netloc}/poc/master-press/article/{article_id}"
        return fallback

    def send_due(self, limit: int = 20) -> dict:
        if not DELIVERY_LOCK.acquire(blocking=False):
            return {"sent": 0, "failed": 0, "errors": []}
        try:
            return self._send_due(limit)
        finally:
            DELIVERY_LOCK.release()

    def _send_due(self, limit: int = 20) -> dict:
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

    def orchestration_tick(self) -> dict:
        results = {"organizations": [], "cases": [], "delivery": {}, "press_releases": {}, "cleanup": {}}
        results["delivery"] = self.send_due()
        results["press_releases"] = self.press_releases.sync()
        for organization in self.store.list_due_organizations():
            try:
                results["organizations"].append(self.run_organization(organization["id"]))
            except RuntimeError as error:
                results["organizations"].append({"organization_id": organization["id"], "error": str(error)})
                break
            except Exception as error:
                results["organizations"].append({"organization_id": organization["id"], "error": str(error)})
        for case in self.store.list_due_cases():
            try:
                results["cases"].append(self.run_case(case["id"]))
            except RuntimeError as error:
                results["cases"].append({"case_id": case["id"], "error": str(error)})
                break
            except Exception as error:
                results["cases"].append({"case_id": case["id"], "error": str(error)})
        now = datetime.now(KST)
        if now.hour == 3 and now.minute < 2:
            results["cleanup"] = self.store.cleanup(self.settings.raw_retention_days, self.settings.metadata_retention_days)
        return results

    def common_worker_tick(self) -> dict | None:
        reanalysis = self.process_next_reanalysis()
        if reanalysis:
            return {"stage": "reanalysis", "result": reanalysis}
        article = self.process_next_article_analysis()
        if article:
            return {"stage": "article", "result": article}
        embedding = self.process_next_embedding()
        if embedding:
            return {"stage": "embedding", "result": embedding}
        if not LOCAL_LLM_LOCK.acquire(blocking=False):
            return None
        try:
            press = self.press_releases.process_next()
            return {"stage": "press_release", "result": press} if press else None
        finally:
            LOCAL_LLM_LOCK.release()

    def case_worker_tick(self, burst: bool = False) -> dict | None:
        if burst and self.store.pending_case_evaluation_jobs() < 10:
            return None
        result = self.process_next_case_evaluation()
        return {"stage": "case", "result": result} if result else None

    def tick(self) -> dict:
        return self.orchestration_tick()


_SERVICE: MasterPressService | None = None
_SERVICE_KEY: tuple | None = None


def get_service() -> MasterPressService:
    global _SERVICE, _SERVICE_KEY
    settings = Settings.from_env()
    settings.ensure_directories()
    key = (str(settings.database_path), settings.naver_client_id, settings.kakao_redirect_uri, settings.llm_model, settings.embedding_model, bool(settings.openrouter_api_key), settings.openrouter_base_url, settings.openrouter_case_model, settings.openrouter_daily_soft_limit)
    if _SERVICE is None or _SERVICE_KEY != key:
        _SERVICE = MasterPressService(settings, Store(settings.database_path))
        _SERVICE_KEY = key
    return _SERVICE


def worker_tick() -> dict:
    return get_service().orchestration_tick()


def common_worker_tick() -> dict | None:
    return get_service().common_worker_tick()


def case_worker_tick(burst: bool = False) -> dict | None:
    return get_service().case_worker_tick(burst=burst)
