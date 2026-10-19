"""Archive final comparison evidence; no project event or approved quantity writes."""
import hashlib,json
from sqlalchemy import select
from backend.db import engine_for,upsert_revision,Audit,Revision
from backend.service import HomeService
from backend.october_alignment import BENCHMARK

def main():
 s=HomeService(engine_for());folder=s.data_dir/'final-review-20261019';bench=json.loads(BENCHMARK.read_text())
 specs=[('official-brief.pdf','제1차 주택공급 정책 브리프 · 서면 첨부','2026-10-16',bench['appendix_url'],dict(start_components=bench['start_components'],component_reconciliation=bench['component_reconciliation'],supply_plans=json.loads((folder/'official-q4-plans.json').read_text()),source_corrections=[r for r in bench['rows'] if r.get('source_correction_note')]))]
 for r in json.loads((folder/'lh-pdf-manifest.json').read_text()):
  if r['id'] in (11981,12047):continue # already in the scheduled LH source
  specs.append((f"lh-{r['id']}.pdf",'LH 후속 공식 자료 '+str(r['id']),{12075:'2026-07-21',12160:'2026-10-16',12158:'2026-10-15'}[r['id']],r['url'],dict(content_text=r['text'])))
 out=[]
 with s.sessions.begin() as db:
  for file,name,stamp,url,extra in specs:
   key='final-review-20261019:'+file
   payload=dict(name=name,sample_kind='document_evidence',source_object_id=key,source_date=stamp,base_date=stamp,date_precision='DAY',evidence_url=url,
    original_sha256=hashlib.sha256((folder/file).read_bytes()).hexdigest(),original_file='final-review-20261019/'+file,
    verification_status='SOURCE_CONTENT_CHECKED',facts=[],matched_project_ids=[],planned_units=None,exclude_from_project_totals=True,
    review_actor='담당자 대행 · 최종 검증 2026-10-19',**extra)
   row,action=upsert_revision(db,'document_evidence','official_document',key,payload,'final-review-20261019')
   if action!='unchanged':db.add(Audit(entity_id=row.entity_id,action='FINAL_OFFICIAL_SOURCE_REVIEW',before={},after=payload))
   out.append(dict(id=row.entity_id,name=name,action=action,evidence_url=url))
 (folder/'registered-official-sources.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
