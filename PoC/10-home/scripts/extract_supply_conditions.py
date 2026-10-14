"""Extract prices from hash-verified archived official notices, with audit history."""
import argparse,hashlib,json
from pathlib import Path
from backend.db import Audit,engine_for,upsert_revision
from backend.service import HomeService
from backend.lh_notice_detail import parse_detail

def run(service,apply=False):
    out={'checked':0,'with_prices':0,'saved':0,'failures':[]}
    for r in service.rows('document_evidence'):
        if r['source_id']!='lh_notice_detail':continue
        out['checked']+=1
        try:
            path=(service.data_dir/r['original_file']).resolve()
            if not path.is_relative_to((service.data_dir/'raw').resolve()):raise ValueError('원문 경로 검증 실패')
            body=path.read_bytes()
            if hashlib.sha256(body).hexdigest()!=r['original_sha256']:raise ValueError('원문 해시 불일치')
            n=dict(id=r['notice_entity_id'],revision_no=r['notice_revision_no'],notice_no=r['notice_no'],name=r.get('notice_title',r['name']),notice_type=r.get('tenure'),evidence_url=r['evidence_url'],source_date=r.get('source_date'))
            terms=parse_detail(body,n,(r['region'],r['district'],r['block']))['supply_terms']
            if not terms:continue
            out['with_prices']+=1
            payload={k:r.get(k) for k in ('name','region','district','block','tenure','base_date','source_date','evidence_url','notice_round','notice_status','original_sha256','original_file')}
            payload.update(terms=terms,source_entity_id=r['id'],source_revision_no=r['revision_no'],actor='김민',reason='자동매칭 확인 완료 · 보관된 공식 공고 원문에서 면적별 평균분양가격 추출',basis='동일 공고·단지 탭 원문 항목 추출',verification_status='SOURCE_CONTENT_CHECKED')
            if apply:
                with service.sessions.begin() as db:
                    row,status=upsert_revision(db,'supply_conditions','lh_notice_terms',r['id'],payload,'supply_conditions_replay')
                    if status!='unchanged':
                        db.add(Audit(entity_id=row.entity_id,action='SUPPLY_CONDITIONS_EXTRACTED',before={},after=payload));out['saved']+=1
        except (ValueError,OSError,KeyError) as e:out['failures'].append({'id':r['id'],'reason':str(e)})
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');a=p.parse_args()
    print(json.dumps(run(HomeService(engine_for(),'/app/data'),a.apply),ensure_ascii=False))
