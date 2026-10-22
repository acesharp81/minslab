from datetime import datetime,timezone
from types import SimpleNamespace
from backend.stage_field_history import record_fields


def revision(no,payload):
    return SimpleNamespace(revision_no=no,payload=payload,recorded_at=datetime(2026,10,no,tzinfo=timezone.utc))


def test_history_tracks_field_changes_and_deletions_without_unrelated_revisions():
    rs=[revision(1,{'units':100,'old':'삭제 대상','actor':'가','reason':'등록'}),revision(2,{'units':100,'old':'삭제 대상','note':'다른 항목 수정'}),revision(3,{'units':120,'actor':'나','reason':'공고 정정'})]
    fields={r['field']:r for r in record_fields(rs,3)}
    assert fields['units']['value']==120
    assert [h['revision_no'] for h in fields['units']['history']]==[3,1]
    assert fields['units']['history'][0]['actor']=='나'
    assert fields['units']['history'][0]['reason']=='공고 정정'
    assert fields['old']['present'] is False and fields['old']['history'][0]['action']=='삭제'
    assert next(r for r in record_fields(rs,1) if r['field']=='units')['value']==100


def test_missing_actor_and_reason_remain_unknown_and_secrets_never_flatten():
    fields=record_fields([revision(1,{'units':0,'serviceKey':'private','raw':{'password':'private'}})],1)
    assert 'private' not in str(fields)
    h=next(r for r in fields if r['field']=='units')['history'][0]
    assert h['after']==0 and h['actor']=='미기록' and h['reason']=='미기록'
    assert h['time_kind']=='수집·저장 시각'


def test_date_repair_uses_real_officer_reason_not_stale_embedded_actor():
    initial={'progress':{'APPROVAL':{'event_date':'2026-04-30','actor':'이전 담당자'}}}
    corrected={'progress':{'APPROVAL':{'event_date':'2026-02-06','actor':'이전 담당자'}},'sequence_date_repairs':[{'at':'2026-10-22T12:00:00+09:00','actor':'담당자 대행','reason':'선후관계 보정','changes':[{'stage':'APPROVAL','field':'event_date','after':'2026-02-06'}]}]}
    h=record_fields([revision(1,initial),revision(2,corrected)],2,[('progress','APPROVAL','event_date')])[0]['history'][0]
    assert h['actor']=='담당자 대행' and h['reason']=='선후관계 보정'
    assert h['before']=='2026-04-30' and h['after']=='2026-02-06'
