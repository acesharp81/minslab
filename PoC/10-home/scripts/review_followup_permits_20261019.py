"""One-off delegated review of two new-block permit links; preserves prior reviews."""
import json
from backend.db import engine_for
from backend.service import HomeService
from backend.stage_evidence import save_link
s=HomeService(engine_for());rows=s.rows('stage_evidence');result=[]
specs=[('PRO_795bc2926b42e5534efe75ef','PER_43f42658b04fc9f493f8af68',434,'CONFIRMED','담당자 대행: 인천계양 A16, 인천 계양구 박촌동, LH 공공주택, 원천 허가 434호와 공모 434호 일치. 2023-12-29 허가일만 연결. 원천 실제 착공일은 비어 있으므로 착공 실적 전이 없음.'),('PRO_fb6568f0135c296216c81ad3','PER_7faf864fb46b47db3cba74a5',717,'RELEASED','담당자 대행: 수원당수2 A3 이름·주택유형은 일치하나 2023년 허가 원천 717호와 공모 911호의 변경승인·부분물량 관계 미확보. 후보 근거 보존, 측정값 적용은 유보. 717호를 911호로 확대하지 않음.')]
for pid,sid,units,status,basis in specs:
 r=next(r for r in rows if r.get('project_id')==pid and r.get('stage')=='APPROVAL');selected=r['selected']
 assert selected['source_entity_id']==sid and selected['units']==units
 if r['status']==status and r.get('reviewed'):continue
 assert not r.get('reviewed')
 selected=dict(selected,basis=basis)
 applied=save_link(s,pid,'APPROVAL',r['revision_no'],status,selected,basis)
 assert not applied.get('conflict')
 result.append(dict(project_id=pid,source_id=sid,units=units,status=status,basis=basis))
if result:
 (s.data_dir/'policy-readmission-permit-review-20261019.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
