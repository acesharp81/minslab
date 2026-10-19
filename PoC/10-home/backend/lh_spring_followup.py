"""Reviewed 2026 LH direct-development notices; plans are never actual starts."""
import re
from .lh_policy_followup import POLICY, physical_key

FEB_URL='https://www.lh.or.kr/galleryDownload.es?bid=0003&list_no=11981&seq=2'
MAY_URL='https://www.lh.or.kr/galleryDownload.es?bid=0003&list_no=12047&seq=2'
# The February notice explicitly identifies the January round as a 9·7 conversion.
# The May appendix identifies its six blocks; subsequent rounds need separate review.
REVIEWED=[('오산오산','1',366),('인천검단','AA31',766),('인천영종','A57',272),
          ('인천영종','A63',293),('양주회천','A4',536),('양주회천','A23',636)]


def parse_plans(pages, policy_pages):
    policy=re.sub(r'\s+','', '\n'.join(policy_pages))
    if not all(x in policy for x in ('9.7대책','직접시행으로전환','총4개지구6개','연내착공')):
        raise ValueError('LH 1차 공모의 9·7 정책 근거 변경')
    text='\n'.join(pages);compact=re.sub(r'\s+','',text)
    if not all(x in compact for x in ('2026.5.29.', '민간사업자선정을마쳤다', '연내착공')):
        raise ValueError('LH 공모 판본·계획 근거 변경')
    table=pages[-1];rows=[]
    pattern=r'^\s*(?:[123]\s+)?(오산오산|인천검단|인천영종|양주회천|서울도봉01|평택고덕|안산장상|성남복정1|고양창릉|양주고읍|화성동탄|수원당수2?)\s+([A-Z]+-?\d+|1)\s+(?:60이하/60-85|60-85|60이하)\s+([\d,]+)\b'
    for m in re.finditer(pattern,table,re.M):
        district,block,units=m[1],m[2].replace('-',''),int(m[3].replace(',',''))
        idx=len(rows);region='인천광역시' if district.startswith('인천') else '서울특별시' if district.startswith('서울') else '경기도'
        city=next((x for x in ('오산시','양주시','평택시','안산시','성남시','고양시','화성시','수원시') if district.startswith(x[:-1])), '도봉구' if region=='서울특별시' else '중구' if district=='인천영종' else '서구')
        explicit=idx<6 and (district,block)==REVIEWED[idx][:2]
        rows.append(dict(sample_kind='agency_plan',name=district+' '+block,district=district,block=block,
            region=region,municipality=city,units=units,planned_units=units,developer='LH',
            source_object_id='12047:'+district+':'+block,source_date='2026-05-29',base_date='2026-05-29',date_precision='DAY',
            evidence_url=MAY_URL+'#page=2',policy_evidence_url=FEB_URL+'#page=1',source_page=2,
            policy_relationship='EXPLICIT_FIRST_ROUND_907' if explicit else 'FOLLOWUP_SCOPE_REVIEW',
            policy_mapping_status='UNMAPPED',proposed_policy=POLICY if explicit else 'UNASSIGNED',
            start_plan_year=2026 if explicit else None,
            facts=[dict(stage='CONSTRUCTION',kind='PLAN',date='2026년',precision='YEAR',units=units,
                basis='LH 2026.05.29: 1차 6개 블록 4월 사업자 선정 완료·연내 착공 목표')] if explicit else [],
            source_excerpt=m[0].strip(),unit_basis='LH 상반기 공모계획의 블록 전체 호수 · 실제 착공 아님'))
    total=re.search(r'소계\s+21개\s*블록\s+([\d,]+)호',table)
    if len(rows)!=21 or not total or sum(r['units'] for r in rows)!=int(total[1].replace(',','')):
        raise ValueError('LH 21개 블록 표 추출·합계 검증 실패')
    if [(r['district'],r['block']) for r in rows[:6]]!=[r[:2] for r in REVIEWED]:
        raise ValueError('LH 1차 공모 6개 블록 구성 변경')
    return rows


def review_key(row):
    return physical_key(row) or ((row.get('region'),row.get('district'),str(row.get('block')))
        if row.get('district') and str(row.get('block','')).isdigit() else None)


