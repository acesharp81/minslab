"""Locally append a review-evidence revision; default is a read-only preview."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.storage import Store
from app.local_review import revised_run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_id');parser.add_argument('--expected-run-id',required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();s=Settings();st=Store(s.data/'inspection.sqlite3')
    with st.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT body FROM jobs WHERE id=?',(args.job_id,)).fetchone()
        if not row:raise SystemExit('검사 자료 없음')
        job=json.loads(row[0])
        if job['state'] in ('RUNNING','QUEUED'):raise SystemExit('진행 중 검사는 변경하지 않습니다.')
        source=job['runs'][-1]
        if source['id']!=args.expected_run_id:raise SystemExit('최신 검사 버전이 변경됐습니다. 다시 확인하세요.')
        run=revised_run(source);run['observation_reused_from']['job_id']=args.job_id
        summary={k:run['local_revision'][k] for k in ('source_run_id','reclassified_rows','binding_rows')}
        summary.update(job_id=args.job_id,run_id=run['id'],applied=args.apply,external_calls=0)
        if args.apply:
            job['runs'].append(run)
            c.execute('UPDATE jobs SET body=? WHERE id=?',(json.dumps(job,ensure_ascii=False),args.job_id));st._save_history(c,job)
    if args.apply:st.audit('system/local-review','RECONCILE_REVIEW_EVIDENCE',args.job_id,summary)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
