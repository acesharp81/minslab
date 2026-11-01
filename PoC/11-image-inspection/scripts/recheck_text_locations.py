"""Append a no-API location revision using pre-experiment verdicts, never labels."""
import copy,hashlib,json,shutil,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.text_location import protect
from app.storage import now


def revise(evaluation,destination):
    baseline=json.loads((ROOT/'docs/qa-suite-2026-11-01/report.json').read_text())['latest_runs']
    tested={'QA_03_ocr_readability.json','QA_06_privacy_signs.json','QA_07_culture_food.json','QA_08_all_pass.json','QA_10_emblem.json'}
    summary=[]
    for name,item in baseline.items():
        source=evaluation/item['experiment']/name;saved=json.loads(source.read_text());prior=saved['run'];run=copy.deepcopy(prior)
        raw=(evaluation/'inputs/images'/saved['image']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=saved['image_sha256']:raise ValueError('Image hash mismatch')
        for row in run['results']:
            if row.get('glyph_evidence') and row.get('rects') and row.get('error_type') in ('VISUAL_TEXT_DEFECT','OCR_UNCERTAIN'):
                row['location_evidence']={'status':'VERIFIED_REGION','rects':copy.deepcopy(row['rects']),'method':'original-crop-glyph-cells'}
        protect(run,run['results'])
        changes=[dict(rule_id=a['rule_id'],instance_id=a['instance_id'],before_rects=b.get('rects'),after_rects=a.get('rects'),location_evidence=a.get('location_evidence')) for a,b in zip(run['results'],prior['results']) if a!=b]
        assert [r['status'] for r in run['results']]==[r['status'] for r in prior['results']]
        if not changes and name not in tested:continue
        directory=evaluation/'location-v1'/source.parent.name;directory.mkdir(parents=True,exist_ok=True)
        target=directory/name
        if target.exists():raise ValueError('Existing location revision; no overwrite')
        shutil.copytree(source.parent/(Path(name).stem+'-work')/'references',directory/(Path(name).stem+'-work')/'references')
        run.update(id=uuid.uuid4().hex,created_at=now(),finished_at=now(),phase='DONE',calls=[],reviews=[],selected=['D-02-l','H-06-b'],progress=2,total=2,elapsed_seconds=0,
            observation_reused_from={'run_id':prior['id']},analysis_reused_from={'run_id':prior['id'],'reason':'기존 판정 유지 · 추가 문자 모델 경로는 검증 결과 기본 미채택'},
            local_revision={'method':'text-location-v1','source_run_id':prior['id'],'api_calls':0,'location_changes':len(changes)})
        for row in run['results']:row['id']=uuid.uuid4().hex
        saved.update(revision='location-v1',source_code='.',source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'app').glob('*.py')},run=run)
        target.write_text(json.dumps(saved,ensure_ascii=False,indent=2))
        summary.append(dict(image=name,run_id=run['id'],source_run_id=prior['id'],api_calls=0,statuses_unchanged=True,changes=changes))
    destination.mkdir(parents=True,exist_ok=True);(destination/'location-audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({'images':len(summary),'location_changes':sum(len(x['changes']) for x in summary),'api_calls':0}))

if __name__=='__main__':revise(ROOT/'data/qa-20261101',ROOT/'docs/glyph-improvement-2026-11-01')
