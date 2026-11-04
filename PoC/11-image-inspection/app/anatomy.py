"""Visible hand structure and expected occlusion are separate observations."""
from typing import Literal
from pydantic import BaseModel, ConfigDict


class HandObservation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    side: Literal['LEFT', 'RIGHT', 'UNKNOWN']
    pose: Literal['OPEN', 'FIST', 'V_SIGN', 'THUMBS_UP', 'GRASP', 'OTHER', 'UNKNOWN']
    visibility: Literal['FULL', 'PARTIAL', 'HIDDEN']
    visible_structure: Literal['NATURAL', 'ANOMALOUS', 'UNCERTAIN']
    occlusion_reason: str
    anomaly_evidence: str


POLICY = '''손은 hands에 인물 기준 LEFT/RIGHT(불명 UNKNOWN), 자세, 보이는 범위, 가림 원인,
실제로 보이는 구조와 이상 근거를 각각 기록한다. 주먹·브이·엄지·물건 쥐기·원근으로 가려진
손가락을 전부 세지 못했다는 이유만으로 이상이나 필수 REVIEW를 만들지 않는다.
보이는 손가락 뿌리·관절·손목 연결에 결함이 없으면 그 관찰 범위는 자연스럽다고 설명한다.
보이지 않는 부분까지 정상이라고 인증하거나 가려진 손가락 수를 추측하지 않는다.
비정상 융합·분기·중복·연결이 실제로 관찰되면 부위와 형태를 anomaly_evidence에 적는다.
일반적인 작음·가림 설명은 anomaly_evidence에 넣지 않는다. 실제 이상 소견이 구체적이나
판독이 미확정인 경우에만 해당 소견을 REVIEW로 요청한다. 손이 아닌 객체의 hands는 빈 배열이다.'''


def protect(run, rows):
    objects = {o['id']: o for o in run.get('analysis_observation', run.get('observation', {})).get('objects', [])}
    for row in rows:
        if row['rule_id'] not in {f'D-02-{c}' for c in 'cdefghi'}:
            continue
        details = [h for oid in row.get('evidence_ids', []) for h in objects.get(oid, {}).get('hands', [])]
        if not details:
            continue
        row['hand_scope'] = {'hands': details, 'policy': 'visible-structure-v1',
                             'note': '가려진 손가락 수는 추측하지 않으며 보이는 구조만 판단합니다.'}
        anomalies = [h['anomaly_evidence'] for h in details
                     if h['visible_structure'] == 'ANOMALOUS' and h['anomaly_evidence'].strip()]
        if anomalies and row['status'] not in ('FAIL', 'ERROR', 'NOT_RUN'):
            row.update(status='REVIEW', review_basis='OBSERVED_ANOMALY', visual_issue=True,
                       document_review=False, target_presence='PRESENT',
                       reason='손 구조의 구체적인 관찰 확인: ' + ' / '.join(dict.fromkeys(anomalies)),
                       recommended_action='표시한 손의 연결·분기 부위를 원본에서 확인하세요.')
    return rows
