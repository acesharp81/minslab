from types import SimpleNamespace
from unittest.mock import patch
from threading import Event
import time
import pytest
from app.ingestion import summary_worker as worker


class StopLoop(BaseException):
    pass


def test_every_poll_keeps_phase_and_skips_overrun_slots():
    assert worker.OPENROUTER_HEAD_START_SECONDS == 1.0
    for phase, expected in [(0.0, [0.0, 10.0, 30.0]), (1.0, [1.0, 11.0, 31.0])]:
        clock = [0.0]
        starts = []
        def sleep(seconds):
            clock[0] += seconds
        def process(*args, **kwargs):
            assert kwargs['shared_pool'] is True
            starts.append(clock[0])
            if len(starts) == 3:
                raise StopLoop()
            clock[0] += [3.0, 12.0][len(starts)-1]
            return {'api_requests': 0, 'failed': 0}
        with patch.object(worker.time, 'monotonic', lambda: clock[0]), \
             patch.object(worker.time, 'sleep', sleep), \
             patch.object(worker, 'process_available', process), pytest.raises(StopLoop):
            worker.run_pool_lane(SimpleNamespace(database_url='fixture',openrouter_daily_limit=950),
                SimpleNamespace(once=False,interval=10),SimpleNamespace(provider='test'),
                origin=0,phase=phase)
        assert starts == expected


def test_provider_exception_retains_cooldown_without_catchup():
    assert worker.next_pool_tick(0, 10, 0, 63) == 70
    assert worker.next_pool_tick(0, 10, 1, 63) == 71
    assert worker.next_pool_tick(100, 10, 1, 100) == 101


def test_mini_starts_while_nemo_request_is_still_running():
    mini_started = Event()
    starts = {}
    settings=SimpleNamespace(database_url='fixture',openrouter_daily_limit=950,
        openrouter_api_key='fixture',openai_api_key='fixture',llm_model='nemo',openrouter_base_url='fixture')
    def process(database_url, client, **kwargs):
        starts[client.provider] = time.monotonic()
        if client.provider == 'openrouter':
            assert mini_started.wait(4), 'Mini must not wait for the Nemo result'
        else:
            mini_started.set()
        return {'api_requests': 0, 'failed': 0}
    with patch('app.db.migrate.apply_migrations'), \
         patch('app.services.openrouter_summary.OpenRouterSummaryClient',return_value=SimpleNamespace(provider='openrouter')), \
         patch('app.services.openai_summary.OpenAISummaryClient',return_value=SimpleNamespace(provider='openai')), \
         patch.object(worker,'process_available',process):
        worker.run_grouped_pool(settings,SimpleNamespace(once=True,interval=10))
    assert 0.9 <= starts['openai']-starts['openrouter'] < 3


def test_mini_only_has_no_head_start_delay():
    settings=SimpleNamespace(database_url='fixture',openrouter_daily_limit=950,
        openrouter_api_key='',openai_api_key='fixture')
    with patch('app.db.migrate.apply_migrations'), \
         patch('app.services.openai_summary.OpenAISummaryClient',return_value=SimpleNamespace(provider='openai')), \
         patch.object(worker,'run_pool_lane') as lane:
        worker.run_grouped_pool(settings,SimpleNamespace(once=True,interval=10))
    assert lane.call_args.kwargs['phase'] == 0
