"""Lossless scoped project/stage export; rows are records, not additive housing totals."""
import csv
import io
import json
from datetime import date
from .source_authority import authority, LABELS, clean, public_url
from .read_scope import projection_reads

STAGES={'POLICY':'정책','BUSINESS':'사업화','APPROVAL':'인허가','CONSTRUCTION':'건축·착공',
        'COMPLETION':'건축·준공','SUPPLY':'공급','MOVE_IN':'입주'}
HEADERS=['사업ID','사업명','정책ID','정책명','프로그램ID','프로그램명','시도','시군구',
         '공급유형','공급형태','사업계획호수','시행자','주소','위도','경도','단계','세부단계',
         '기록구분','조회기준일','일자','일자정밀도','호수','공정률','입력상태','출처구분',
         '출처ID','출처명','원천ID','원천판본','원문URL','연결확인상태','근거','사업메타정보JSON','단계기록JSON']

def csv_text(headers, rows):
    out=io.StringIO();writer=csv.writer(out);writer.writerow(headers)
    for row in rows:
        # Spreadsheet formulas must not execute source-supplied text on opening.
        writer.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v for v in row])
    return '\ufeff'+out.getvalue()

def records(service, matrix, collection_status=None):
    with projection_reads():
        projects={p['id']:p for p in service.projects(as_of=date.fromisoformat(matrix['as_of_date']))}
        for item in matrix['items']:
            if collection_status and not any(c['status']==collection_status for c in item['cells'].values()):continue
            p=projects.get(item['id'],{});mapping=p.get('mapping',{})
            from .supply_type import assess
            supply=assess(p)
            metadata=json.dumps(clean(p),ensure_ascii=False,separators=(',',':'))
            metadata_pending=True
            def project_metadata():
                nonlocal metadata_pending
                value=metadata if metadata_pending else ''
                metadata_pending=False
                return value
            prefix=[item['id'],item['name'],item.get('policy_id'),item.get('policy_name'),mapping.get('program_id'),item.get('program'),
                    item.get('region'),item.get('municipality'),supply.get('label') or supply.get('code'),p.get('tenure'),p.get('planned_units'),
                    p.get('developer'),p.get('address'),p.get('latitude'),p.get('longitude')]
            for stage,label in STAGES.items():
                cell=item['cells'].get('CONSTRUCTION' if stage=='COMPLETION' else stage,{})
                def matches(r):
                    milestone=r.get('milestone') or r.get('stage')
                    return milestone=='COMPLETION' if stage=='COMPLETION' else milestone!='COMPLETION' if stage=='CONSTRUCTION' else True
                found=False
                for kind,rows in [('목표·계획',cell.get('management',{}).get('target',[])),
                                  ('현재 측정',cell.get('management',{}).get('measurement',[])),('수집 근거',cell.get('sources',[]))]:
                    for r in rows:
                        if not matches(r):continue
                        found=True;url=public_url(r.get('evidence_url'));sid=r.get('source_id','')
                        classification=authority(url,sid,r.get('inferred') or str(r.get('input_status','')).startswith('ESTIMATED'))
                        yield prefix+[label,stage,kind,matrix['as_of_date'],r.get('date') or r.get('event_date') or r.get('due_date') or r.get('date_label'),
                            r.get('precision') or r.get('date_precision'),r.get('units'),r.get('pct'),r.get('input_status'),LABELS[classification],
                            sid,r.get('name'),r.get('source_entity_id'),r.get('source_revision_no'),url,r.get('review_status'),r.get('basis'),project_metadata(),
                            json.dumps(clean(r),ensure_ascii=False,separators=(',',':'))]
                if not found:
                    yield prefix+[label,stage,'미확보',matrix['as_of_date']]+[None]*13+[project_metadata(),'{}']

def export(service,matrix,collection_status=None):
    return csv_text(HEADERS,records(service,matrix,collection_status))
