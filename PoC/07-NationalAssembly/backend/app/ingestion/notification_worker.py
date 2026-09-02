from __future__ import annotations

import argparse
import logging
import socket
import time
import uuid

from ..config import get_settings
from ..db.connection import connect
from ..db.watch_delivery_repository import WatchDeliveryRepository
from ..services.watch_kakao import KakaoNotificationProvider, KakaoProviderError


LOGGER = logging.getLogger(__name__)
RETRYABLE = {429, 500, 502, 503, 504}


def run_once(database_url: str) -> dict[str, int]:
    settings = get_settings()
    with connect(database_url) as connection:
        repository = WatchDeliveryRepository(connection)
        repository.prune_operational_history()
        if not settings.watch_kakao_enabled:
            return {"claimed": 0, "sent": 0, "failed": 0}
        provider = KakaoNotificationProvider(settings)
        worker_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
        delivery = repository.claim(worker_id)
        if not delivery:
            return {"claimed": 0, "sent": 0, "failed": 0}
        try:
            provider.send(delivery, repository)
            repository.finish(delivery["outbox_id"], sent=True)
            return {"claimed": 1, "sent": 1, "failed": 0}
        except KakaoProviderError as exc:
            if exc.status in {401, 403}:
                repository.mark_reauthorize(delivery["account"]["account_id"], str(exc))
            repository.finish(
                delivery["outbox_id"], sent=False, error=str(exc),
                retryable=exc.status in RETRYABLE,
            )
            return {"claimed": 1, "sent": 0, "failed": 1}
        except Exception as exc:  # noqa: BLE001 - isolated provider failure
            repository.finish(
                delivery["outbox_id"], sent=False,
                error="unexpected provider failure", retryable=True,
            )
            LOGGER.warning("Kakao delivery failed without sensitive payload: %s", type(exc).__name__)
            return {"claimed": 1, "sent": 0, "failed": 1}


def main() -> None:
    parser = argparse.ArgumentParser(description="PoC 7 외부 알림 outbox worker")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    logging.basicConfig(level=settings.national_assembly_log_level)
    while True:
        try:
            result = run_once(settings.database_url)
            if any(result.values()):
                LOGGER.info("notification worker processed %s", result)
        except Exception:  # noqa: BLE001 - persistent worker retries
            LOGGER.exception("notification worker iteration failed")
        if args.once:
            return
        time.sleep(max(0.5, args.interval))


if __name__ == "__main__":
    main()
