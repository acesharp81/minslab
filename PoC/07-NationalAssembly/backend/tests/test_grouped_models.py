from datetime import datetime, timezone
from unittest.mock import Mock
from contextlib import contextmanager
import pytest
from app.config import Settings
from app.services import grouped_models as gm
from app.db.openai_group_budget import OpenAIGroupBudget
from app.db.openai_daily_budget import DailyTokenLimitReached


def config(**kwargs):
    return Settings(_env_file=None, openai_api_key='fixture',openrouter_api_key='fixture',
        openai_credit_grant_id='initial',openai_credit_expires_at='2026-10-31T00:00:00+09:00',
        openai_credit_budget_usd=8,openai_credit_month_end_renewal=True,**kwargs)


@pytest.mark.parametrize('when,expected,amount,end',[
 ('2026-10-29T12:00:00+09:00','initial',8,'2026-10-31'),
 ('2026-10-31T00:00:00+09:00','initial:renew:2026-10-31',100,'2026-11-30'),
 ('2026-11-01T00:00:00+09:00','initial:renew:2026-10-31',100,'2026-11-30'),
 ('2026-11-30T00:00:00+09:00','initial:renew:2026-11-30',100,'2026-12-31'),
 ('2027-01-01T00:00:00+09:00','initial:renew:2026-12-31',100,'2027-01-31'),
 ('2028-02-29T00:00:00+09:00','initial:renew:2028-02-29',100,'2028-03-31'),
])
def test_credit_cycle_handles_month_end_leap_year_and_no_double_reset(when,expected,amount,end):
    period=gm.credit_period(config(),datetime.fromisoformat(when))
    assert period[0]==expected and period[1]==amount and period[2].startswith(end)


def test_budget_groups_do_not_share_allowance():
    s=config(openai_other_projects_mini_tokens=500000,openai_other_projects_main_tokens=100000)
    assert gm.daily_limit(s,'mini')==9500000
    assert gm.daily_limit(s,'main')==900000
    s.openai_credit_grant_id=''
    assert not gm.credit_active(s)


def test_group_pool_ignores_nim_and_other_auxiliaries(monkeypatch):
    monkeypatch.setattr(gm,'credit_active',lambda s:True)
    s=config(model_workload_groups_enabled=True,meeting_brief_nvidia_enabled=True,groq_aux_enabled=True,gemini_aux_enabled=True)
    assert [x.model for x in gm.pool(s,'integration')]==['gpt-5.4','gpt-6.1-terra']
    assert [x.provider for x in gm.pool(s)]==['openai','openrouter']
    assert gm.pool(s)[0].model=='gpt-5.4-mini'


def test_migration_ledger_queries_bind_group_to_every_operation():
    c=Mock();c.execute.return_value.fetchone.return_value=(datetime.now(timezone.utc).date(),)
    c.execute.return_value.rowcount=1
    b=OpenAIGroupBudget(c,'mini');day=b.reserve(100,1000)
    sql,args=c.execute.call_args.args
    assert sql.count('%s')==len(args)==7 and args[0]=='mini'
    b.settle(day,100,{'usage':{'prompt_tokens':20,'completion_tokens':5}})
    sql,args=c.execute.call_args.args
    assert sql.count('%s')==len(args) and args[-3]=='mini'
    b.settle(day,100,{'request_rejected':True})
    assert c.execute.call_args.args[1][3]==0 # no unknown charge for a rejected request


def test_integration_uses_terra_only_after_failure_or_quality_escalation(monkeypatch):
    main=Mock(provider='openai',model='gpt-5.4');terra=Mock(provider='openai',model='gpt-6.1-terra')
    main._post.return_value=({'ok':True},{})
    terra._post.return_value=({'repair':True},{})
    monkeypatch.setattr(gm,'pool',lambda s,w:[main,terra])
    c=gm.WorkloadBriefClient(config())
    assert c._post('p',{},'meeting_brief')[0]=={'ok':True}
    terra._post.assert_not_called()
    c.on_quality_failure('meeting_brief')
    assert c._post('repair',{},'meeting_brief')[0]=={'repair':True}
    c=gm.WorkloadBriefClient(config());main._post.side_effect=DailyTokenLimitReached()
    assert c._post('p',{},'meeting_brief')[0]=={'repair':True}


def test_unconfigured_paid_credit_cannot_make_even_input_count_request(monkeypatch):
    s=config();s.openai_credit_grant_id=''
    c=Mock();c.execute.return_value.fetchone.return_value=None
    @contextmanager
    def connection(_):yield c
    monkeypatch.setattr(gm,'connect',connection)
    post=Mock();monkeypatch.setattr('app.services.meeting_brief.requests.post',post)
    with pytest.raises(DailyTokenLimitReached):gm.quota_client(s,'paid')._post('p',{},'meeting_brief')
    post.assert_not_called()

@pytest.mark.parametrize('when,start,end,amount',[
 ('2026-10-31T23:59:59+09:00',None,'2026-11-01',8),
 ('2026-11-01T00:00:00+09:00','2026-11-01','2026-12-01',100),
 ('2026-12-31T23:59:59+09:00','2026-12-01','2027-01-01',100),
 ('2027-01-01T00:00:00+09:00','2027-01-01','2027-02-01',100),
 ('2028-02-29T23:59:59+09:00','2028-02-01','2028-03-01',100),
 ('2028-03-01T00:00:00+09:00','2028-03-01','2028-04-01',100),
])
def test_calendar_month_preserves_initial_balance(when,start,end,amount):
    s=config(openai_credit_month_start_renewal=True)
    s.openai_credit_expires_at='2026-11-01T00:00:00+09:00'
    period=gm.credit_period(s,datetime.fromisoformat(when))
    assert period[0]==('initial:renew:'+start if start else 'initial')
    assert period[1]==amount and period[2].startswith(end)


def test_shared_card_uses_monthly_denominator_without_restoring_spent_balance(monkeypatch):
    from app.services import shared_budget as b
    s=config(openai_credit_month_start_renewal=True)
    c=Mock();c.execute.return_value.fetchone.return_value=(1.8,0,.604)
    monkeypatch.setattr(b,'credit_period',lambda _:('initial',8,'2026-11-01T00:00:00+09:00'))
    monkeypatch.setattr(b.OpenAIGroupBudget,'today',lambda _:dict(total_tokens=0,reserved_tokens=0,unknown_tokens=0))
    card=next(m for m in b.snapshot(c,s)['models'] if m['id']=='openai-shared')
    assert card['limit']==100 and card['current_period_allowance']==8
    assert card['opening_used']==92 and card['used']==93.8
    assert card['remaining']==pytest.approx(5.596)
    assert '매월 1일' in card['note']
