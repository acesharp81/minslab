from __future__ import annotations

import argparse
import logging
import socket
import time
import uuid

import requests

from ..config import get_settings
from ..db.connection import connect
from ..db.official_change_report_repository import OfficialChangeReportRepository
from ..db.summary_repository import SummaryRepository
from ..db.topic_report_repository import TopicReportRepository
from ..services.openrouter_summary import DEFAULT_MODEL
from ..services.official_change_report import (
    PROMPT_VERSION as OFFICIAL_CHANGE_REPORT_PROMPT_VERSION,
    OpenRouterOfficialChangeReportClient,
    OfficialChangeReportResponseError,
    deterministic_changed_report,
    deterministic_unchanged_report,
)
from ..services.topic_report import (
    DEFAULT_TOPIC_REPORT_MODEL,
    OpenRouterTopicReportClient,
    TopicReportResponseError,
)


LOGGER = logging.getLogger(__name__)


def safe_topic_report_error(exc: Exception) -> str:
    if isinstance(exc, (TopicReportResponseError, OfficialChangeReportResponseError)):
        return str(exc)
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"HTTPError:HTTP_{exc.response.status_code}"
    return type(exc).__name__


def run_official_change_once(database_url: str) -> dict[str, object]:
    settings = get_settings()
    if not settings.official_change_reports_enabled:
        return {"status": "DISABLED", "generated": 0}
    model = (
        settings.official_change_report_model.strip()
        or settings.topic_report_model.strip()
        or settings.watch_llm_model.strip()
        or DEFAULT_MODEL
    )
    worker_id = f"{socket.gethostname()}:{uuid.uuid4()}"
    with connect(database_url) as connection:
        repository = OfficialChangeReportRepository(connection)
        repository.sync_pending(
            provider="openrouter", model=model,
            prompt_version=OFFICIAL_CHANGE_REPORT_PROMPT_VERSION,
        )
        item = repository.claim(worker_id)
        if item is None:
            return {"status": "IDLE", "generated": 0}
        snapshot = dict(item.get("input_snapshot") or {})
        if not snapshot.get("changes"):
            repository.complete(
                item["report_id"],
                report=deterministic_unchanged_report(snapshot),
                usage_metadata={
                    "api_requests": 0,
                    "reason": "NO_MEANINGFUL_CHANGE",
                    "privacy": {"public_evidence_only": True},
                },
            )
            return {"status": "READY", "generated": 1, "api_requests": 0}
        if not settings.openrouter_api_key:
            repository.fail(item["report_id"], "OPENROUTER_CONFIG_REQUIRED")
            return {"status": "CONFIG_REQUIRED", "generated": 0}
        if repository.reserve_daily(
            max(1, min(settings.official_change_report_daily_limit, 950))
        ) is None:
            repository.fail(item["report_id"], "OFFICIAL_CHANGE_DAILY_LIMIT", limited=True)
            return {"status": "DAILY_LIMIT_REACHED", "generated": 0}
        usage = SummaryRepository(connection)
        if usage.reserve_daily_request(
            "openrouter", max(1, min(settings.openrouter_daily_limit, 950))
        ) is None:
            repository.fail(item["report_id"], "OPENROUTER_DAILY_LIMIT", limited=True)
            return {"status": "GLOBAL_LIMIT_REACHED", "generated": 0}
        try:
            result = OpenRouterOfficialChangeReportClient(
                settings.openrouter_api_key, model=model,
                base_url=settings.openrouter_base_url,
            ).generate(snapshot)
            usage.record_monthly_token_usage(
                "openrouter", model, result.usage_metadata,
            )
            repository.complete(
                item["report_id"], report=result.report,
                usage_metadata=result.usage_metadata,
            )
            return {
                "status": "READY", "generated": 1,
                "report_id": str(item["report_id"]), "api_requests": 1,
            }
        except OfficialChangeReportResponseError as exc:
            safe_error = safe_topic_report_error(exc)
            repository.complete(
                item["report_id"],
                report=deterministic_changed_report(
                    snapshot, reason=f"OPENROUTER_{safe_error}",
                ),
                usage_metadata={
                    "api_requests": 1,
                    "fallback_reason": safe_error,
                    "privacy": {"public_evidence_only": True},
                },
            )
            LOGGER.warning(
                "official change report used grounded fallback: %s", safe_error,
            )
            return {
                "status": "READY", "generated": 1,
                "report_id": str(item["report_id"]), "api_requests": 1,
                "fallback": True,
            }
        except Exception as exc:
            safe_error = safe_topic_report_error(exc)
            repository.fail(item["report_id"], safe_error)
            LOGGER.warning(
                "official change report failed without evidence payload: %s", safe_error,
            )
            return {"status": "FAILED", "generated": 0}


