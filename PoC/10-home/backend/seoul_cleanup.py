"""Public Seoul redevelopment roster and dated history, matched at collection time."""
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .api_samples import today

URL='https://cleanup.seoul.go.kr/cleanup/bsnssttus/lscrMainIndx.do'


def address_key(value):
    text=re.sub(r'서울특별시|서울시|번지|일대|일원|\s+','',str(value or ''))
    # Representative parcel only; the area may contain additional parcels.
    m=re.search(r'([가-힣0-9]+(?:동\d*가|동|가))([0-9]+(?:-[0-9]+)?)',text)
    return m.group(0) if m else None


def parse_roster(body):
    soup=BeautifulSoup(body,'html.parser');rows=[]
    for tr in soup.select('tr'):
        cells=tr.find_all('td',recursive=False)
        if len(cells)<10:continue
        values=[c.get_text(' ',strip=True) for c in cells]
        link=re.search(r"cafeOpenPopup\('([a-zA-Z0-9_-]+)'\)",str(cells[-1]))
        if not values[0].isdigit() or not link:continue
        rows.append(dict(source_object_id=link[1],name=values[3],municipality=values[1],
            address='서울특별시 '+values[1]+' '+values[4],source_stage=values[5],business_type=values[2],
            evidence_url='https://cleanup.seoul.go.kr/cafe/mainIndx.do?cafeUrl='+link[1]))
    if not rows:raise ValueError('서울 정비사업 목록 schema 또는 접근 응답 변경')
    return rows


def matches(project, row):
    if project.get('region')!='서울특별시' or project.get('municipality')!=row['municipality']:return False
    pa,sa=address_key(project.get('address')),address_key(row['address'])
    if pa==sa and pa:return True
    # Without a parcel, retain only long distinctive names; numeric blocks must agree.
    name=re.sub(r'\s+','',project['name']);other=re.sub(r'\s+','',row['name'])
    return (len(name)>=4 or len(name)>=3 and any(c.isdigit() for c in name)) and bool(re.search(re.escape(name)+r'(?!\d)',other))


def parse_history(body, reference):
    soup=BeautifulSoup(body,'html.parser');facts=[]
    definitions={
        '정비구역지정':('BUSINESS',{'지정','(변경)지정','지정고시','(변경)지정고시'}),
        '조합설립인가':('BUSINESS',{'인가','(변경)인가','인가고시','(변경)인가고시'}),
        '사업시행인가':('APPROVAL',{'인가','(변경)인가','인가고시','(변경)인가고시'}),
        '착공신고':('CONSTRUCTION',{'신고','신고수리','착공신고','(변경)신고','(변경)신고수리'}),
        '일반분양승인':('SUPPLY',{'승인','(변경)승인','승인고시','(변경)승인고시'}),
        '준공인가':('CONSTRUCTION',{'인가','(변경)인가','인가고시','(변경)인가고시'})}
    if not soup.select('li.foldings-li'):raise ValueError('정비사업 추진경과 schema 변경')
    for section in soup.select('li.foldings-li'):
        heading=section.select_one('.foldings-in-wrap span')
        label=heading.get_text(strip=True) if heading else ''
        if label not in definitions:continue
        stage,allowed=definitions[label]
        for item in section.select('.check-list01 > li'):
            stamp=item.select_one('h3.tit')
            if not stamp:continue
            when=re.sub(r'\s+','',stamp.get_text())
            text=item.get_text(' ',strip=True);tag=re.search(r'\[([^\]]+)\]',text)
            from datetime import date
            try:date.fromisoformat(when)
            except ValueError:continue
            if when>reference or not tag or tag[1] not in allowed:continue
            # Approval to offer is distinct from an actual recruitment notice.
            kind='DOCUMENT' if stage=='SUPPLY' else 'ACTUAL'
            facts.append(dict(stage=stage,kind=kind,date=when,event_type=label,
                milestone='COMPLETION' if label=='준공인가' else stage,
                basis='정비사업 정보몽땅 추진경과 · '+label+' ['+tag[1]+'] · 신청·총회일 제외'))
    return facts


