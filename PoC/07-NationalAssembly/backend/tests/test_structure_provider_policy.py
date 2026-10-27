from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.ingestion import meeting_brief_worker as meeting
from app.ingestion import topic_structure_worker as structure


def settings():
    return SimpleNamespace(meeting_brief_nvidia_enabled=True, nvidia_api_key='fixture',
        meeting_brief_nvidia_model='nim', nvidia_base_url='https://fixture.invalid',
        meeting_brief_nvidia_min_interval_seconds=6, openrouter_api_key='fixture',
        meeting_brief_model='router', openrouter_base_url='https://fixture.invalid',
        openai_api_key='fixture', meeting_brief_openai_model='gpt-fixture',
        openai_base_url='https://fixture.invalid', database_url='fixture', openai_daily_token_limit=650000)


@pytest.mark.parametrize('capacity,expected', [
    (True, ['nvidia','openrouter']), (None, ['nvidia','openrouter']),
    (False, ['nvidia','openai']),
])
def test_all_structure_workloads_share_quota_gated_pool(monkeypatch, capacity, expected):
    monkeypatch.setattr(structure,'get_settings',settings)
    monkeypatch.setattr(meeting,'openrouter_brief_has_capacity',lambda _:capacity)
    assert [c.provider for c in structure.clients("verification")] == expected


def test_paid_reservation_rechecks_quota_before_any_budget_or_network_call(monkeypatch):
    monkeypatch.setattr(structure,'get_settings',settings)
    monkeypatch.setattr(meeting,'openrouter_brief_has_capacity',lambda _:False)
    paid=structure.clients("verification")[-1]
    connect=Mock();monkeypatch.setattr(structure,'connect',connect)
    monkeypatch.setattr(meeting,'openrouter_brief_has_capacity',lambda _:True)
    with pytest.raises(meeting.ProviderPolicyDeferred):paid.reserve_tokens(100)
    connect.assert_not_called()


def test_idle_mapping_cannot_bypass_shared_quota(monkeypatch):
    monkeypatch.setattr(meeting,'eligible_broadcast_ids',lambda *_:[])
    monkeypatch.setattr(meeting,'get_settings',settings)
    monkeypatch.setattr(meeting,'recent_openai_mapping_candidate',lambda:'fixture')
    monkeypatch.setattr(meeting,'openrouter_brief_has_capacity',lambda _:True)
    mapping=Mock();monkeypatch.setattr(meeting,'map_existing_brief_one',mapping)
    assert meeting.process_available()==[]
    mapping.assert_not_called()


def test_new_report_classification_precedes_historical_narrative():
    assert meeting.narrative_backfill_ready([],[],[])
    assert meeting.narrative_backfill_ready([{'status':'CACHED'}],[],[])
    assert not meeting.narrative_backfill_ready([{'status':'GENERATED'}],[],[])
    assert not meeting.narrative_backfill_ready([], [{'status':'PROCESSING'}], [])
    assert not meeting.narrative_backfill_ready([], [], [{'status':'PROCESSING'}])
    assert not meeting.narrative_backfill_ready([{'status':'FAILED'}],[],[])
