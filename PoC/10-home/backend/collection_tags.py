"""Presentation categories; do not change adopted values or mapping states."""
from .input_status import input_status
from .source_authority import authority

LABELS={'OFFICIAL':'공식확인','OFFICER':'담당자확인','ESTIMATED':'추정 입력','MISSING':'미수집','UPCOMING':'미도래'}


def tag(value=None, upcoming=False, missing=False):
    v=value or {}
    if missing:
        code='UPCOMING' if upcoming else 'MISSING'
        reason='예정일이 기준일 이후여서 실제 측정 시기가 도래하지 않았습니다.' if upcoming else '이 항목의 채택값 또는 확인 근거가 확보되지 않았습니다.'
    elif input_status(v).startswith('ESTIMATED'):
        code='ESTIMATED';reason=v.get('input_basis') or v.get('basis') or '사건 선후관계·기간 등 저장된 산정 근거에 따른 추정값입니다.'
    elif authority(v.get('evidence_url'))=='OFFICIAL':
        code='OFFICIAL';reason='공식 자료를 수집하여 연결한 근거입니다.'
    elif input_status(v)=='CONFIRMED' or v.get('review_status')=='CONFIRMED':
        code='OFFICER';reason='비공식 자료를 담당자가 확인한 근거입니다.' if authority(v.get('evidence_url'))=='NONOFFICIAL' else '담당자가 직접 확인·입력한 값입니다. 외부 원문 URL은 별도 확인이 필요합니다.'
    else:
        code='MISSING';reason='채택 가능한 출처·담당자 확인이 미확보되었습니다.'
    return dict(code=code,label=LABELS[code],reason=reason)
