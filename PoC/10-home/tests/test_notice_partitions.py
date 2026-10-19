from backend.independent_metrics import partition_notices


def event(tenure,quantity,key,proof=None):
    return dict(notice_tenure=tenure,quantity=quantity,event_id=key,event_date='2026-08-20',
        review_status='CONFIRMED',collected_at=key,notice_scope_proof=proof,quantity_scope='WHOLE')


def proof():
    return dict(breakdown={'국민임대':991,'영구임대':332},total_units=1323,source_revision_id='original')


def test_original_and_corrected_notices_count_once_per_verified_tenure():
    rows=[event('국민임대',991,'a',proof()),event('국민임대',991,'b',proof()),event('영구임대',332,'c')]
    picked=partition_notices(rows)
    assert len(picked)==2 and sum(e['quantity'] for e in picked)==1323
    assert next(e for e in picked if e['notice_tenure']=='국민임대')['event_id']=='b'
    assert all(e['quantity_scope']=='PART' and e['source_total_units']==1323 for e in picked)


def test_different_quantities_or_tenures_do_not_prove_disjointness():
    assert partition_notices([event('국민임대',991,'a'),event('영구임대',332,'b')]) is None


def test_incomplete_or_overlapping_scopes_remain_unresolved():
    assert partition_notices([event('국민임대',991,'a',proof())]) is None
    assert partition_notices([event('국민임대',991,'a',proof()),event('영구임대',333,'b')]) is None
    assert partition_notices([event('국민임대',991,'a',proof()),event('영구임대',332,'b'),event(None,1323,'c')]) is None


def test_conflicting_original_breakdowns_are_not_summed():
    other=dict(proof(),breakdown={'국민임대':990,'영구임대':333})
    assert partition_notices([event('국민임대',991,'a',proof()),event('영구임대',332,'b',other)]) is None
