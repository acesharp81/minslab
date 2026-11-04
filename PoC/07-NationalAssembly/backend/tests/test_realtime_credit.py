from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import Mock
import pytest

from app.config import Settings
from app.services import realtime_credit as rc
from app.db.openai_daily_budget import DailyTokenLimitReached


def settings():
    return Settings(_env_file=None,openai_api_key='fixture',openai_credit_grant_id='grant',
        openai_credit_expires_at='2099-01-01T00:00:00+00:00',openai_credit_budget_usd=100,
        openai_realtime_credit_enabled=True)


def fake_connect(monkeypatch, spent='0', used='0'):
    c=Mock();c.execute.return_value.fetchone.side_effect=[(Decimal(spent),),(Decimal(used),)]
    @contextmanager
    def connect(_):yield c
    monkeypatch.setattr(rc,'connect',connect)
    return c


def test_free_first_and_next_day_returns_to_free(monkeypatch):
    free=Mock(model='gpt-5.4-mini');free._post.return_value=({'ok':1},{})
    monkeypatch.setattr(rc,'quota_client',lambda *_:free)
    paid=Mock();monkeypatch.setattr(rc,'credit_client',paid)
    client=rc.RealtimeMiniClient(settings())
    assert client._post('p',{},'assembly_summaries')[0]=={'ok':1}
    paid.assert_not_called()
    free._post.side_effect=[DailyTokenLimitReached('limit'),({'free_again':1},{})]
    monkeypatch.setattr(rc,'router_exhausted',lambda _:True)
    paid.return_value.model='gpt-6-luna';paid.return_value._post.return_value=({'paid':1},{})
    assert client._post('p',{},'assembly_summaries')[1]['billing_route']=='MONTHLY_CREDIT_SPILLOVER'
    assert client.model=='gpt-6-luna'
    assert client._post('p',{},'assembly_summaries')[0]=={'free_again':1}
    assert client.model=='gpt-5.4-mini'


def test_available_router_or_provider_cooldown_never_spills(monkeypatch):
    free=Mock();free._post.side_effect=DailyTokenLimitReached('limit')
    monkeypatch.setattr(rc,'quota_client',lambda *_:free)
    monkeypatch.setattr(rc,'router_exhausted',lambda _:False)
    paid=Mock();monkeypatch.setattr(rc,'credit_client',paid)
    with pytest.raises(DailyTokenLimitReached):rc.RealtimeMiniClient(settings())._post('p',{},'assembly_summaries')
    paid.assert_not_called()
    free._post.side_effect=DailyTokenLimitReached('PROVIDER_COOLDOWN')
    monkeypatch.setattr(rc,'router_exhausted',lambda _:True)
    with pytest.raises(DailyTokenLimitReached):rc.RealtimeMiniClient(settings())._post('p',{},'assembly_summaries')
    paid.assert_not_called()


def test_free_router_balance_unknown_fails_closed(monkeypatch):
    s=settings();s.openrouter_api_key='configured'
    monkeypatch.setattr(rc,'gateway_usage',lambda _:None)
    assert not rc.router_exhausted(s)
    monkeypatch.setattr(rc,'gateway_usage',lambda _:{'used':950,'limit':1000})
    assert rc.router_exhausted(s)


@pytest.mark.parametrize('spent,used',[('80','0'),('0','20'),('100','0')])
def test_common_grant_and_realtime_sublimit_protect_balance(monkeypatch,spent,used):
    fake_connect(monkeypatch,spent,used)
    c=rc.credit_client(settings())
    with pytest.raises(DailyTokenLimitReached) as e:c.reserve_tokens(20_000)
    assert e.value.skip_input_count


def test_reservation_uses_common_ledger_and_force_credit_even_for_mini(monkeypatch):
    from app.services import shared_budget
    fake_connect(monkeypatch)
    reserve=Mock(return_value={'event_id':'event'});monkeypatch.setattr(shared_budget,'reserve',reserve)
    c=rc.credit_client(settings(),'gpt-5.4-mini')
    assert c.reserve_tokens(20_000)=={'event_id':'event'}
    assert reserve.call_args.kwargs['force_credit'] is True
    assert reserve.call_args.args[4]=='gpt-5.4-mini'
    assert reserve.call_args.args[-2:]==(12000,8000)


def test_no_active_grant_blocks_before_network(monkeypatch):
    s=settings();s.openai_credit_grant_id=''
    c=rc.credit_client(s)
    post=Mock();monkeypatch.setattr('app.services.meeting_brief.requests.post',post)
    with pytest.raises(DailyTokenLimitReached):c._post('p',{},'assembly_summaries')
    post.assert_not_called()


def test_standard_price_and_unknown_result_settlement(monkeypatch):
    from app.services import shared_budget
    usage={'usage':{'prompt_tokens':900000,'completion_tokens':100000}}
    assert rc.usage_cost('gpt-5.4-mini',usage)==Decimal('1.125')
    # Luna long context uses 2x input and 1.5x output.
    assert rc.usage_cost('gpt-6-luna',usage)==Decimal('.255')
    assert rc.usage_cost('gpt-6-luna',{'usage':{'prompt_tokens':90000,'completion_tokens':10000}})==Decimal('.014')
    fake_connect(monkeypatch)
    settle=Mock();monkeypatch.setattr(shared_budget,'settle',settle)
    c=rc.credit_client(settings())
    c.settle_tokens({'event_id':'event'},10000,{})
    assert settle.call_args.args[2:5]==(None,None,None)


def test_unreviewed_model_cannot_use_credit():
    with pytest.raises(ValueError):rc.credit_client(settings(),'unknown-model')


def test_summary_repairs_only_rejected_luna_items_and_keeps_true_model(monkeypatch):
    from app.services import openai_summary as summary
    c=Mock(model='gpt-6-luna');c._post.return_value=({'summaries':['first']},{})
    monkeypatch.setattr(rc,'RealtimeMiniClient',lambda _:c)
    repair=Mock(model='gpt-5.4-mini');repair._post.return_value=({'summaries':['second']},{})
    monkeypatch.setattr(rc,'credit_client',lambda *_:repair)
    monkeypatch.setattr(summary,'validated_summary_items',lambda raw,rows:[{'content_hash':raw[0]}])
    monkeypatch.setattr(summary,'build_summary_prompt',lambda rows:str([r['content_hash'] for r in rows]))
    client=summary.OpenAISummaryClient(settings())
    result=client.summarize([{'content_hash':'first'},{'content_hash':'second'}])
    assert repair._post.call_args.args[0]=="['second']"
    assert [r['_summary_model'] for r in result.items]==['gpt-6-luna','gpt-5.4-mini']
    assert result.usage_metadata['rejected_ids']==[]