def collect_cleanup(source,fetcher,service):
    roster=[];seen=set()
    for page in range(1,21):
        body=fetcher.get(URL,params={'cpage':page,'pageSize':1000})
        current=parse_roster(body)
        for r in current:
            if r['source_object_id'] in seen:raise ValueError('정비사업 목록 페이지 중복')
            seen.add(r['source_object_id']);roster.append(r)
        if len(current)<1000:break
    else:raise ValueError('정비사업 목록 수집 상한 초과')
    projects=[p for p in service.rows('project') if p.get('region')=='서울특별시']
    linked={};ambiguous=[]
    for p in projects:
        candidates=[r for r in roster if matches(p,r)]
        if len(candidates)==1:linked.setdefault(candidates[0]['source_object_id'],[]).append(p['id'])
        elif len(candidates)>1:ambiguous.append(p['id'])
    records=[];errors=[];stamp=today().isoformat()
    for r in roster:
        if r['source_object_id'] not in linked:continue
        facts=[dict(stage='BUSINESS',kind='STATE',date=stamp,basis='서울 공식 사업장 목록 확인 · 원천 진행단계: '+r['source_stage']+' · 조회일이며 실제 사업화일 아님')]
        if any(w in r['source_stage'] for w in ('사업시행인가','관리처분','착공','준공','이전고시','조합해산','조합청산')):
            facts.append(dict(stage='APPROVAL',kind='STATE',date=stamp,method='STAGE_INFERENCE',basis='원천 진행단계 '+r['source_stage']+'에서 승인 도달 확인 · 개별 사건일은 추진경과 확인'))
        history_url=None;error=None
        try:
            page=BeautifulSoup(fetcher.get(r['evidence_url']),'html.parser')
            link=next((a.get('href') for a in page.select('a[href]') if a.get_text(strip=True)=='추진경과'),None)
            if not link:raise ValueError('추진경과 공개 링크 없음')
            history_url=urljoin(r['evidence_url'],link)
            facts+=parse_history(fetcher.get(history_url),stamp)
        except Exception as exc:
            error=type(exc).__name__+': 추진경과 조회 실패 또는 schema 확인 필요';errors.append(r['source_object_id'])
        payload=dict(r,sample_kind='document_evidence',region='서울특별시',base_date=stamp,date_precision='COLLECTION',
            source_date_label='공개 목록 조회일 · 사건일은 facts에 별도 보존',planned_units=None,
            reported_phase=r['source_stage'],phase_observed_at=stamp,
            matched_project_ids=linked[r['source_object_id']],facts=facts,history_url=history_url,history_error=error,
            verification_status='SOURCE_CONTENT_CHECKED',unit_basis='단계 및 일정 근거 · 기존 사업 물량 유지',
            matching_basis='동일 자치구·대표 지번 또는 고유 사업명 단일 후보 · 담당자 검토')
        records.append(('document_evidence',r['source_object_id'],payload))
    return records,dict(roster_rows=len(roster),matched_projects=sum(map(len,linked.values())),documents=len(records),
        ambiguous_project_ids=ambiguous,history_failures=errors,complete_query=True,complete_population=False,
        scope_note='서울 공개 정비사업 목록 전체 대조. 일치 사업만 추진경과 수집. 단계 날짜 없는 상태는 조회일 관측으로 구분. 일반분양승인은 모집실적 아님')


def reconcile(service):
    from scripts.repair_reviewed_project_cases import explicit_link
    projects={p['id']:p for p in service.rows('project')};counts={}
    for source in service.rows('document_evidence'):
        if source['source_id']!='seoul_cleanup':continue
        for pid in source.get('matched_project_ids',[]):
            if pid not in projects:continue
            outcome=explicit_link(service,projects[pid],source,source['facts'],source['matching_basis'])
            if outcome=='preserved':
                from .db import Revision,Audit,entity_id,upsert_revision
                from sqlalchemy import select,text
                key=pid+':'+source['id'];eid=entity_id('evidence_bridge','cross_source',key)
                with service.sessions.begin() as db:
                    if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019081)'))
                    old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
                    # Same stored identity only. Never overwrite an officer's chosen edition.
                    if old and old.payload.get('status')=='REVIEW' and not old.payload.get('reviewed') and old.payload.get('source_revision_no',0)<source['revision_no']:
                        payload=dict(old.payload,source_revision_no=source['revision_no'],facts=source['facts'],base_date=today().isoformat())
                        row,_=upsert_revision(db,'evidence_bridge','cross_source',key,payload,'seoul_cleanup_refresh')
                        db.add(Audit(entity_id=row.entity_id,action='EVIDENCE_SOURCE_REFRESH',before=old.payload,after=payload))
                        outcome='refreshed'
            counts[outcome]=counts.get(outcome,0)+1
    return counts
