from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests

from app.db.summary_repository import SummaryRepository
from app.services.openrouter_quota import gateway_usage, GatewayQuotaUnavailable


def settings(status=True):
    return SimpleNamespace(openrouter_base_url='http://poc07-openrouter-gateway:8071/api/v1',
        openrouter_gateway_status_url='http://poc07-openrouter-gateway:8071/internal/status' if status else '')


def payload(used=593):
    return {'provider':'openrouter', 'period':'UTC_DAY',
            'usage_date':datetime.now(timezone.utc).date().isoformat(),
            'reserved':used, 'operational_limit':950}


def test_legacy_950_does_not_block_central_593_or_increment_local_again():
    conn=Mock()
    conn.execute.return_value.fetchone.return_value=(950,)
    response=Mock();response.json.return_value=payload()
    with patch('app.db.summary_repository.get_settings',return_value=settings()), \
         patch('app.services.openrouter_quota.requests.get',return_value=response):
        repo=SummaryRepository(conn)
        assert repo.reserve_daily_request('openrouter',950)==594
        assert repo.reserve_daily_request('openrouter',950)==594
        assert repo.daily_usage('openrouter')==593
    conn.execute.assert_not_called()


def test_real_central_limit_blocks_and_fresh_reset_count_recovers():
    conn=Mock();response=Mock();response.json.side_effect=[payload(950),payload(0)]
    with patch('app.db.summary_repository.get_settings',return_value=settings()), \
         patch('app.services.openrouter_quota.requests.get',return_value=response):
        repo=SummaryRepository(conn)
        assert repo.reserve_daily_request('openrouter',950) is None
        assert repo.reserve_daily_request('openrouter',950)==1
    conn.execute.assert_not_called()


def test_direct_mode_still_reserves_atomically_without_http():
    s=SimpleNamespace(openrouter_base_url='https://openrouter.ai/api/v1',
                      openrouter_gateway_status_url=settings().openrouter_gateway_status_url)
    conn=Mock();conn.execute.return_value.fetchone.return_value=(42,)
    with patch('app.db.summary_repository.get_settings',return_value=s), \
         patch('app.services.openrouter_quota.requests.get') as get:
        assert SummaryRepository(conn).reserve_daily_request('openrouter',950)==42
        assert 'ON CONFLICT' in conn.execute.call_args.args[0]
        get.assert_not_called()


def test_old_worker_allowlist_uses_known_gateway_status():
    response=Mock();response.json.return_value=payload()
    with patch('app.services.openrouter_quota.requests.get',return_value=response) as get:
        assert gateway_usage(settings(False))=={'used':593,'limit':950}
        assert get.call_args.args[0]=='http://poc07-openrouter-gateway:8071/internal/status'


@pytest.mark.parametrize('bad', [None, {}, {**payload(),'reserved':-1},
    {**payload(),'usage_date':(datetime.now(timezone.utc)-timedelta(days=1)).date().isoformat()},
    {**payload(),'reserved':'593'}])
def test_invalid_or_stale_status_never_falls_back_to_false_local_exhaustion(bad):
    conn=Mock();response=Mock();response.json.return_value=bad
    with patch('app.db.summary_repository.get_settings',return_value=settings()), \
         patch('app.services.openrouter_quota.requests.get',return_value=response):
        with pytest.raises(GatewayQuotaUnavailable):
            SummaryRepository(conn).reserve_daily_request('openrouter',950)
    conn.execute.assert_not_called()


def test_gateway_unavailable_is_not_daily_limit_or_permission_to_bypass_gateway():
    with patch('app.services.openrouter_quota.requests.get',side_effect=requests.Timeout):
        with pytest.raises(GatewayQuotaUnavailable):
            gateway_usage(settings())
