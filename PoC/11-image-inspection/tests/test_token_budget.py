"""Optional PostgreSQL regression uses temporary tables, never the live ledger.
Run with POC11_TEST_SHARED_DATABASE=1 and a configured shared database URL.
"""
import os
import pytest
import psycopg
from app import token_budget
from app.config import Settings, ROOT


@pytest.mark.skipif(os.environ.get('POC11_TEST_SHARED_DATABASE')!='1', reason='Explicit shared PostgreSQL test connection required')
def test_shared_allowance_and_idempotent_settlement():
    with psycopg.connect(Settings().get('SHARED_BUDGET_DATABASE_URL'),connect_timeout=5) as c:
        c.execute('CREATE TEMP TABLE openai_group_daily_usage (LIKE public.openai_group_daily_usage INCLUDING ALL)')
        c.execute((ROOT/'deploy/shared-token-reservations.sql').read_text().replace('CREATE TABLE IF NOT EXISTS','CREATE TEMP TABLE'))
        c.execute("INSERT INTO openai_group_daily_usage(budget_group,usage_date,total_tokens) VALUES('main',timezone('UTC',now())::date,900000)")
        reservation=token_budget.reserve(c,'test1',80000)
        assert token_budget.snapshot(c)['remaining']==20000
        with pytest.raises(RuntimeError,match='100만'):token_budget.reserve(c,'blocked',20001)
        event={'input_tokens':12000,'output_tokens':3000,'cost_usd':.1}
        token_budget.settle(c,reservation,event)
        token_budget.settle(c,reservation,event)
        assert token_budget.snapshot(c)['remaining']==85000
        reservation=token_budget.reserve(c,'unknown',20000)
        token_budget.settle(c,reservation,{'cost_usd':None})
        assert token_budget.snapshot(c)['unknown_tokens']==20000
        reservation=token_budget.reserve(c,'rejected',10000)
        token_budget.settle(c,reservation,{'cost_usd':0})
        assert token_budget.snapshot(c)['remaining']==65000
        assert token_budget.snapshot(c)['reserved_tokens']==0


@pytest.mark.skipif(os.environ.get('POC11_TEST_SHARED_DATABASE')!='1', reason='Explicit shared PostgreSQL test connection required')
def test_mini_uses_separate_poc7_group_without_debiting_main():
    with psycopg.connect(Settings().get('SHARED_BUDGET_DATABASE_URL'),connect_timeout=5) as c:
        c.execute('CREATE TEMP TABLE openai_group_daily_usage (LIKE public.openai_group_daily_usage INCLUDING ALL)')
        c.execute((ROOT/'deploy/shared-token-reservations.sql').read_text().replace('CREATE TABLE IF NOT EXISTS','CREATE TEMP TABLE'))
        c.execute("INSERT INTO openai_group_daily_usage(budget_group,usage_date,total_tokens) VALUES('mini',timezone('UTC',now())::date,9900000)")
        reservation=token_budget.reserve(c,'mini-test',80000,'mini')
        assert token_budget.snapshot(c,'mini')['remaining']==20000
        assert token_budget.snapshot(c,'main')['remaining']==1000000
        with pytest.raises(RuntimeError,match='1,000만'):token_budget.reserve(c,'mini-overflow',20001,'mini')
        token_budget.settle(c,reservation,{'input_tokens':5000,'output_tokens':1000,'cost_usd':.1})
        token_budget.settle(c,reservation,{'input_tokens':5000,'output_tokens':1000,'cost_usd':.1})
        assert token_budget.snapshot(c,'mini')['remaining']==94000
        assert token_budget.snapshot(c,'main')['used_tokens']==0
        reservation=token_budget.reserve(c,'mini-unknown',10000,'mini')
        token_budget.settle(c,reservation,{'cost_usd':None})
        assert token_budget.snapshot(c,'mini')['unknown_tokens']==10000
