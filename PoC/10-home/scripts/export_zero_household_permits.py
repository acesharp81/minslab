"""Read-only export: source permit rows with zero households, never zero supply."""
import csv
import hashlib
import json
import sys
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path
from sqlalchemy import text
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for
from backend.service import HomeService


def valid_day(value):
    try:return date.fromisoformat(value) if value else None
    except (ValueError,TypeError):return None


def main():
    service=HomeService(engine_for(),'/app/data')
    out=service.data_dir/'remediation/zero-households-20261017'
    out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():raise ValueError('고정 추출본 덮어쓰기 금지')
    fields=['원천명칭','주소','지역','원천허가일','원천착공일','세대수','원천관리번호','HOME원천ID','판본ID','원천','원천안내URL']
    paths={key:out/name for key,name in [('all','허가일확인_0세대_전체.csv'),('approved','2026년허가_0세대.csv'),('started','2026년착공일_0세대.csv')]}
    handles={k:p.open('w',encoding='utf-8-sig',newline='') for k,p in paths.items()}
    writers={k:csv.writer(v) for k,v in handles.items()}
    for w in writers.values():w.writerow(fields)
    counts=Counter();regions={k:Counter() for k in paths};started=[];project_counts=Counter()
    with service.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
        with c.begin():
            c.execute(text('SET TRANSACTION READ ONLY'))
            cutoff=c.execute(text('SELECT CURRENT_TIMESTAMP')).scalar()
            end=cutoff.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Seoul')).date().isoformat();start=end[:4]+'-01-01'
            query="""SELECT entity_id,id,source_id,payload->>'name' AS name,payload->>'address' AS address,
                sample_region,payload->'dates'->>'원천 허가일 (apprvDay)' AS approval,
                payload->'dates'->>'원천 착공일 (stcnsDay)' AS started,
                payload->>'source_object_id' AS native_id,payload->>'evidence_url' AS url
                FROM home_revision WHERE kind='permit' AND superseded_at IS NULL AND payload->>'units'='0'
                ORDER BY sample_region,sample_name,entity_id"""
            for r in c.execution_options(stream_results=True).execute(text(query)).mappings():
                counts['all_zero_rows']+=1
                if not valid_day(r['approval']) or r['approval']>end:
                    counts['approval_date_unconfirmed']+=1;continue
                row=[r['name'],r['address'],r['sample_region'],r['approval'],r['started'],0,r['native_id'],r['entity_id'],r['id'],r['source_id'],r['url']]
                # Preserve large native IDs as text in spreadsheets; JSON keeps exact strings.
                safe=["'"+str(v) if i==6 or isinstance(v,str) and v.startswith(('=','+','-','@')) else v for i,v in enumerate(row)]
                groups=['all']
                if start<=r['approval']<=end:groups.append('approved')
                if valid_day(r['started']) and start<=r['started']<=end:
                    groups.append('started');started.append(dict(zip(fields,row)))
                for key in groups:
                    writers[key].writerow(safe);counts[key]+=1;regions[key][r['sample_region']]+=1
            for r in c.execution_options(stream_results=False).execute(text("SELECT policy_id,status,count(*) FROM home_mapping GROUP BY policy_id,status")):
                project_counts[str(r[0])+' / '+str(r[1])]=r[2]
    for f in handles.values():f.close()
    summary=dict(known_at=cutoff.isoformat(),period_start=start,period_end=end,counts=dict(counts),regions={k:dict(v) for k,v in regions.items()},
        project_counts=dict(project_counts),definition='原천 총세대수=0이며 실제 형식의 허가일이 존재하는 인허가 원장 행. 개별 현장 검증 완료 또는 공급0을 뜻하지 않음. 행 수는 고유 사업 수가 아님.',
        original_2152_scope='2026년 착공일이 있는 0세대 원장 행. 2026년 허가된 행 전체와 다른 범위.',
        source_url='https://www.data.go.kr/data/15136560/openapi.do')
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (out/'2026년착공일_0세대.json').write_text(json.dumps(started,ensure_ascii=False,indent=2)+'\n')
    sources=[]
    for s in service.sources():
        stats=s.get('stats',{})
        sources.append(dict(source_id=s['id'],name=s['name'],url=s['url'],status=s['status'],record_count=s['record_count'],last_success=s.get('last_success'),
            scope={k:stats.get(k) for k in ('scope_total_dongs','scope_completed_dongs','scope_remaining_dongs','source_base_date') if k in stats}))
    (out/'source-status.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(out/'허가일확인_0세대_전체.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        z.write(paths['all'],paths['all'].name);z.write(out/'summary.json','summary.json')
    manifest=dict(summary=summary,files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
