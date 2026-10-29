"""Prepare a compatible rule revision without replacing individual action meanings.
Reads exported Markdown, removes conflicting duplicate action IDs from parent prose,
and documents the actual bounded verification contract. Saving is a separate API operation.
"""
import argparse,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rule_editor import parse_markdown,to_markdown

def align(markdown):
    pack=parse_markdown(markdown)
    for parent in pack['parents']:
        parent['original']=re.sub(r'`[HEPD]-\d{2}-[a-z]`', '해당 세부 항목',parent['original'])
        parent['original']=parent['original'].replace('2절 OCR','공통 문자').replace('reference_asset_id','reference_ids')
        parent['original']=parent['original'].replace('빨간 사각형','빨간 위치 표시').replace('노란 사각형','노란 위치 표시')
    guidance=pack['guidance'].replace('v2.3','v2.4')
    guidance=guidance.replace('확인한 객체에 **파란 테두리**','확인한 객체는 정상 영역 옵션을 켜면 파란 위치 표시').replace('**빨간 테두리**','빨간 위치 표시').replace('**노란 테두리**','노란 위치 표시')
    guidance=guidance.replace('OCR의 1차 문자열과 모델이 원본을 직접 읽은 문자열을 별도로 저장한다.', '1차 시각 모델 전사와 확대 원본을 독립 재판독한 문자열을 별도로 저장한다. 현재는 동일 시각 모델의 두 판독이며 독립 OCR 엔진을 실행했다고 표현하지 않는다.')
    guidance=guidance.replace('crop, 확대, 대비 보정 또는 다른 판독 방식으로 재검사한다. 대비 보정으로 생긴 획을 실제 원본 문자로 단정하지 않는다.', '주변을 포함한 crop과 깨끗한 확대 원본으로 재판독한다. 자동 한도 때문에 재검사하지 못한 구역은 미확인으로 남기고 선택 재검사를 안내한다.')
    guidance=guidance.replace('`reference_asset_id`','`reference_ids`')
    guidance=re.sub(r'\*\*F\..*', '**F. 재검사 우선순위**\n\n누락 의심 영역·작은 태극기·작은 문자·손을 우선한다. 여러 객체를 하나로 합치지 않는다. 태극과 각 괘의 존재/획/위치를 구분하고 한 요소의 가림 때문에 나머지 확인 결과를 보류하지 않는다. 문자 줄 앞뒤·줄바꿈과 제공 정본의 숫자/단위를 대조한다. 고유명사·서비스명·의도된 카피를 사전에 없다는 이유만으로 오타 처리하지 않는다. FAIL에는 관찰·기준·수정 사항, REVIEW에는 미해결 사유·실제 재검사 기록·확인 질문, PASS에는 검사한 범위를 적는다. 자체 확신도를 검증된 정확도로 설명하지 않는다.\n',guidance,flags=re.S)
    guidance+='''\n\n**G. 실행 계약과 비용 한도**\n\n- 세부 ID 의미는 각 `### ID` 아래 행동 한 곳에서만 정의한다. 상위 설명은 상황·예시이며 세부 ID에 다른 행동을 재배정하지 않는다.\n- 새 그림 읽기는 깨끗한 원본과 위치 참고 격자를 함께 전달한다. 화면에 격자를 강제로 그리지 않으며 가상 셀을 정밀한 글자 경계라고 표시하지 않는다. 원형 번호 및 영역 클릭으로 관련 의견을 연다.\n- 자동 확대/공식 도안 비교는 후보 객체 최대 9개, 묶음 호출 최대 3회이다. 획 손상·인식 불확실성·일치하는 공식 도안이 있는 대상을 우선한다. 객체 ID·원본 crop 범위·판독 결과·공식 자료 ID·비교한 rule_id·자료 이미지 해시를 기록한다. 미확인/한도 초과/실패는 확인 완료로 쓰지 않는다.\n- `assessments[rule_id]`는 객체별 판정 배열이다. 한 항목에 evidence_ids는 객체 하나만 연결하며 서로 다른 객체의 PASS/FAIL을 합치지 않는다. 대상이 없으면 ABSENT/NOT_APPLICABLE 항목 하나를 반환한다. 부모 집계와 무관하게 객체별 의견을 보존한다.\n- `error_type`은 문자 오류 종류를 기록한다. `evidence_status`·`location_unresolved`·문자 영역 집계는 서버가 실제 저장된 근거에서 계산한다. 필드 이름을 자유롭게 추가하지 않는다.\n- 등록된 기준 이미지가 있어도 자동으로 모든 대상과 대조했다고 보지 않는다. 실제 해당 객체·세부 행동·동일 자료 이미지의 직접 비교 기록이 있어야 공식 도안 확인 근거로 쓴다. 불명확한 비교는 UNAVAILABLE/REVIEW이며 적합한 기준자료 자체가 없으면 REQUIRED다.\n- 개별 자산 이용권·동의·법적 해석은 담당자 검토를 유지한다. 공공누리 일반 안내를 개별 이미지 사용 허락으로 취급하지 않는다.\n- 분석만 재실행은 저장된 첫 인식과 재검사 기록을 재사용하며 추가 이미지를 호출하지 않는다. 이전 기록에 문자 품질·비교 기록이 없으면 이를 확인했다고 주장하지 말고 새 그림+분석이 필요함을 알린다.\n'''
    pack['guidance']=guidance
    for step in pack['steps']:
        step['objective']=step['objective'].replace('reference_asset_id','reference_ids')
    result=to_markdown(pack);parse_markdown(result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('output');a=p.parse_args()
    Path(a.output).write_text(align(Path(a.input).read_text()))
