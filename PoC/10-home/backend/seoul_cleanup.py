"""Public Seoul redevelopment roster and dated history, matched at collection time."""
import re
import hashlib
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .api_samples import today

URL='https://cleanup.seoul.go.kr/cleanup/bsnssttus/lscrMainIndx.do'


def parse_overview(body):
    soup=BeautifulSoup(body,'html.parser');components={};tables=[];partial={}
    for table in soup.select('table'):
        caption=table.caption.get_text(' ',strip=True) if table.caption else ''
        if caption not in ('주택공급계획 분양','주택공급계획 임대'):continue
        tables.append(dict(caption=caption,text=table.get_text(' ',strip=True)))
        values=[]
        for tr in table.select('tr'):
            cells=tr.find_all('td',recursive=False)
            if not cells:continue
            if len(cells)!=9:continue
            raw=[c.get_text(strip=True).replace(',','') for c in cells]
            # Column 4 is apartment-building count, never a household count.
            total=int(raw[4]) if raw[4].isdigit() else None
            parts=[int(v) for v in raw[5:8]] if all(v.isdigit() for v in raw[5:8]) else []
            partial['분양' if caption.endswith('분양') else '임대'] = dict(
                reported_total=total,area_band_units=[int(v) if v.isdigit() else None for v in raw[5:8]],
                missing_band_indices=[i for i,v in enumerate(raw[5:8]) if not v.isdigit()],
                complete=bool(parts))
            if total is not None and parts and total!=sum(parts):raise ValueError('정비사업 개요 세대수 합계 충돌')
            if total is not None or parts:values.append(total if total is not None else sum(parts))
        if len(values)==1:components['분양' if caption.endswith('분양') else '임대']=values[0]
    return dict(housing_plan_components=components,housing_plan_partial_components=partial,
        housing_plan_total=sum(components.values()) if len(components)==2 else None,
        housing_plan_tables=tables,overview_date_status='UNDATED_PLAN',
        overview_scope_note='사업개요의 분양·임대 계획. 기준 판본·변경일 미확정으로 착공·승인 실적 물량에 전용하지 않음')


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
    stamp=today().isoformat()
    # Preserve the discovered roster even when no managed project matches it.
    # This exposes missing projects instead of silently discarding them.
    records=[('renewal_roster',r['source_object_id'],dict(r,sample_kind='renewal_roster',region='서울특별시',
        base_date=stamp,date_precision='COLLECTION',policy_candidate_only=True,proposed_policy='UNASSIGNED',facts=[],
        unit_basis='정비사업 공개 명부 · 개별 사건일·실적 물량과 구분')) for r in roster]
    errors=[];overview_errors=[]
    # Discover active construction outside the existing managed-project list.
    # Bounded, resumable visits avoid a closed loop of only known projects.
    previous=service.latest_collection_stats(source['id'])
    seen_discovery=set(previous.get('discovery_checked_ids',[]))
    unlinked=[r for r in roster if r['source_object_id'] not in linked
              and any(s in r['source_stage'] for s in ('사업시행인가','관리처분','착공'))]
    pending=[r for r in unlinked if r['source_object_id'] not in seen_discovery]
    if not pending:
        seen_discovery=set();pending=unlinked
    discovery_ids={r['source_object_id'] for r in sorted(pending,key=lambda r:r['source_object_id'])[:10]}
    for r in roster:
        if r['source_object_id'] not in linked and r['source_object_id'] not in discovery_ids:continue
        facts=[dict(stage='BUSINESS',kind='STATE',date=stamp,basis='서울 공식 사업장 목록 확인 · 원천 진행단계: '+r['source_stage']+' · 조회일이며 실제 사업화일 아님')]
        if any(w in r['source_stage'] for w in ('사업시행인가','관리처분','착공','준공','이전고시','조합해산','조합청산')):
            facts.append(dict(stage='APPROVAL',kind='STATE',date=stamp,method='STAGE_INFERENCE',basis='원천 진행단계 '+r['source_stage']+'에서 승인 도달 확인 · 개별 사건일은 추진경과 확인'))
        history_url=None;error=None;overview={}
        try:
            page=BeautifulSoup(fetcher.get(r['evidence_url']),'html.parser')
            overview_link=next((a.get('href') for a in page.select('a[href]') if a.get_text(strip=True)=='사업개요'),None)
            if overview_link:
                try:
                    overview_url=urljoin(r['evidence_url'],overview_link);body=fetcher.get(overview_url)
                    overview=dict(parse_overview(body),overview_url=overview_url,overview_sha256=hashlib.sha256(body).hexdigest(),overview_original_file='raw/'+fetcher.manifest[-1]['file'])
                except Exception:overview_errors.append(r['source_object_id'])
            link=next((a.get('href') for a in page.select('a[href]') if a.get_text(strip=True)=='추진경과'),None)
            if not link:raise ValueError('추진경과 공개 링크 없음')
            history_url=urljoin(r['evidence_url'],link)
            facts+=parse_history(fetcher.get(history_url),stamp)
        except Exception as exc:
            error=type(exc).__name__+': 추진경과 조회 실패 또는 schema 확인 필요';errors.append(r['source_object_id'])
        payload=dict(r,sample_kind='document_evidence',region='서울특별시',base_date=stamp,date_precision='COLLECTION',
            source_date_label='공개 목록 조회일 · 사건일은 facts에 별도 보존',planned_units=None,
            reported_phase=r['source_stage'],phase_observed_at=stamp,
            matched_project_ids=linked.get(r['source_object_id'],[]),facts=facts,history_url=history_url,history_error=error,
            discovery_candidate=r['source_object_id'] in discovery_ids,
            verification_status='SOURCE_CONTENT_CHECKED',unit_basis='단계 및 일정 근거 · 기존 사업 물량 유지',
            matching_basis='동일 자치구·대표 지번 또는 고유 사업명 단일 후보 · 담당자 검토',**overview)
        records.append(('document_evidence',r['source_object_id'],payload))
        if r['source_object_id'] in discovery_ids and error is None and r['source_object_id'] not in overview_errors:
            seen_discovery.add(r['source_object_id'])
    return records,dict(roster_rows=len(roster),roster_records=len(roster),matched_projects=sum(map(len,linked.values())),documents=sum(k=='document_evidence' for k,_,_ in records),
        ambiguous_project_ids=ambiguous,history_failures=errors,overview_failures=overview_errors,complete_query=True,complete_population=False,
        discovery_candidates=len(unlinked),discovery_visited=len(discovery_ids),discovery_checked_ids=sorted(seen_discovery),
        discovery_remaining=sum(r['source_object_id'] not in seen_discovery for r in unlinked),
        scope_note='서울 공개 명부 전체 대조. 기존 사업 및 미등록 사업시행인가·관리처분·착공 후보 10개씩 상세 순환 조회. 날짜 없는 상태는 조회일 관측. 일반분양승인은 모집실적 아님')


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