def run_once(database_url: str) -> dict[str, object]:
    settings = get_settings()
    if not settings.topic_reports_enabled:
        return {"status": "DISABLED", "generated": 0}
    model = (
        settings.topic_report_model.strip()
        or DEFAULT_TOPIC_REPORT_MODEL
    )
    if not settings.openrouter_api_key:
        return {"status": "CONFIG_REQUIRED", "generated": 0}
    worker_id = f"{socket.gethostname()}:{uuid.uuid4()}"
    with connect(database_url) as connection:
        repository = TopicReportRepository(connection)
        item = repository.claim(worker_id)
        if item is None:
            return {"status": "IDLE", "generated": 0}
        if repository.reserve_user_daily(
            item["report_id"], item["subscriber_id"],
            max(1, settings.topic_report_user_daily_limit),
        ) is None:
            repository.fail(item["report_id"], "USER_DAILY_LIMIT", limited=True)
            return {"status": "USER_LIMIT_REACHED", "generated": 0}

        if repository.reserve_global_daily(
            max(1, min(settings.topic_report_daily_limit, 950))
        ) is None:
            repository.fail(item["report_id"], "TOPIC_REPORT_DAILY_LIMIT", limited=True)
            return {"status": "DAILY_LIMIT_REACHED", "generated": 0}
        usage = SummaryRepository(connection)
        if usage.reserve_daily_request(
            "openrouter", max(1, min(settings.openrouter_daily_limit, 950))
        ) is None:
            repository.fail(item["report_id"], "OPENROUTER_DAILY_LIMIT", limited=True)
            return {"status": "GLOBAL_LIMIT_REACHED", "generated": 0}
        try:
            result = OpenRouterTopicReportClient(
                settings.openrouter_api_key, model=model,
                base_url=settings.openrouter_base_url,
            ).generate(
                ministry=item["ministry"], topic=item["topic"],
                period_start=item["period_start"].isoformat(),
                period_end=item["period_end"].isoformat(),
                evidence=list(item.get("evidence") or []),
            )
            usage.record_monthly_token_usage(
                "openrouter", model, result.usage_metadata,
            )
            repository.complete(
                item["report_id"], report=result.report,
                usage_metadata=result.usage_metadata,
            )
            return {"status": "READY", "generated": 1, "report_id": str(item["report_id"])}
        except Exception as exc:
            safe_error = safe_topic_report_error(exc)
            repository.fail(item["report_id"], safe_error)
            LOGGER.warning("topic report failed without evidence payload: %s", safe_error)
            return {"status": "FAILED", "generated": 0}


def main() -> None:
    from ..db.migrate import apply_migrations

    parser = argparse.ArgumentParser(description="국정ON 주문형 주제별 보고서 worker")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    logging.basicConfig(level=settings.national_assembly_log_level)
    apply_migrations(settings.database_url)
    while True:
        try:
            official_result = run_official_change_once(settings.database_url)
            result = run_once(settings.database_url)
            LOGGER.info(
                "report worker: official=%s topic=%s", official_result, result,
            )
        except Exception as exc:
            LOGGER.exception("topic report worker failed: %s", type(exc).__name__)
        if args.once:
            break
        time.sleep(max(0.5, args.interval))


if __name__ == "__main__":
    main()
