"""Display adoption separately from estimates; absence never proves uncollectability."""
LABELS={'CONFIRMED':'확인 완료','COLLECTED':'수집완료',
        'ESTIMATED_UNCOLLECTED':'추정 입력(미수집)','ESTIMATED_UNAVAILABLE':'추정 입력(수집 불가)'}

def input_status(value,assessment=None,confirmed=False):
    inferred=bool(value.get('inferred')) or any(
        p.get('rule') not in ('SOURCE_ACCEPTED','BEST_SOURCE_SELECTED','MEASUREMENT_TO_TARGET')
        for p in value.get('field_provenance',{}).values() if p.get('rule'))
    if inferred:
        unavailable=(assessment or {}).get('status')=='COLLECTION_UNAVAILABLE' or value.get('collection_status')=='COLLECTION_UNAVAILABLE' or value.get('input_rule')=='UNAVAILABLE_POLICY_ESTIMATE'
        return 'ESTIMATED_UNAVAILABLE' if unavailable else 'ESTIMATED_UNCOLLECTED'
    return 'CONFIRMED' if confirmed or value.get('manual') or value.get('origin')=='MANUAL' or value.get('source_id')=='officer' or value.get('officer_confirmed') else 'COLLECTED'

def input_label(value,assessment=None,confirmed=False):
    return LABELS[input_status(value,assessment,confirmed)]
