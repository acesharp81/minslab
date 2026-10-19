"""Read-only exact district/block review of fourteen admitted plans against stored permits."""
import json
from sqlalchemy import select,or_
from backend.db import engine_for,Revision
from backend.service import HomeService
from backend.lh_spring_followup import review_key
s=HomeService(engine_for());ps=[p for p in s.projects() if p['source_id']=='lh_policy_followup'];terms={p['district'] for p in ps}
with s.sessions() as db:
 rows=db.scalars(select(Revision).where(Revision.kind=='permit',Revision.superseded_at.is_(None),or_(*(Revision.sample_name.contains(t,autoescape=True) for t in terms)))).all()
 sources=[dict(r.payload,id=r.entity_id,revision_no=r.revision_no,source_id=r.source_id) for r in rows]
result=[]
for p in ps:
 same=[r for r in sources if review_key(r)==review_key(p)]
 result.append(dict(project_id=p['id'],name=p['name'],units=p['planned_units'],key=review_key(p),matches=[dict(r,exact_units=r.get('units')==p['planned_units']) for r in same]))
(s.data_dir/'final-review-20261019/permit-final-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps([dict(name=r['name'],units=r['units'],matches=[dict(name=m['name'],units=m.get('units'),dates=m.get('dates'),id=m['id']) for m in r['matches']]) for r in result],ensure_ascii=False,indent=2))
