"""Pinned official PDF corrections: offer scope, AA7 plan, and statistical vintages."""
import argparse
import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

FOLDER='policy907-full-verification-20261021'
BATCH='official-csv-review-20261021'
ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    out=ROOT/'docs/analysis'/FOLDER
    specs=[]
    for key,pid,units,date,capacity,hold in [
        ('kumto_a2_notice','PRO_fcc796121d9c033bc356aaad',219,'2026-07-08',438,219),
        ('kumto_a4_notice','PRO_b572acaa0e4e1468c625d137',187,'2026-08-11',384,197)]:
        text=re.sub(r'\s+','',(out/(key+'.txt')).read_text())
        assert f'금회공급{units}세대' in text or f'금회모집{units}세대' in text
        manifest=json.loads((out/'additional_pdf_manifest.json').read_text())
        capture=next(r for r in manifest if r['key']==key)
        assert digest(out/(key+'.pdf'))==capture['sha256']
        specs.append(dict(key=key,project_id=pid,units=units,date=date,capacity=capacity,excluded_units=hold,
            file=key+'.pdf',sha256=capture['sha256'],url=capture['url'],pages='PDF p1~2'))
    # Independently parse the regional and apartment rows of official monthly PDFs.
    permit=[]
    for file,year,month in [('monthly_202602.txt',2026,2),('monthly_202607.txt',2026,7),
        ('monthly_202507.txt',2025,7),('monthly_202407.txt',2024,7)]:
        text=(out/file).read_text();section=text.split('➊ 인허가',1)[1].split('➋ 착공',1)[0]
        rows=re.findall(r'^\s*\(서울\)\s+(.+)$',section,re.M)
        assert len(rows)==2,(file,rows)
        values=[[int(n.replace(',','')) for n in re.findall(r'(?<![\d.])[\d,]+(?![\d.])',r)[:5]] for r in rows]
        assert all(len(r)==5 for r in values)
        for offset,index in [(0,2),(-1,4)]:
            for typ,quant in [('TOTAL',values[0][index]),('APARTMENT',values[1][index]),('NON_APARTMENT',values[0][index]-values[1][index])]:
                permit.append(dict(year=year+offset,month=month,type=typ,units=quant,source_file=file,
                    source_pdf=file.replace('.txt','.pdf'),snapshot_publication_year=year))
    # August source uses the already-pinned original official PDF.
    aug=ROOT/'docs/evidence/HOME_COLLECTION_GAP_REVIEW_20261019/official_august.txt'
    text=aug.read_text();section=text.split('➊ 인허가',1)[1].split('➋ 착공',1)[0]
    rows=re.findall(r'^\s*\(서울\)\s+(.+)$',section,re.M)
    assert len(rows)==2
    values=[[int(n.replace(',','')) for n in re.findall(r'(?<![\d.])[\d,]+(?![\d.])',r)[:5]] for r in rows]
    for year,index in [(2026,2),(2025,4)]:
        for typ,quant in [('TOTAL',values[0][index]),('APARTMENT',values[1][index]),('NON_APARTMENT',values[0][index]-values[1][index])]:
            permit.append(dict(year=year,month=8,type=typ,units=quant,source_file='official_august.txt',
                source_pdf='official_august.pdf',snapshot_publication_year=2026))
    import shutil
    for ext in ['txt','pdf']:shutil.copyfile(aug.with_suffix('.'+ext),out/('official_august.'+ext))
    assert next(r['units'] for r in permit if r['year']==2026 and r['month']==7 and r['type']=='APARTMENT')==23480
    def qty(y,m,t):return next(r['units'] for r in permit if r['year']==y and r['month']==m and r['type']==t)
    a03={str(y):qty(y,8,'NON_APARTMENT')-qty(y,2,'NON_APARTMENT') for y in [2025,2026]}
    aa7=out/'I03.html';assert '2031년준공및입주' in re.sub(r'\s+','',(out/'I03.txt').read_text())
    seoul=out/'S01.html';assert '중계본동(3,178호)' in re.sub(r'\s+','',(out/'S01.txt').read_text())
    plan=dict(batch_id=BATCH,prepared_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),offers=specs,permit=permit,
        junggye=dict(project_id='PRO_f5bf0d92748d113c80d49497',file=seoul.name,sha256=digest(seoul),
            url='https://www.seoul.go.kr/news/news_report.do?nttNo=465574',units=3178,observed_on='2026-09-07'),
        aa7=dict(project_id='PRO_30970726b72b0633c3d177fd',file=aa7.name,sha256=digest(aa7),
            url='https://www.incheon.go.kr/IC010205/view?curPage=1&repSeq=DOM_0000000015047612',
            publication_date='2026-07-01',units=1006,special_subset_units=80,completion_year=2031,move_in_year=2031),
        a03_pdf_vintage_values=a03,a03_pdf_vintage_growth=(a03['2026']/a03['2025']-1)*100,
        typed_starts=dict(file='typed_starts_jan_feb.json',sha256=digest(out/'typed_starts_jan_feb.json')),
        typed_history=dict(file='typed_starts_history.json',sha256=digest(out/'typed_starts_history.json')))
    (out/'supplement_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    print(json.dumps(dict(offers=sum(s['units'] for s in specs),pdf_stat_rows=len(permit),a03=a03,rate=plan['a03_pdf_vintage_growth']),ensure_ascii=False))


def apply():
    from sqlalchemy import select,text
    from backend.db import Revision,Mapping,Audit,engine_for,entity_id,upsert_revision
    from backend.service import HomeService
    folder=Path('/app/data')/FOLDER;plan=json.loads((folder/'supplement_plan.json').read_text())
    service=HomeService(engine_for());now=plan['prepared_at'];results=[]
    for s in plan['offers']+[plan['aa7'],plan['typed_starts'],plan['typed_history'],plan['junggye']]:assert digest(folder/s['file'])==s['sha256']
    with service.sessions.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        def protect():return [(r.entity_id,r.payload_hash) for r in db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None)).order_by(Revision.entity_id))],[(m.project_id,m.program_id,m.policy_id,m.status,m.revision_no) for m in db.scalars(select(Mapping).order_by(Mapping.project_id))]
        protected=protect()
        def current(eid):return db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)).with_for_update())
        def put(kind,sid,key,value):
            old=current(entity_id(kind,sid,key));before=deepcopy(old.payload) if old else {}
            r,outcome=upsert_revision(db,kind,sid,key,value,BATCH)
            if outcome!='unchanged':db.add(Audit(entity_id=r.entity_id,action='OFFICIAL_CSV_REVIEW',before=before,after=value))
            results.append(dict(kind=kind,id=r.entity_id,outcome=outcome));return r
        for s in plan['offers']:
            pid=s['project_id'];p=current(pid);assert p.payload['planned_units']==s['capacity']
            label='공식 공고 자동 매핑 - LH '+s['date']+' 금회 모집 '+str(s['units'])+'호'
            fact=dict(stage='SUPPLY',kind='ACTUAL',date=s['date'],units=s['units'],milestone='NOTICE',
                notice_round='MAIN',basis=label+'; 전체 임대규모와 순환용·별도 공급 제외',source_type='OFFICIAL')
            value=dict(sample_kind='document_evidence',name=p.payload['name']+' 최초 모집 PDF 상세 범위',source_date=s['date'],
                source_publication_date=s['date'],base_date='2026-10-21',planned_units=None,units=None,
                offered_units=s['units'],rental_inventory_units=s['capacity'],excluded_from_current_offer=s['excluded_units'],
                matched_project_ids=[pid],facts=[fact],status='CONFIRMED',checked_source_type='OFFICIAL',
                verification_status='SOURCE_CONTENT_CHECKED',evidence_url=s['url'],original_file=FOLDER+'/'+s['file'],
                original_sha256=s['sha256'],source_pages=s['pages'],exclude_from_project_totals=True,
                review_label=label,link_method='EXACT_DISTRICT_BLOCK_TENURE',policy_link_status='EXISTING_CONFIRMED')
            doc=put('document_evidence','official_document',BATCH+':'+s['key'],value)
            put('evidence_bridge','cross_source',pid+':'+doc.entity_id,dict(project_id=pid,source_entity_id=doc.entity_id,
                source_revision_no=doc.revision_no,source_id='official_document',source_name=value['name'],source_type='OFFICIAL',facts=[fact],units=None,status='CONFIRMED',
                reviewed=True,matching_version=BATCH,relation_type='EXACT_DISTRICT_BLOCK_TENURE',
                basis='공식 PDF 단지명·블록·국민/행복 유형·금회 모집표 정확 대조',evidence_url=s['url'],
                checked_source_type='OFFICIAL',review_label=label,base_date='2026-10-21'))
            pr=current(entity_id('project_profile','manual_project',pid));v=deepcopy(pr.payload);old=v['progress']['SUPPLY']
            if old.get('batch_id')!=BATCH:
                assert old.get('inferred') and old['units']==s['capacity']
                v['progress']['SUPPLY']=dict(origin='SOURCE',actor='공식 공고 자동 매핑',reason=label,changed_at=now,
                    batch_id=BATCH,input_rule='OFFICER_VERIFIED_SOURCE',input_basis=label,inferred=False,
                    event_date=s['date'],units=s['units'],source_type='OFFICIAL',review_label=label,evidence_url=s['url'],
                    source_entity_id=doc.entity_id,source_revision_no=doc.revision_no,previous_estimate=old)
                put('project_profile','manual_project',pid,v)
        s=plan['aa7'];pid=s['project_id'];label='공식 자료 자동 매핑 - 인천시 2026-07-01 검단 AA7 계획'
        facts=[dict(stage='CONSTRUCTION',kind='PLAN',date_label='2028년 하반기',units=1006,basis=label,source_type='OFFICIAL'),
            dict(stage='COMPLETION',kind='PLAN',date_label='2031년',units=1006,basis=label,source_type='OFFICIAL'),
            dict(stage='MOVE_IN',kind='PLAN',date_label='2031년',units=1006,basis=label+'; 입주 완료 실적 아님',source_type='OFFICIAL')]
        doc=put('document_evidence','official_document',BATCH+':AA7',dict(sample_kind='document_evidence',
            name='검단 AA7 육아친화 특화주택 선정·준공 및 입주 목표',region='인천광역시',source_date='2026-07-01',
            source_publication_date='2026-07-01',base_date='2026-10-21',planned_units=None,units=None,
            block_total_units=1006,special_subset_units=80,facts=facts,matched_project_ids=[pid],status='CONFIRMED',
            evidence_url=s['url'],original_file=FOLDER+'/'+s['file'],original_sha256=s['sha256'],
            checked_source_type='OFFICIAL',review_label=label,exclude_from_project_totals=True))
        put('evidence_bridge','cross_source',pid+':'+doc.entity_id,dict(project_id=pid,source_entity_id=doc.entity_id,
            source_revision_no=doc.revision_no,source_id='official_document',source_name='검단 AA7 공식 계획',source_type='OFFICIAL',facts=facts,status='CONFIRMED',reviewed=True,
            checked_source_type='OFFICIAL',relation_type='EXACT_DISTRICT_BLOCK',basis=label,evidence_url=s['url'],
            review_label=label,base_date='2026-10-21'))
        schedule=current(entity_id('execution_schedule','officer',pid+':MOVE_IN'));assert schedule
        v=deepcopy(schedule.payload)
        if v.get('batch_id')!=BATCH:
            assert v.get('inferred') and v['due_date']=='2032-07-02'
            previous=deepcopy(v);v.update(due_date='2031-12-31',units=1006,inferred=False,
                input_rule='SOURCE_ACCEPTED',input_basis=label+'; 원문 연도 말일 관리표기, 실제 사건일 아님',
                actor='공식 자료 자동 매핑',reason=label,basis=label,evidence_url=s['url'],batch_id=BATCH,
                changed_at=now,date_precision='YEAR',source_date_label='2031년',previous_estimate=previous,
                source_anchor=dict(precision='YEAR',original_schedule='2031년',evidence_url=s['url']))
            put('execution_schedule','officer',pid+':MOVE_IN',v)
        s=plan['junggye'];pid=s['project_id'];label='공식 자료 자동 매핑 - 서울시 2026-09-07 중계본동 3,178호 착공 확인'
        fact=dict(stage='CONSTRUCTION',kind='ACTUAL',date=s['observed_on'],units=3178,milestone='CONSTRUCTION',
            date_basis='OBSERVED_BY',source_event_date=None,observed_on=s['observed_on'],
            basis=label+'; 발표 시점까지 착공 사실 확인, 정확한 사건일·월은 미확인',source_type='OFFICIAL')
        doc=put('document_evidence','official_document',BATCH+':JUNGGYE',dict(sample_kind='document_evidence',name=label,
            region='서울특별시',source_date=s['observed_on'],source_publication_date=s['observed_on'],base_date='2026-10-21',
            units=None,planned_units=None,facts=[fact],matched_project_ids=[pid],status='CONFIRMED',checked_source_type='OFFICIAL',
            evidence_url=s['url'],original_file=FOLDER+'/'+s['file'],original_sha256=s['sha256'],exclude_from_project_totals=True))
        put('evidence_bridge','cross_source',pid+':'+doc.entity_id,dict(project_id=pid,source_entity_id=doc.entity_id,
            source_revision_no=doc.revision_no,source_id='official_document',source_name=label,source_type='OFFICIAL',
            facts=[fact],status='CONFIRMED',reviewed=True,checked_source_type='OFFICIAL',relation_type='EXACT_NAME_DISTRICT_UNITS',
            basis=label,evidence_url=s['url'],review_label=label,base_date='2026-10-21'))
        pr=current(entity_id('project_profile','manual_project',pid));v=deepcopy(pr.payload);old=v['progress']['CONSTRUCTION']
        if old.get('batch_id')!=BATCH:
            assert old.get('inferred') and old['units']==3178
            v['progress']['CONSTRUCTION']=dict(origin='SOURCE',actor='공식 자료 자동 매핑',reason=label,changed_at=now,
                batch_id=BATCH,input_rule='OFFICER_VERIFIED_SOURCE',input_basis=fact['basis'],inferred=False,
                event_date=s['observed_on'],date_basis='OBSERVED_BY',source_event_date=None,observed_on=s['observed_on'],
                units=3178,source_type='OFFICIAL',review_label=label,evidence_url=s['url'],source_entity_id=doc.entity_id,
                source_revision_no=doc.revision_no,previous_estimate=old)
            put('project_profile','manual_project',pid,v)
        for row,type_spec in [(row,spec) for spec in [plan['typed_starts'],plan['typed_history']]
                for row in json.loads((folder/spec['file']).read_text())]:
            key='5387:1:'+':'.join([row['date'],'서울',row['대분류'],row['중분류'],row['소분류']])
            put('housing_type_stat','molit_statistics',key,dict(sample_kind='housing_type_stat',name='서울 '+row['date']+' 착공 유형별',
                region='서울특별시',statistic_metric='착공',statistic_frequency='MONTH',statistic_period=row['date'],
                statistic_unit='호',units=row.get('착공실적'),value_status='SOURCE_NUMBER' if '착공실적' in row else 'NOT_PROVIDED',
                major_type=row['대분류'],middle_type=row['중분류'],minor_type=row['소분류'],
                source_publication_date=None,source_as_of=row['date'],base_date='2026-10-21',
                evidence_url='https://stat.molit.go.kr/portal/api/apiList.do',original_file=FOLDER+'/'+type_spec['file'],
                original_sha256=type_spec['sha256'],exclude_from_project_totals=True))
        manifests=json.loads((folder/'monthly_extra_manifest.json').read_text())+json.loads((folder/'additional_pdf_manifest.json').read_text())
        for item in plan['permit']:
            pdf=folder/item['source_pdf'];assert pdf.read_bytes().startswith(b'%PDF')
            url=next((r['url'] for r in manifests if r['key']+'.pdf'==item['source_pdf']),
                'https://www.index.go.kr/unity/potal/FileDown.do?seq=17704&id=1229&div=1')
            key='permit-pdf:'+item['source_pdf']+':'+str(item['year'])+':'+str(item['month'])+':'+item['type']
            put('housing_type_stat','molit_monthly_release',key,dict(sample_kind='housing_type_stat',name='서울 인허가 유형별 PDF 누계',
                region='서울특별시',statistic_metric='인허가',statistic_frequency='YTD',statistic_period=f"{item['year']}{item['month']:02d}",
                statistic_unit='호',units=item['units'],major_type=item['type'],source_as_of=f"{item['year']}{item['month']:02d}",
                source_publication_date=None,publication_vintage=item['source_pdf'],base_date='2026-10-21',
                evidence_url=url,original_file=FOLDER+'/'+pdf.name,original_sha256=digest(pdf),
                unit_basis='서울 전체·아파트 1~대상월 누계; 비아파트는 차이. 서로 다른 공표판본 별도 보존',exclude_from_project_totals=True))
        assert protect()==protected
    name='supplement_applied.json' if any(r['outcome']!='unchanged' for r in results) else 'supplement_idempotence.json'
    (folder/name).write_text(json.dumps(dict(changes=results,project_quantities_and_policy_assignments_preserved=True),ensure_ascii=False,indent=2))
    print(json.dumps(dict(file=name,changes=len(results),changed=sum(r['outcome']!='unchanged' for r in results)),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','apply']);args=parser.parse_args()
    (prepare if args.action=='prepare' else apply)()