def admit_reviewed(service, apply=False):
    from sqlalchemy import select, text
    from .db import Revision, Mapping, ProgramMapping, Audit, upsert_revision, entity_id
    from .collectors import urban_project
    actor='담당자 대행 · 최종 검증 사용자 지시 2026-10-19'
    result=dict(applied=apply,actor=actor,projects=[])
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019193)'))
        allrows=db.scalars(select(Revision).where(Revision.superseded_at.is_(None),Revision.kind.in_(['agency_plan','project']))).all()
        sources={r.payload.get('source_object_id'):r for r in allrows if r.kind=='agency_plan' and r.source_id=='lh_policy_followup'}
        projects=[r for r in allrows if r.kind=='project']
        pg=db.scalar(select(ProgramMapping).where(ProgramMapping.name=='LH 직접시행 전환·토지이용 효율화',ProgramMapping.policy_id==POLICY,ProgramMapping.status=='CONFIRMED'))
        if not pg:raise ValueError('승인 프로그램 없음')
        todo=[]
        for district,block,units in REVIEWED:
            key='12047:'+district+':'+block;src=sources.get(key)
            if not src or src.payload.get('units')!=units or src.payload.get('policy_relationship')!='EXPLICIT_FIRST_ROUND_907' or src.payload.get('start_plan_year')!=2026:
                raise ValueError('검토된 원천 판본 변경: '+key)
            p=src.payload;pid=entity_id('project','lh_policy_followup','reviewed:'+key)
            same=[r for r in projects if review_key(r.payload)==review_key(p)]
            if any(r.entity_id!=pid for r in same):raise ValueError('동일 블록 중복 검토 필요: '+key)
            basis=(actor+' · LH 2026.02.12 PDF 1쪽: 9·7 직접시행 전환 1월 공모 4개 지구·6개 블록. '
                'LH 2026.05.29 PDF 2쪽: 1차 6개 블록 명세·호수 및 4월 사업자 선정 완료. '
                f'{district} {block} {units}호를 지역·지구·블록으로 기존 전체 원장과 대조; 중복 없음. '
                '직접시행 전환 프로그램에 연결. 연내 착공은 계획이며 실제 착공 확인 아님.')
            item=dict(id=pid,name=p['name'],units=units,source_id=src.entity_id,program=pg.name,program_id=pg.id,basis=basis,evidence_url=p['evidence_url'])
            if same:
                mapping=db.scalar(select(Mapping).where(Mapping.project_id==pid))
                if not mapping or mapping.status!='CONFIRMED' or mapping.policy_id!=POLICY or mapping.program_id!=pg.id or same[0].payload.get('planned_units')!=units:
                    raise ValueError('기존 담당자 판정 보존 필요: '+pid)
                result['projects'].append(dict(item,result='existing_preserved'));continue
            todo.append((key,src,p,item))
        for key,src,p,item in todo:
            if not apply:result['projects'].append(dict(item,result='proposed'));continue
            payload=urban_project(p['name'],p['municipality'],p['region'],p['units'],POLICY,'2026-05-29',pg.name)
            payload.update(district=p['district'],block=p['block'],developer='LH',tenure='공공주택 · 세부유형 확인 필요',
                evidence_url=p['evidence_url'],policy_evidence_url=p['policy_evidence_url'],source_object_id='reviewed:'+key,
                source_reference_id=src.entity_id,source_reference_revision=src.revision_no,source_document_sha256=p['original_sha256'],
                mapping_basis=item['basis'],start_plan_year=2026,schedule_basis='LH 공모: 2026년 연내 착공 목표',
                facts=[],unit_basis='LH 공모 블록 전체 호수 · 담당자 대행 채택',registration_set='FINAL_REVIEW_20261019')
            row,_=upsert_revision(db,'project','lh_policy_followup','reviewed:'+key,payload,'final-review-20261019')
            db.add(Mapping(project_id=row.entity_id,policy_id=POLICY,program_id=pg.id,status='CONFIRMED',revision_no=1,basis=item['basis'],evidence_url=FEB_URL))
            db.add(Audit(entity_id=row.entity_id,action='MAPPING_REVIEW',before={},after=dict(item,actor=actor,policy_id=POLICY,status='CONFIRMED')))
            bridge=dict(project_id=row.entity_id,name=p['name'],region=p['region'],source_entity_id=src.entity_id,source_revision_no=src.revision_no,
                evidence_source_id=src.source_id,source_id=src.source_id,source_name=p['name'],evidence_url=p['evidence_url'],units=p['units'],
                facts=p['facts'],status='CONFIRMED',reviewed=True,review_actor=actor,relation_type='EXPLICIT_POLICY_FOLLOWUP_BLOCK',basis=item['basis'],base_date='2026-10-19')
            b,_=upsert_revision(db,'evidence_bridge','cross_source',row.entity_id+':'+src.entity_id,bridge,'final-review-20261019')
            db.add(Audit(entity_id=b.entity_id,action='DELEGATED_PLAN_LINK_CONFIRMED',before={},after=bridge))
            result['projects'].append(dict(item,result='added'))
    return result
