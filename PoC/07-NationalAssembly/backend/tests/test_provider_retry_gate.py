from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from app.services.provider_retry_gate import blocked_provider

NOW=datetime(2026,10,31,23,59,tzinfo=timezone.utc)
CLIENT=SimpleNamespace(provider='openai',model='mini')
def history(error, **kw):
 return [{'error':error,'created_at':NOW,'usage':{'provider':'openai','attempted_model':'mini',**kw}}]
def test_size_failure_needs_different_input_or_model_not_elapsed_time():
 assert blocked_provider(CLIENT,history('AUXILIARY_INPUT_TOO_LARGE'),NOW+timedelta(days=7))
 assert blocked_provider(SimpleNamespace(provider='openai',model='main'),history('AUXILIARY_INPUT_TOO_LARGE'),NOW) is None
 assert blocked_provider(CLIENT,[],NOW) is None

def test_daily_reset_and_rate_wait_boundaries():
 assert blocked_provider(CLIENT,history('DAILY_TOKEN_LIMIT'),NOW)
 assert blocked_provider(CLIENT,history('DAILY_TOKEN_LIMIT'),NOW+timedelta(minutes=1)) is None
 assert blocked_provider(CLIENT,history('AUXILIARY_RATE_WAIT',retry_after_seconds=120),NOW+timedelta(seconds=119))
 assert blocked_provider(CLIENT,history('AUXILIARY_RATE_WAIT',retry_after_seconds=120),NOW+timedelta(seconds=120)) is None

def test_quality_repair_is_not_suppressed_as_capacity_failure():
 assert blocked_provider(CLIENT,history('NARRATIVE_UNSUPPORTED_NUMBER'),NOW) is None
