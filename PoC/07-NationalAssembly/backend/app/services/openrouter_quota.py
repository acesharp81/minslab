"""Use the same budget ledger as the network boundary for gateway clients."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests


class GatewayQuotaUnavailable(RuntimeError):
    """Unknown gateway state must not become a false daily-limit decision."""


def gateway_usage(settings: Any) -> dict[str, int] | None:
    base = urlsplit(settings.openrouter_base_url)
    status_url = str(settings.openrouter_gateway_status_url or '')
    # Older worker environment allowlists omit the status URL. Their known
    # gateway origin still uniquely identifies the authoritative status route.
    if not status_url and base.hostname == 'poc07-openrouter-gateway':
        status_url = urlunsplit((base.scheme, base.netloc, '/internal/status', '', ''))
    status = urlsplit(status_url)
    if (not status_url or not base.hostname
            or (base.scheme, base.hostname, base.port) != (status.scheme, status.hostname, status.port)):
        return None  # Direct OpenRouter callers retain the atomic local budget.
    try:
        response = requests.get(status_url, timeout=2.0)
        response.raise_for_status()
        data = response.json()
        used, limit = data['reserved'], data['operational_limit']
        if (data.get('provider') != 'openrouter' or data.get('period') != 'UTC_DAY'
                or data.get('usage_date') != datetime.now(timezone.utc).date().isoformat()
                or type(used) is not int or type(limit) is not int
                or used < 0 or not 1 <= limit <= 1000):
            raise ValueError('invalid_gateway_budget')
        return {'used': used, 'limit': limit}
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise GatewayQuotaUnavailable('openrouter_gateway_budget_unavailable') from exc
