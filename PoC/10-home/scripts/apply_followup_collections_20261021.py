"""Reviewed recruitment evidence and official type statistics; no new policy assignments.

Prepare on the host, then copy pinned files/plan to the HOME data directory.
Apply inside HOME's configured environment. Only four inferred SUPPLY entries
may become source-confirmed entries; their quantities must already agree.
"""
import argparse,calendar,hashlib,json,re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BATCH='source-followup-20261021'
ACTOR='담당자 대행 · 추가 공식 수집 및 유형 대응 검토'
IDS={'LH__c5ff63dfefc4381e8fe3e65d':('PRO_10812cb53671cfc2fe139728',14),
     'LH__c0b2f673e55d8542f6cfcdab':('PRO_cd0c470968bd4d8ee81b2651',60),
     'LH__d079620763503455cc205921':('PRO_caf8c53bb625d4bd6e627ef6',61),
     'LH__1bb92b7a22a41c7e9245c358':('PRO_1c2a1be12daff06cef52f8c6',110)}

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare(root):
    from bs4 import BeautifulSoup
    folder=root/'docs/analysis/official_followup_sources_20261021'
    manifest=json.loads((folder/'capture_manifest.json').read_text());specs=[]
    for m in manifest:
        if m['key'] not in IDS:continue
        pid,units=IDS[m['key']];assert m['status']==200
        raw=folder/m['file'];assert digest(raw)==m['sha256']
        soup=BeautifulSoup(raw.read_bytes(),'html.parser');tables=[]
        for table in soup.select('table'):
            heads=[re.sub(r'\s+','',h.get_text()) for h in table.select('thead th')]
            if '금회공급세대수' not in heads:continue
            column=heads.index('금회공급세대수');total=0
            for tr in table.select('tbody tr'):
                cells=tr.find_all(['th','td'],recursive=False);assert len(cells)==len(heads)
                value=cells[column].get_text(strip=True).replace(',','');assert value.isdigit();total+=int(value)
            tables.append(total)
        assert tables==[units],m['key']
        source=m['notice']['payload'];name=source['name']
        assert re.sub(r'\s+','',name) in re.sub(r'\s+','',soup.get_text())
        published=[]
        for strong in soup.select('li > strong'):
            if strong.get_text(strip=True)=='공고일':
                hit=re.search(r'(20\d{2})[.](\d{2})[.](\d{2})',strong.parent.get_text(' ',strip=True))
                if hit:published.append('-'.join(hit.groups()))
        assert set(published)=={source['source_date']}
        assert not any(w in name for w in ('예비','추가','잔여','재모집','재공고'))
        specs.append(dict(key=m['key'],project_id=pid,units=units,file=m['file'],sha256=m['sha256'],
            name=name,url=m['url'],date=source['source_date'],notice_no=source['notice_no'],
            checked_at=m['checked_at'],region=source['region']))
    assert len(specs)==4 and sum(s['units'] for s in specs)==245
    sh=[]
    for file,url,date,units,total,resupply in [
        ('sh_first_seoul_youth.html','https://youth.seoul.go.kr/api/sh/view.do?key=2309250014&sn=38','2026-05-28',55,1884,1829),
        ('sh_official_second.html','https://www.i-sh.co.kr/app/lay2/program/S1T294C296/www/brd/m_247/view.do?seq=309337','2026-08-28',154,1484,1330)]:
        path=folder/file;txt=re.sub(r'\s+','',BeautifulSoup(path.read_bytes(),'html.parser').get_text())
        assert f'신규공급{units}호' in txt and f'{resupply:,}호' in txt
        sh.append(dict(key=file.split('.')[0],name=f'SH 2026년 {1 if units==55 else 2}차 행복주택 신규모집',file=file,
            sha256=digest(path),url=url,date=date,units=units,announced_total_including_resupply=total,
            excluded_resupply_and_waitlist=resupply,region='서울특별시'))
    source=root/'data/official-followup-sources-20261021/molit_5387_seoul_2025_2026.json'
    rows=json.loads(source.read_text());assert len(rows)==96
    shutil=__import__('shutil');shutil.copyfile(source,folder/source.name)
    breakdown={}
    for year in ('2025','2026'):
        rs=[r for r in rows if r['date'].startswith(year)];assert len(rs)==48
        total=sum(r['착공실적'] for r in rs if r['대분류']=='계(다가구동수기준)')
        apartment=sum(r['착공실적'] for r in rs if r['대분류']=='아파트')
        nonapt=sum(r['착공실적'] for r in rs if (r['대분류'],r['중분류'],r['소분류']) in
            [('단독','단독','단독'),('단독','다가구','동수'),('다세대','다세대','다세대'),('연립','연립','연립')])
        assert nonapt==total-apartment
        breakdown[year]=dict(total=total,apartment=apartment,non_apartment=nonapt)
    rate=(breakdown['2026']['non_apartment']/breakdown['2025']['non_apartment']-1)*100
    assert breakdown['2025']['non_apartment']==2229 and breakdown['2026']['non_apartment']==4165 and round(rate)==87
    definition=folder/'yonhap_definition.html';text=BeautifulSoup(definition.read_bytes(),'html.parser').get_text(' ',strip=True)
    assert '일반주택(비아파트)' in text.replace(' ','')
    plan=dict(batch_id=BATCH,prepared_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),lh=specs,sh=sh,
        statistics=dict(file=source.name,sha256=digest(folder/source.name),breakdown=breakdown,rate=rate,rounded_rate=87,
            source_url='https://stat.molit.go.kr/portal/api/apiList.do',form_id='5387',style_num='1'),
        definition=dict(file=definition.name,sha256=digest(definition),url='https://www.yna.co.kr/amp/view/AKR20261016083900003',
            label='담당자 확인 완료 - 비공식 자료: 연합뉴스(2026-10-16)',source_scope='일반주택=비아파트의 유형 대응 해석; 원호수는 국토부 공식 API'))
    (folder/'application_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    print(json.dumps(dict(lh_new_notice_units=245,sh_new_notice_units=209,start_growth=rate),ensure_ascii=False))

def apply(folder,plan):
    from sqlalchemy import select,text
    from backend.db import Audit,Mapping,Revision,engine_for,entity_id,now,upsert_revision
    from backend.service import HomeService
    service=HomeService(engine_for());pids={s['project_id'] for s in plan['lh']}
    for item in plan['lh']+plan['sh']+[plan['statistics'],plan['definition']]:assert digest(folder/item['file'])==item['sha256']
    def protect(db):
        state={}
        for r in db.scalars(select(Revision).where(Revision.superseded_at.is_(None),Revision.kind.in_(['project','execution_schedule','project_profile']))):
            if r.kind=='project_profile' and r.payload.get('project_id') in pids:
                value=deepcopy(r.payload);value.get('progress',{}).pop('SUPPLY',None);state[r.entity_id]=value
            else:state[r.entity_id]=r.payload_hash
        state['mappings']=[(m.project_id,m.policy_id,m.program_id,m.status,m.revision_no) for m in db.scalars(select(Mapping).order_by(Mapping.project_id))]
        return state
    output=dict(lh=[],sh=[],statistic_rows=[],new_policy_assignments=0)
    with service.sessions.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(9072026)'));before=protect(db)
        def current(eid):return db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)).with_for_update())
        def put(kind,source,key,value,action):
            old=current(entity_id(kind,source,key));prior=deepcopy(old.payload) if old else {}
            row,outcome=upsert_revision(db,kind,source,key,value,BATCH)
            if outcome!='unchanged':db.add(Audit(entity_id=row.entity_id,action=action,before=prior,after=value))
            return row,outcome
        for s in plan['lh']:
            pid=s['project_id'];project=current(pid);mapping=db.scalar(select(Mapping).where(Mapping.project_id==pid))
            assert mapping.status=='CONFIRMED' and mapping.policy_id=='POL_2025_0907'
            assert project.payload['planned_units']==s['units']
            label='담당자 확인 완료 - 공식 자료: LH '+s['date']+' '+s['name']
            fact=dict(stage='SUPPLY',kind='ACTUAL',date=s['date'],units=s['units'],milestone='NOTICE',
                notice_round='MAIN',scope_partial=False,scope_units=s['units'],basis=label+' · 금회 최초 모집 호수, 계약·입주 완료와 구분',
                evidence_url=s['url'],source_type='OFFICIAL',review_label=label)
            value=dict(name=s['name'],sample_kind='document_evidence',source_object_id=BATCH+':'+s['key'],
                source_date=s['date'],source_publication_date=s['date'],base_date='2026-10-21',date_precision='DAY',region=s['region'],
                notice_no=s['notice_no'],notice_round='MAIN',offered_units=s['units'],units=None,planned_units=None,
                facts=[fact],matched_project_ids=[pid],exclude_from_project_totals=True,verification_status='SOURCE_CONTENT_CHECKED',
                status='CONFIRMED',reviewed=True,review_actor=ACTOR,review_label=label,checked_source_type='OFFICIAL',
                evidence_url=s['url'],original_sha256=s['sha256'],original_file=BATCH+'/'+s['file'],checked_at=s['checked_at'],
                basis='기존 확인 정책 연결 유지. 공식 단지고유명·주택유형·금회 공급표·기존 임대 사업 호수 대조. 혼합단지 전체 호수와 분리')
            doc,dout=put('document_evidence','official_document',value['source_object_id'],value,'OFFICIAL_NOTICE_CAPTURE')
            bridge=dict(project_id=pid,source_entity_id=doc.entity_id,source_revision_no=doc.revision_no,source_id='official_document',
                evidence_source_id='official_document',source_name=label,source_type='OFFICIAL',checked_source_type='OFFICIAL',
                facts=[fact],units=None,status='CONFIRMED',reviewed=True,review_actor=ACTOR,review_label=label,
                officer_review_status='CONFIRMED',relation_type='OFFICER_VERIFIED_EVENT_SCOPE',basis=value['basis'],evidence_url=s['url'],base_date='2026-10-21')
            linked,bout=put('evidence_bridge','cross_source',pid+':'+doc.entity_id,bridge,'OFFICIAL_NOTICE_LINK')
            profile=current(entity_id('project_profile','manual_project',pid));assert profile
            pv=deepcopy(profile.payload);prior=pv.get('progress',{}).get('SUPPLY');assert prior
            if prior.get('batch_id')==BATCH:
                assert (prior['event_date'],prior['units'])==(s['date'],s['units']);pout='unchanged'
            else:
                assert prior.get('inferred') and prior.get('units')==s['units'],'do not overwrite non-estimated or differently scoped progress'
                pv['progress']['SUPPLY']=dict(origin='MANUAL',actor=ACTOR,reason=label,changed_at=plan['prepared_at'],batch_id=BATCH,
                    input_rule='OFFICER_VERIFIED_SOURCE',input_basis=label,inferred=False,event_date=s['date'],units=s['units'],
                    review_label=label,source_type='OFFICIAL',evidence_url=s['url'],source_entity_id=doc.entity_id,source_revision_no=doc.revision_no,
                    previous_estimate=prior,field_provenance={f:dict(rule='VERIFIED_RECRUITMENT_NOTICE',evidence_url=s['url'],original_sha256=s['sha256']) for f in ['event_date','units']})
                _,pout=put('project_profile','manual_project',pid,pv,'SUPPLY_ESTIMATE_VERIFIED')
            output['lh'].append(dict(project_id=pid,name=s['name'],units=s['units'],event_date=s['date'],document_id=doc.entity_id,
                bridge_id=linked.entity_id,document_outcome=dout,bridge_outcome=bout,profile_outcome=pout))
        for s in plan['sh']:
            label='담당자 확인 완료 - 공식 자료: '+s['name']
            value=dict(name=s['name'],sample_kind='document_evidence',source_object_id=BATCH+':'+s['key'],region=s['region'],
                source_date=s['date'],source_publication_date=s['date'],base_date='2026-10-21',date_precision='DAY',notice_round='MAIN',
                offered_units=s['units'],announced_total_including_resupply=s['announced_total_including_resupply'],
                excluded_resupply_and_waitlist=s['excluded_resupply_and_waitlist'],planned_units=None,units=None,
                facts=[dict(stage='SUPPLY',kind='ACTUAL',date=s['date'],units=s['units'],milestone='NOTICE',notice_round='MAIN',
                    basis=label+' · 신규만 추출, 재공급·예비 포함 전체 모집인원 제외')],
                exclude_from_project_totals=True,matched_project_ids=[],policy_mapping_status='UNMAPPED',
                review_label=label,checked_source_type='OFFICIAL',verification_status='SOURCE_CONTENT_CHECKED',reviewed=True,
                status='CONFIRMED',review_actor=ACTOR,evidence_url=s['url'],original_sha256=s['sha256'],original_file=BATCH+'/'+s['file'],
                policy_link_hold_reason='공고 확인과 9·7 개별사업 귀속은 별도. 개별 단지·정책 근거 없이 통합공고를 정책 사업으로 편입하지 않음')
            row,outcome=put('document_evidence','official_document',value['source_object_id'],value,'SH_NEW_NOTICE_CAPTURE')
            output['sh'].append(dict(document_id=row.entity_id,units=s['units'],outcome=outcome,policy_status='UNMAPPED'))
        rows=json.loads((folder/plan['statistics']['file']).read_text())
        for s in rows:
            year,month=int(s['date'][:4]),int(s['date'][4:]);end=f'{year}-{month:02d}-{calendar.monthrange(year,month)[1]}'
            key='5387:1:'+':'.join([s['date'],'서울',s['대분류'],s['중분류'],s['소분류']])
            value=dict(sample_kind='housing_type_stat',name=f"서울 {s['date']} 착공 {s['대분류']}/{s['중분류']}/{s['소분류']}",
                source_object_id=key,region='서울특별시',source_date=end,source_date_label='통계 관측 종료일 · 공표일 아님',
                source_publication_date=None,source_as_of=s['date'],base_date='2026-10-21',statistic_metric='착공',
                statistic_period=s['date'],statistic_frequency='MONTH',statistic_unit='호',units=s['착공실적'],
                form_id='5387',style_num='1',major_type=s['대분류'],middle_type=s['중분류'],minor_type=s['소분류'],
                evidence_url='https://stat.molit.go.kr/portal/api/apiList.do',source_api='https://stat.molit.go.kr/portal/openapi/service/rest/getList.do',
                verification_status='SOURCE_CONTENT_CHECKED',exclude_from_project_totals=True,
                unit_basis='공식 유형별 통계. 다가구 동수·가구수와 소계·총계는 대안 기준이므로 서로 합산 금지',
                original_file=BATCH+'/'+plan['statistics']['file'],original_sha256=plan['statistics']['sha256'])
            row,outcome=put('housing_type_stat','molit_statistics',key,value,'TYPE_STAT_CAPTURE')
            output['statistic_rows'].append(dict(id=row.entity_id,outcome=outcome))
        label=plan['definition']['label'];value=dict(sample_kind='collection_research',name='A04 서울 일반주택=비아파트 유형 대응 및 착공 증가율',
            base_date='2026-10-21',source_date='2026-10-16',review_label=label,checked_source_type='NON_OFFICIAL',
            status='CONFIRMED',review_actor=ACTOR,evidence_url=plan['definition']['url'],
            original_file=BATCH+'/'+plan['definition']['file'],original_sha256=plan['definition']['sha256'],
            verification_scope=plan['definition']['source_scope'],numeric_source_type='OFFICIAL',
            official_numeric_source_ids=[r['id'] for r in output['statistic_rows']],
            breakdown=plan['statistics']['breakdown'],growth_percent=plan['statistics']['rate'],official_rounded_percent=87,
            match_status='APPROX_COMPATIBLE',classification_basis='연합뉴스의 일반주택(비아파트) 명시와 정부 별첨의 APT/일반 구분을 대조. 다가구 동수 기준 총계에서 아파트를 제외',
            exclude_from_project_totals=True,facts=[])
        r,outcome=put('collection_research','external_officer',BATCH+':A04-definition',value,'OFFICER_TYPE_CONFIRMED')
        output['definition']=dict(id=r.entity_id,outcome=outcome,label=label)
        assert protect(db)==before,'unapproved fields changed'
    output.update(protected_project_quantities_and_policy_links=True,official_new_recruitment_partial=245+209,
        source_type_stat_count=len(rows),start_growth_percent=plan['statistics']['rate'])
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if args.prepare:prepare(Path(__file__).resolve().parents[1])
    elif args.apply:
        folder=Path('/app/data')/BATCH;plan=json.loads((folder/'application_plan.json').read_text());result=apply(folder,plan)
        file='applied.json' if any(r['document_outcome']!='unchanged' for r in result['lh']) else 'idempotence.json'
        (folder/file).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='statistic_rows'},ensure_ascii=False))
