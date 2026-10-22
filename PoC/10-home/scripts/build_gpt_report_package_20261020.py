"""Build the current GPT reporting handoff from a read-only operational snapshot."""
import csv
from collections import Counter,defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'data/gpt-report-20261020'
BASE=ROOT/'docs/analysis/presentation_final_20261020'
OUT=ROOT/'docs/analysis/gpt_report_20261020'
OFFICIAL='https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=87948&fileTy=ATTACH&fileNo=3'
SPEECH='https://www.korea.kr/briefing/policyBriefingView.do?newsId=156785506'
MONTHLY='https://www.index.go.kr/unity/potal/FileDown.do?seq=17704&id=1229&div=1'


def read(path):return json.loads(path.read_text())
def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str))
def csvread(path):
    with path.open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def csvwrite(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def table(heads,rows):
    fmt=lambda x:str(x if x is not None else '未확보').replace('|',' / ').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(heads)+' |','| '+' | '.join(['---']*len(heads))+' |']+['| '+' | '.join(fmt(x) for x in row)+' |' for row in rows])
def num(x):return f'{x:,}' if isinstance(x,(int,float)) else '미측정' if x is None else str(x)
def pick(row,keys):return {k:row[k] for k in keys if k in row}


def main():
    OUT.mkdir(parents=True,exist_ok=True);e=OUT/'evidence';e.mkdir(exist_ok=True)
    summary=read(WORK/'summary.json');projects=read(WORK/'projects.json');model=read(WORK/'model.json');sources=read(WORK/'sources.json')
    profiles={p['project_id']:p for p in read(WORK/'project_profile.json')};schedules=read(WORK/'execution_schedule.json');bridges=read(WORK/'evidence_bridge.json');docs=read(WORK/'document_evidence.json')
    ps={p['id']:p for p in projects};cohorts=model['portfolio_cohorts'];cohort_by_source={pid:c for c in cohorts for pid in c['source_ids']};source_by={s['id']:s for s in sources}
    assert summary['metrics']['CONSTRUCTION']['actual']==79884 and summary['metrics']['SUPPLY']['actual']==58541
    # Keep the established evidence/projects.json and evidence/model.json layout,
    # while omitting repeated plot snapshots and whole HTML text.
    project_keys=['id','name','region','municipality','source_municipality','district','block','tenure','planned_units','units','source_id','base_date','source_date','evidence_url','policy_evidence_url','mapping','start_actual_date','start_plan_date','completion_plan_date','move_in_month','source_supply_label','source_move_in_label','notice_move_in_month','rows','dates','warnings','unit_basis','schedule_basis','source_revision_id','source_payload_hash','revision_no','construction_start_evidence','address','latitude','longitude','source_values','identity_resolution_status','identity_source_id','identity_evidence_url','identity_exclusions','historical_schedule','land_area_sqm','building_count','floors_above','quantity_scope','unit_basis','official_supply_plan_units']
    write(e/'projects.json',[pick(p,project_keys) for p in projects])
    write(e/'model.json',dict(reference_date='2026-10-20',format='COMPACT_POLICY_MODEL',plan=model['plan'],portfolio_cohorts=cohorts,excluded_source_ids=model['excluded_source_ids'],measurement_contract=model.get('measurement_contract'),metrics=summary['metrics'],note='Repeated plot snapshots/geometry omitted; cohort IDs, events and schedules retained.'))
    for name in ['summary.json','project_profile.json','execution_schedule.json','evidence_bridge.json','agency_plan.json','statistic_reference.json','programs.json','record_counts.json','source_connection.json']:
        shutil.copy2(WORK/name,e/name)
    write(e/'sources.json',sources)
    doc_keys=['id','name','source_id','source_object_id','sample_kind','base_date','source_date','published_at','evidence_url','attachment_url','original_sha256','original_file','facts','reference_facts','planned_units','units','offered_units','region','municipality','district','block','tenure','scope_breakdown','complex_scope_breakdown','complex_total_units','notice_round','verification_status','status','reviewed','review_label','checked_source_type','officer_review_status','review_decision','confirmed_scope','matched_project_ids','actual_admission_status','official_actual_verified','exclude_from_project_totals','basis','source_revision_id','revision_no','warnings','publisher','document_title','published_month','source_page','source_page_index','identity','identity_resolution_status','identity_source_id','identity_evidence_url','identity_correction','not_same_project','scope_caution','superseded_hypothesis','unverified_fields','official_corroboration']
    write(e/'document_evidence.json',[pick(d,doc_keys) for d in docs])
    stats=[r for r in read(WORK/'statistic.json') if str(r.get('statistic_period','')).startswith('2026')]
    write(e/'statistic_monthly_2026.json',stats)
    # Official 32-line plan comparison. Original plan columns are retained as
    # explicitly dated baseline fields, never relabelled as fresh measurements.
    rows=[];base_rows=csvread(BASE/'comparison_32.csv')
    yeon=next(p for p in projects if p['name']=='연남동 공공임대주택' and p['mapping']['status']=='CONFIRMED')
    for old in base_rows:
        pid=old['project_id'] or (yeon['id'] if old['number']=='32' else None)
        if not pid or pid not in ps:raise ValueError('Current official project absent: '+old['official_name'])
        p=ps[pid];c=cohort_by_source.get(pid);official=int(old['official_units']);capacity=p['planned_units']
        assert p['mapping']['status']=='CONFIRMED' and p['mapping']['policy_id']=='POL_2025_0907'
        direct=[]
        for link in bridges:
            if link['project_id']!=pid or link.get('status')!='CONFIRMED':continue
            for f in link.get('facts',[]):
                if f.get('stage')=='SUPPLY' and f.get('kind')=='ACTUAL' and f.get('notice_round','MAIN')=='MAIN' and not f.get('scope_partial') and f.get('date','9999')<='2026-10-20':
                    direct.append(dict(date=f['date'],units=f.get('units'),url=link['evidence_url'],source_type=link.get('checked_source_type') or f.get('source_type') or 'OFFICIAL_OR_STORED_SOURCE',label=link.get('review_label') or link.get('source_name')))
        latest=max(direct,key=lambda f:(f['date'],f['units'] or 0),default={})
        reason=old['reason']
        if old['number']=='1':reason='전체1305호 일치. 기존 잔여계획215호와 달리 10월16일 본청약1305호를 비공식 원문으로 담당자 확인 완료. 사전당첨592+특별566+일반147. 기존8월31일 공급 추정일 보정.'
        if old['number']=='25':reason='전체350호 일치. LH10월19일 최초 행복주택 모집 확인 완료·실제 공급 반영. 공사·임대 원천 동일 현장350호를 한 번만 집계.'
        if old['number']=='32':reason='정부4분기 계획8호 연결 유지. SH2025년11월 업무보고79쪽에서 독립 공공임대8호·대지277㎡·1동5층 확인; 연희96호 일부 가설 철회. 당시2025-11 착공·2026-10 준공은 월 단위 과거계획; 실제 착공·준공·모집 미확인. SH근거 https://mas.smc.seoul.kr/attach/record/SEOUL/appendix/a11/A0069855.pdf#page=79'
        row=dict(number=int(old['number']),official_name=old['official_name'],type=old['type'],official_units=official,
            project_id=pid,cohort_id=c['id'] if c else None,project_name=p['name'],project_units=capacity,
            count_once_units=capacity if int(old['count_once_units'] or 0)>0 or old['number']=='32' else 0,
            match_kind='INDEPENDENT_PROJECT_AND_OFFICIAL_PLAN_MATCHED' if old['number']=='32' else old['match_kind'],same_quantity=(capacity==official and old['match_kind']!='COMBINED'),mapping_status=p['mapping']['status'],
            baseline_source_supply_units=old['source_supply_units'],baseline_source_supply_plan=old['source_supply_plan'],baseline_quarter_match=old['source_quarter_match'],baseline_note='이전 제출본의 원천 계획 대조; 최신 실제 모집과 구별',
            latest_confirmed_recruitment_date=latest.get('date'),latest_confirmed_recruitment_units=latest.get('units'),latest_confirmed_recruitment_source=latest.get('label'),latest_confirmed_recruitment_source_type=latest.get('source_type'),latest_confirmed_recruitment_url=latest.get('url'),
            current_management_supply_schedule=next((s['due_date'] for s in schedules if s['project_id']==pid and s['stage']=='SUPPLY' and s.get('status')!='RELEASED'),None),
            official_evidence_url=OFFICIAL+('#page=5' if old['type']=='공공분양' else '#page=6'),reason=reason)
        rows.append(row)
    sums={typ:dict(official=sum(r['official_units'] for r in rows if r['type']==typ),home_unique=sum(r['count_once_units'] for r in rows if r['type']==typ)) for typ in ['공공분양','공공임대']}
    verified=dict(official_rows=len(rows),identity_matched_rows=len(rows),official_units=sum(r['official_units'] for r in rows),matched_official_units=sum(r['official_units'] for r in rows),identity_coverage_percent=100,
        unique_management_cohorts=len({r['cohort_id'] or r['project_id'] for r in rows}),home_unique_units=sum(r['count_once_units'] for r in rows),
        exact_individual_quantity_rows=sum(r['same_quantity'] for r in rows),exact_individual_official_units=sum(r['official_units'] for r in rows if r['same_quantity']),by_type=sums,
        caveat='Identity/plan linkage coverage only; not independent supply verification, timing accuracy, complete public collection coverage, or 32 unique projects.')
    assert (verified['official_rows'],verified['official_units'],verified['home_unique_units'])==(32,14731,14807)
    assert sums['공공임대']['home_unique']==4648
    csvwrite(OUT/'comparison_32.csv',rows);write(OUT/'comparison_32.json',dict(summary=verified,rows=rows))
    # Current named construction cohorts, exactly the same capped aggregation as
    # the existing comparison export, recomputed from the current snapshot.
    groups=['고양창릉','인천계양','하남교산','남양주왕숙2','부천대장','중계본동','흑석11','신림2'];named=[]
    for c in cohorts:
        compact=re.sub(r'\s','',c['name']);g=next((g for g in groups if g in compact),None)
        if not g:continue
        events=[ev for ev in c['events'] if ev['stage']=='CONSTRUCTION' and ev.get('status','ACTUAL')=='ACTUAL' and ev['event_date']<='2026-10-20']
        units=lambda es:min(c['units'],max((ev.get('units') if ev.get('units') is not None else c['units'] for ev in es),default=0))
        named.append(dict(group=g,id=c['id'],name=c['name'],capacity=c['units'],current_cumulative=units(events),event_date_in_2026=units([ev for ev in events if ev['event_date'].startswith('2026')]),source_ids=c['source_ids'],events=events))
    totals={g:dict(records=sum(r['group']==g for r in named),cumulative=sum(r['current_cumulative'] for r in named if r['group']==g),managed_2026=sum(r['event_date_in_2026'] for r in named if r['group']==g)) for g in groups}
    descriptions=[
      ('高양창릉'.replace('高','고'),'약2,300',2306,'개략량 부합','S3 1282+S4 1024. LH 원천 착공일2026-04-15/03-31','OFFICIAL_SOURCE',None),
      ('인천계양','약2,300',2342,'전체 공사량 기준 개략량 부합','A6 663+A17 전체463+A16 434+A18 782. A17임대154 포함한 비교용 전체량; 현재 차트에 별도154 가산한 값은 아님','MIXED_OFFICIAL_AND_OFFICER_CONFIRMED_NONOFFICIAL',154),
      ('하남교산','약1,100',1115,'수량 부합 / 기간 기준 별도 확인','A2 1115와 약1100은 부합. 원천 착공2024-10-30과 공식 올해 표현의 기준 차이는 남음. 수량만으로 A3로 변경하지 않음','OFFICIAL_SOURCE_DIFFERENT_EVENT_YEAR',None),
      ('남양주왕숙2','약1,100',1063,'개략량 부합','A6 510+A7 553의 상반기 착공 담당자 확인 완료. 계약1082와19호 상충 보존','OFFICER_CONFIRMED_NONOFFICIAL',None),
      ('부천대장','약600',574,'개략량 부합','A9 상반기 착공 담당자 확인 완료. A2/A12 1343은 별도 블록','OFFICER_CONFIRMED_NONOFFICIAL',None),
      ('중계본동','약3,100',3178,'개략 규모 근접','독립 서울시 기착공 상태·규모 확인. 정확한 착공일은 미확보. 3178→3100을 엄밀한 백호 반올림이라고 단정하지 않음','OFFICIAL_OBSERVED_START',None),
      ('흑석11','서면약1,500 / 발언약2,500',1515,'서면 개략량 부합','독립 서울시 실제 착공2026-02-06. 발언과985호 차이는 공식 출처 상충','OFFICIAL_SOURCE',None),
      ('신림2','약1,400',1430,'개략량 부합','분양1246+임대184. 관악구 실제 착공2026-05-06','OFFICIAL_SOURCE',None)]
    starts=[dict(project=g,official_approx=off,home_comparison_units=u,home_policy_cumulative=totals[g]['cumulative'],home_managed_event_2026=totals[g]['managed_2026'],assessment=assess,reason=reason,verification=kind,scope_adjustment_not_added_to_chart=scope,official_source_url=OFFICIAL+'#page=4') for g,off,u,assess,reason,kind,scope in descriptions]
    csvwrite(OUT/'comparison_start_8.csv',starts);write(OUT/'comparison_start_8.json',dict(rows=starts,cohorts=named))
    # Same-region, same-period official statistics, kept apart from policy sums.
    refs=read(WORK/'statistic_reference.json')
    def monthly(metric,regions,end='202608',start='202601'):
        selected=[r for r in stats if r['statistic_metric']==metric and r['region'] in regions and start<=r['statistic_period']<=end]
        keys=[(r['region'],r['statistic_period']) for r in selected]
        assert len(keys)==len(set(keys))
        assert len(selected)==len(regions)*(int(end[-2:])-int(start[-2:])+1)
        return sum(r['units'] for r in selected),selected
    seoul='서울특별시';capital=[seoul,'경기도','인천광역시'];permit=lambda region,freq:next(r for r in refs if r['region']==region and r['statistic_frequency']==freq)
    statistics=[]
    def stat(name,official,value,method,records):
        statistics.append(dict(item=name,official_units=official,home_units=value,match=value==official,scope='전체 주택 지역 통계; 정책 연결 사업 독립 합산 아님',method=method,evidence_urls=' | '.join(sorted({r['evidence_url'] for r in records})),source_record_ids=' | '.join(r['id'] for r in records)))
    stat('서울 1~8월 인허가',39940,permit(seoul,'YTD')['units'],'공식 PDF 누계 레코드 직접 대조',[permit(seoul,'YTD')])
    stat('서울 8월 인허가',11306,permit(seoul,'MONTH')['units'],'공식 PDF 당월 레코드 직접 대조',[permit(seoul,'MONTH')])
    stat('서울 1~7월 인허가',28634,permit(seoul,'YTD')['units']-permit(seoul,'MONTH')['units'],'8월 누계-8월 당월; 별도7월 원문을 독립 확인했다는 뜻은 아님',[permit(seoul,'YTD'),permit(seoul,'MONTH')])
    stat('수도권 1~8월 인허가',96056,sum(permit(r,'YTD')['units'] for r in capital),'3개 시도 YTD 합계',[permit(r,'YTD') for r in capital])
    for title,metric,regions,end,start,expected in [('서울 1~8월 착공','착공',[seoul],'202608','202601',20679),('수도권 1~8월 착공','착공',capital,'202608','202601',86739),('서울 8월 착공','착공',[seoul],'202608','202608',1172),('서울 1~7월 착공','착공',[seoul],'202607','202601',19507),('서울 1~8월 분양승인','분양승인',[seoul],'202608','202601',15962),('서울 1~8월 준공','준공',[seoul],'202608','202601',25630)]:
        v,rs=monthly(metric,regions,end,start);stat(title,expected,v,'저장된 공식 월별 레코드 중복 없이 합산',rs)
    assert all(r['match'] for r in statistics);csvwrite(OUT/'comparison_statistics.csv',statistics)
    sectors=[dict(sector='공공주택',official_approx_units=16200,home_verified_scope='명시5개 지구 누적17230호; 관리일2026년7791호(추정 포함). 같은 모집단의 부문 총계 아님',gap_reason='공공택지14200+도심약2000의 전체 명단과 동일 기간·범위 대조 미완료'),dict(sector='신축매입',official_approx_units=13000,home_verified_scope='해당 정책 프로그램 연결사업0개',gap_reason='매입약정-현장-착공 연계 부족; 건설형 공급계획 수집의 매입/전세 제외와 별개 경로 필요. 우리 수집·연계 공백 포함'),dict(sector='민간정비',official_approx_units=17000,home_verified_scope='명시3개 사업6123호=3178+1515+1430 독립 공식 대조',gap_reason='공식은9월까지 수도권 정비 전체, 명시3건은 부분집합'),dict(sector='기타 일반·민간주택',official_approx_units=47000,home_verified_scope='개별 인허가·착공 원천 보유; 동일 부문 전체 합계 미완결',gap_reason='공공택지 민영/조합/도시개발 등 범주 재분류와 다른 부문 중복 제거 필요'),dict(sector='공공지원 민간임대',official_approx_units=5600,home_verified_scope='해당 정책 프로그램 연결사업0개',gap_reason='공공지원 자격·개별 현장·실제 착공 연계 원장 부족. 명칭에 임대가 있다고 다른 임대자료를 대입하지 않음')]
    csvwrite(OUT/'comparison_sector_5.csv',sectors)
    held=csvread(BASE/'held_candidates_9.csv')
    for r in held:
        names=re.sub(r'\s','',r['사업']);hits=[p for p in projects if names in re.sub(r'\s','',p['name'])]
        r['current_named_project_ids']=' | '.join(p['id'] for p in hits);r['current_snapshot_check']='동명 원천 사업 직접 등록 미확인; 기존 공모·선정 근거의 정책 귀속 후보로 유지' if not hits else ' | '.join(p['mapping']['status'] for p in hits)
    assert sum(int(r['후보계획호수']) for r in held)==6296;csvwrite(OUT/'held_candidates_9.csv',held)
    explicit=csvread(BASE/'explicit_policy_links.csv')
    for r in explicit:
        p=ps.get(r['project_id']);r['current_mapping_status']=p['mapping']['status'] if p else 'GROUP_REFERENCE_ONLY';r['current_policy_id']=p['mapping'].get('policy_id') if p else None;r['current_project_units']=p.get('planned_units') if p else None
        verified_starts=[(f,link) for link in bridges if link['project_id']==r['project_id'] and link.get('status')=='CONFIRMED'
                         for f in link.get('facts',[]) if f.get('stage')=='CONSTRUCTION' and f.get('kind')=='ACTUAL' and f.get('pct') is None and f.get('milestone')!='COMPLETION']
        current_start=max(verified_starts,key=lambda pair:pair[0].get('date') or '',default=None)
        r['original_policy_review_basis']=r['basis']
        r['current_start_verification']=current_start[1].get('review_label') or current_start[1].get('source_name') if current_start else '이번 스냅샷에서 해당 사업의 확인 착공 근거 미확인'
        r['current_start_units']=current_start[0].get('units') if current_start else None
        r['current_start_date_basis']=current_start[0].get('date_basis','EVENT') if current_start else None
        r['current_start_evidence_url']=current_start[1]['evidence_url'] if current_start else None
        if current_start:r['basis']+=' · 이후 착공 확인은 current_start_* 열을 우선하며 원래 검토 당시의 미확인 문구와 구별.'
    block_rows=[r for r in explicit if r['scope']=='EXPLICIT_BLOCK_FOLLOWUP']
    assert len(block_rows)==14 and sum(r['current_project_units'] for r in block_rows)==8031
    csvwrite(OUT/'explicit_policy_links.csv',explicit)
    # A full collection catalogue with current schedule/processing explanations.
    url_rows=[]
    for s in sources:
        op=s['operations'];url_rows.append(dict(id=s['id'],name=s['name'],org=s['org'],url=s['url'],data_type=s.get('data_type'),collection_mode=s.get('collection_mode'),automatic_or_manual=op['mode'],frequency=op['frequency'],last_attempt=s.get('last_attempt'),last_success=s.get('last_success'),status=s['status'],current_source_record_count=s.get('record_count'),discovery=op['discovery'],preprocessing=op['parser'],changes=op['changes']))
    csvwrite(OUT/'source_urls.csv',url_rows)
    # Explicit source manifests and operational receipts, without old narratives.
    for directory,files in {'external_events_20261020':['plan.json','initial-applied.json','applied.json','idempotence.json','api_verification.json','confirmed_events.csv','source_manifest.json'],'nonofficial_confirmed_20261020':['applied.json','supplemental-applied.json','idempotence.json','api_verification.json'],'predecessor_gaps_20261020':['applied.json','partial-scope-applied.json','verification.json'],'three_newtown_final_20261020':['source_manifest.json','changneung_source_rows.json']}.items():
        for filename in files:
            original=ROOT/'docs/analysis'/directory/filename
            if original.exists():
                dest=e/'review_receipts'/directory/filename;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,dest)
    official_pdf=BASE/'evidence/live-sources/official-october.pdf';dest=e/'official/official-october.pdf';dest.parent.mkdir(exist_ok=True);shutil.copy2(official_pdf,dest)
    official_sha=hashlib.sha256(dest.read_bytes()).hexdigest();assert official_sha=='e95a9929b94f9994fe963907a46b90e7761cd26a9811d1b36d7e7988f1ecdc1f'
    # Row-level SH primary source and the completed identity correction.
    identity_dir=ROOT/'docs/analysis/yeonnam_sh_identity_20261020'
    previous_csv=ROOT/'data/yeonnam-sh-20261020/before/comparison_32.csv'
    previous=csvread(previous_csv);now=csvread(OUT/'comparison_32.csv')
    changes=[dict(number=a['number'],fields={k:dict(before=a[k],after=b.get(k)) for k in a if a[k]!=b.get(k)})
             for a,b in zip(previous,now) if a!=b]
    assert len(previous)==len(now)==32 and [c['number'] for c in changes]==['32']
    assert next(r for r in now if r['number']=='32')['project_id']==yeon['id']
    assert next(r for r in now if r['number']=='32')['count_once_units']=='8'
    shutil.copy2(previous_csv,identity_dir/'comparison_32.before.csv')
    write(identity_dir/'comparison_verification.json',dict(status='PASS',unchanged_other_rows=31,changed_rows=changes,
        before_row_32=previous[-1],after_row_32=now[-1],before_csv_sha256=hashlib.sha256(previous_csv.read_bytes()).hexdigest(),
        after_csv_sha256=hashlib.sha256((OUT/'comparison_32.csv').read_bytes()).hexdigest(),
        official_32_summary=verified,additional_units=0,note='Existing 8-unit ID and official plan admission retained. Only identity explanation strengthened. cohort_id is a management group, not a recruitment round.'))
    shutil.copytree(identity_dir,e/'yeonnam_sh_identity_20261020',dirs_exist_ok=True)
    analysis=(ROOT/'docs/HOME_YEONNAM_8_IDENTITY_REVIEW_20261020.md').read_text()
    (OUT/'HOME_YEONNAM_8_IDENTITY_REVIEW_20261020.md').write_text(analysis.replace('analysis/yeonnam_sh_identity_20261020/','evidence/yeonnam_sh_identity_20261020/').replace('analysis/gpt_report_20261020/comparison_32.csv','comparison_32.csv'))
    # Additional exact sources for the presenter and downstream GPT.
    write(OUT/'comparison.json',dict(snapshot=summary,official_32_summary=verified,official_32=rows,start_8=starts,statistics=statistics,sectors=sectors,named_totals=totals))
    write(e/'tests.json',dict(prior_relevant_tests=dict(passed=116,subtests=11),final_scoped_override_regression=dict(passed=60),note='Implementation regression checks, not a statistical dataset accuracy rate; recorded in prior work.'))
    source_counts=Counter(s['status'] for s in sources)
    local_time=lambda value:datetime.fromisoformat(value).astimezone(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    aggregate_table=table(['단계','현재 누적 관리 측정량','12월 말 계획 기준 누적 예상'],[(k,num(summary['metrics'][stage]['actual']),num(summary['metrics'][stage]['year_end'])) for k,stage in [('사업화','BUSINESS'),('인허가','APPROVAL'),('착공','CONSTRUCTION'),('준공','COMPLETION'),('공급·모집','SUPPLY'),('입주','MOVE_IN')]])
    start_table=table(['공식 명시 사업','공식 개략량','HOME 비교용 물량','차트의 지구·사업 누적','판정·비고'],[(r['project'],r['official_approx'],num(r['home_comparison_units']),num(r['home_policy_cumulative']),r['assessment']+' — '+r['reason']) for r in starts])
    plan_table=table(['번호','공식 사업','공식4분기 호수','HOME 사업량','최신 판단'],[(r['number'],r['official_name'],num(r['official_units']),str(r['project_units'])+(' (합본, 1회만 합산)' if r['match_kind']=='COMBINED' else ''),r['reason']) for r in rows])
    stat_table=table(['동일 지역·기간 검증 항목','공식 통계','HOME 보유·재계산','확인 방법'],[(r['item'],num(r['official_units']),num(r['home_units']),r['method']) for r in statistics])
    sector_table=table(['공식 부문','공식 개략량','HOME에서 확인한 범위','남는 차이의 이유'],[(r['sector'],num(r['official_approx_units']),r['home_verified_scope'],r['gap_reason']) for r in sectors])
    held_table=table(['정책 귀속 유보 후보','계획 호수','이미 확보한 내용','유보 근거'],[(r['사업'],num(int(r['후보계획호수'])),r['이미확인한내용'],r['유보이유']) for r in held])
    ops_table=table(['출처·경로','현재 상태·주기','발견·전처리 방식'],[(s['name'],s['status']+' / '+s['operations']['mode']+' / '+s['operations']['frequency'],s['operations']['discovery']+' '+s['operations']['parser']) for s in sources if s['id'] in ['lh_notice','lh_notice_detail','eum_housing_notices','lh_policy_followup','lh_construction','molit_monthly_release','building_general_permit','gh_supply_plan']])
    sources_md='\n'.join(f"- [{r['name']}]({r['url']}) — {r['automatic_or_manual']} / {r['frequency']} / {r['status']}" for r in url_rows)
    master=f'''# HOME 데이터셋·공식자료 비교 — GPT 보고자료 작성용 최신 마스터

기준일: **2026-10-20**. 운영 DB 읽기 전용 추출: {local_time(summary['capture_started_at'])}~{local_time(summary['capture_finished_at'])} **한국시간**. 모든 정책 집계의 업무 기준일은2026-10-20이다.

이 자료는 이전 제출본의 **발표2페이지 + 상세 마스터 + 사업별CSV + evidence/projects.json·model.json + 출처·검증 파일** 구성을 유지하면서, 이후 담당자 확인·외부 근거 보완까지 반영한 새 기준본이다. 이전 패키지의450개 원천 사업, 연남8호 미연결, 착공77,031호, 공급58,195호 등을 최신값으로 사용하지 않는다. 아래 숫자는 출처·기간·범위를 구분해 재현할 수 있도록 묶었다.

## 0. GPT에 요청하는 작업

이 문서와 첨부 CSV/JSON을 근거로, HOME가 공개된 주택정책 자료를 사업 단위로 구조화하고 검증 가능한 데이터셋으로 구축했다는 점을 설명하는 한국어 보고서·발표자료를 작성하라. 첫 페이지는‘공식자료 기준 ↔ HOME’, 둘째 페이지는‘차이 이유와 데이터 신뢰성’으로 구성하고, 상세 근거는 부록으로 제시하라.

확인된 강점은 구체적인 호수·사업명·구성·원문으로 설명한다. **원문 확인된 비공식 근거는‘담당자 확인 완료 - 비공식 자료: 출처’로 채택된 자료**다. 비공식이라는 이유만으로 다시 미확인 후보로 되돌리지 않는다. 확인 범위가 승인·예정·기공식인 경우에는 실제 착공·준공·입주로 확대하지 않는다.

수량이 개략 표현과 부합하는 경우‘개략량 부합’이라고 쓴다. 공급계획 전체 명단에 대응하는 사업을 관리한다는 것과 실제 실적·시기까지 전부 독립 검증했다는 것은 구별한다. 출처가 부족한 원인을 모두‘기관 미공개’나‘수집 시차’로 설명하지 않는다.

## 1. 현재 데이터셋과 최종 집계

| 현재 스냅샷 항목 | 값 | 해석 |
| --- | ---: | --- |
| 등록 수집 원천 | **{summary['registered_sources']}개** | 원천 등록 건수. 전부 수집 완결이라는 뜻은 아님 |
| 현행 원천 객체 판본 | **{num(summary['current_records'])}건** | 통계·인허가·대장·문서 등 여러 자료유형 포함. 사업 수·주택 호수가 아님 |
| 전체 원천별 사업 기록 | **{summary['all_project_source_records']}개** | 같은 실제 현장의 공사·분양·임대 원천이 중복 등장할 수 있음 |
| 9·7 정책에 확인 연결된 원천별 사업 기록 | **{summary['effective_policy_source_records']}개** | 유효 상위 프로그램의 정책 귀속까지 반영한 기록 수 |
| 정책 차트의 중복 제거 관리 묶음 | **{summary['unique_policy_cohorts']}개** | 원천 사업 수와 다름. 복수계약 경고 등 기존 제외 기준 유지 |
| 공식4분기 명세 대응 | **32개 항목 전건 관리 연결** | 합본2개 항목은 같은 관리 묶음에 연결. 독립 실적100%라는 뜻 아님 |

{aggregate_table}

현재 누적에는 과거 착공과 담당자 관리 추정이 포함된다. 예를 들어 사업화151,098호·인허가97,889호는 새로 수집한 공식 사건만의 합이 아니다. 선행 단계 추정 보완으로 사업화+56,880·인허가+9,833이 반영된 기록을 별도로 보존한다. 입주 현재값은‘미측정’이며0호로 바꾸지 않는다. 연말 값은 계획 기준 예상으로 실제 완료 보장이 아니다.

## 2. 발표1페이지 원고 — 공식자료 기준 / HOME

| 공식자료 기준 | HOME 데이터셋 | 설명 가능한 성과 |
| --- | --- | --- |
| 공공분양4분기 **19개 항목·10,083호** | 같은 명단 대응 사업량 **10,159호** | 전건 연결. +76호의 차이를 대장·신길4개 비교군으로 분해 |
| 공공임대4분기 **13개 항목·4,648호** | 연남동8호 포함 대응 사업량 **4,648호** | 사업 규모 합계 일치. 계획 등록·실제 모집·개별 착공 검증은 구별 |
| 공식4분기 공급 명세 **32개 항목·14,731호** | 32개 항목 대응, 중복 제외 **31개 관리 묶음·14,807호** | 명단 대응100%. 물량 차이+76호이며 전체 실적 정확도100%로 부르지 않음 |
| 검단 공공임대 약1,300호 | AA19 **국민991+영구332=1,323호** | 유형별 구성과 정정공고·공사 전체량의 중복 통제를 설명 가능 |
| LH 명시적9·7 후속 공모14개 블록 | 동일 세부 계획 **8,031호** | 해당14개 명세 수량 일치. 왕숙2는 후속 계약 공시와19호 상충도 함께 보존 |
|10월4분기 명단 밖의 별도 공식 관리 사례 | 후속14개8,031+당수C5 490+도심4곳4,058=**19개·12,579호** | 다른 공식자료에서 확인한 사례. 다른 기간·단계의 물량이므로14,731에 합산하지 않음 |
| 서울1~8월 인허가 약4만호 | HOME 공식 지역 통계 **39,940호** | 같은 지역·기간 통계의 개략 발표 규모와 부합 |

**발표 멘트:** “HOME는 정부가 명시한 공급계획32개 항목을 전건 구조화해 대응 사업을 관리하고 있습니다. 임대 명세4,648호는 사업 규모 합계가 일치하며, 분양 명세의76호 차이도 사업별로 추적할 수 있습니다. 검단의 국민·영구임대 구성, 실제 모집공고, 변경 판본까지 연결해 같은 물량을 반복 집계하지 않도록 관리합니다.”

**연남동 최종 보완:** [SH2025년11월 업무보고79쪽](https://mas.smc.seoul.kr/attach/record/SEOUL/appendix/a11/A0069855.pdf#page=79) 원문을 직접 수집·대조해 연남동 공공임대8호가 연희96호와 별개인 점을 확인했다. 기존8호 사업ID를 재사용했으며 이번 보완으로 사업 수·실제 착공·공급을 추가 가산하지 않았다. 당시 착공2025-11·준공2026-10은 월 단위 과거계획으로 보존했다. [상세 분석·전후 검증](HOME_YEONNAM_8_IDENTITY_REVIEW_20261020.md). CSV의 cohort_id는 기존 정책 관리 묶음ID이며 실제 모집공고 회차ID가 아니다.

## 3. 발표2페이지 원고 — 숫자의 차이를 어떻게 설명하는가

| 사례 | 공식자료 ↔ HOME | 확인한 이유·남는 확인 범위 |
| --- | --- | --- |
| 창릉·계양·왕숙2·대장 착공 | 약2300/2300/1100/600 ↔2306/2342/1063/574 | 개략 규모 부합. 계양은 임대 포함 전체 공사량으로 비교; 정부의 정확한 포함 블록은 별도 명세와 구별 |
| 교산 착공 | 약1100 ↔A2 1115 | **수량 부합**. 숫자만으로 블록 오매칭 판정하지 않음. 원천2024년 착공과 올해 발표 산입 기준은 별도 확인 |
| 고덕강일3 공급 | 공식1305 ↔본청약1305 | 비공식 원문으로10월16일 공고 확인 완료. 예전 잔여계획215와 전체 본청약1305의 범위를 구분 |
| 병점 주복1 | 공식780 ↔원천726+54=780 | 원천 수량·4분기 일치. 화면 관리 목표의 별도 연도와 구별 |
| 대장A2·신길2 분양 | 공식과 HOME 합계76호 차이 | 현행 수집 계획과 발표 명세의 범위 차이. 원천 수량 검산은 완료, 기관의 변경 사유 전부를 입증한 것은 아님 |
| 대장A5·A6 임대 | 전체541 ↔금회 모집537 | 전체314/227과 금회312/225 구분. 가정어린이집 임시 배정 설명·공급표 확보 |
| 연남동8호 | 정부계획8호 ↔SH 독립사업8호 | SH업무보고79쪽에서 연희96호와 별도 행 확인. 96호 일부 가설 철회; 실제 착공·준공·모집은 별도 확인 |
| 신축매입·공공지원 민간임대 부문 | 공식 개략 총계 ↔프로그램 연결사업0 | 우리 수집·분류·연계 공백이 남는 영역. 모두 미공개 때문이라고 설명하지 않음 |

**발표 결론:** “HOME의 신뢰성은 정부의 개략 숫자를 복사하는 데 있지 않고, 공개자료를 블록·유형·사건·판본으로 분해하여 검산하고 차이를 설명할 수 있다는 데 있습니다. 확인된 공식·비공식 근거는 출처와 함께 채택하고, 추정과 실제, 계획과 완료를 구별해 재검증 가능한 원장으로 관리합니다.”

## 4. 공식 명시 착공8개 사업 전건 비교

{start_table}

**수량 해석:** 개략 표현과의 수십 호 차이는 곧바로 수집 오류로 판정하지 않는다. 교산1115는 약1100과 수량상 부합하며 이 차이만으로 A3로 바꾸지 않는다. 중계3178↔약3100처럼 모든 항목을 동일한 백 호 반올림 규칙으로 확정할 수는 없어‘개략 규모 근접’이라고 쓴다.

**계양 전체 착공 범위:** A17은 분양309+행복154=전체463호다. 임대의 향후 모집 일정은 전체 착공에서 제외할 이유가 아니다. 발표 대조에는 A6 663+A17 전체463+A16 434+A18 782=**2342호**를 사용한다. 현재 차트 누적3283은 다른 블록·분양 범위도 포함한 원장 값이다. 비교 산식은3283−A10 778−A9분양317+A17임대154=2342이며 **154를 운영 차트에 별도 추가 반영한 값은 아니다.**

**왕숙2 판본 상충:** 기존 A1·A3 1498은2025년 착공 원천이고, A6·A7 1063은 비공식 상반기 착공 원문으로 담당자 확인 완료했다. LH 공모510+553=1063과 계약 공시519+563=1082의19호 차이를 보존한다. 계약일을 실제 착공일로 전용하지 않는다.

**흑석11 서면·발언 상충:** HOME1515는 서면약1500과 부합한다. 구두약2500과의985호 차이를 수집 시차나 HOME 누락으로 바꾸어 설명하지 않는다.

착공 원문: [정부 서면4쪽]({OFFICIAL}#page=4), [정부 브리핑]({SPEECH}), [LH 공사현황 DOCX](https://www.lh.or.kr/boardDownload.es?bid=0007&list_no=654682&seq=14), [담당자 확인 완료 - 비공식 자료: 이투데이](https://www.etoday.co.kr/news/view/2613748). 개별 행·사업 ID·사건은 [CSV](comparison_start_8.csv)와 [JSON](comparison_start_8.json)에 보존했다.

## 5. 공식4분기 공급32개 항목 전체 비교

이 표의‘HOME 사업량’은 대응 사업·유형의 관리 규모다. 실제4분기 모집 완료량이나 공급계획 일치율과 같지 않다. 안산신길2 A1/A3는 공식 두 행에 대응하는 하나의 합본357호이며 총계에 한 번만 넣었다.

{plan_table}

### 분양76호 차이의 검산

- 부천대장A2: HOME548−발표498=**+50호**. 원천382+50+116=548을 검산했으나 정부가 어느50호를 왜 제외했는지는 확정하지 않았다.
- 안산신길2 B1:387−382=**+5호**.
- 안산신길2 A6:251−252=**−1호**.
- 안산신길2 A1/A3: 합본357−공식170−165=**+22호**. 합본357을 공식 두 행에 각각 더하지 않는다.
- 총차이50+5−1+22=**76호**. 공식분양10083↔HOME10159.

공식임대4648↔HOME4648은 **관리 사업 규모 합계 일치**다. 공식 공급계획을 그대로 채택한 항목이 포함되므로 모든 항목을 다른 원문에서 독립 재검증한 결과라고 소개하지 않는다. 현재 명세의 개별 수량 일치 행은 **{verified['exact_individual_quantity_rows']}개·공식호수{num(verified['exact_individual_official_units'])}호**이며, 합본 대응은 별도 판단한다.

이전 CSV의 원천계획·분기 일치 정보는 `baseline_` 열로 보존했다. 새 CSV에는 현재 매핑, 관리 일정, 원문 확인된 실제 모집일·물량·URL을 별도 열로 추가했다. 고덕강일과 부평은 계획 추정에서 실제 공고 확인으로 발전한 사례다.

## 6. 전체 주택 공식 통계와 HOME 보유값 대조

{stat_table}

위10개 항목은 모두 수치 대조가 맞았다. **이 사실은 공식 지역 통계의 수집·추출·합산 정합성을 검증한 결과**다. HOME9·7 연결 사업을 독립적으로 전부 합산해 같은 숫자가 나왔다는 뜻은 아니다. 서울 인허가39940은8월 누계이고11306은8월 당월이므로 둘을 더하지 않는다. 서울1~7월28634는 같은 판본의누계−당월 계산으로 도출한 값이며 별도7월 원문 검증과 구별한다. 분양승인15962는 해당 공식 통계의 지표이며 공공임대 모집 등 모든 공급을 포괄하는 수치로 바꾸지 않는다.

근거: [국토부 월별 통계 PDF]({MONTHLY})와 저장된 공식 월별 레코드. [검증CSV](comparison_statistics.csv), [인허가6개 원문 레코드](evidence/statistic_reference.json), [2026년 월별 지역통계](evidence/statistic_monthly_2026.json).

## 7. 공식 수도권 착공 총계와 HOME 정책 누적은 왜 직접 같지 않은가

정부 브리핑의 **올해10월 둘째 주까지 수도권 착공9만9000호 이상**은 전체 주택의 당해 실적이다. HOME **정책 누적79884호**는 확인 연결된 사업을 현재까지 추적한 관리 집합이며 과거 착공과 담당자 추정이 포함된다. 동일 지역·기간·포함 사업·실적 정의의 전수 집합이 아니므로 단순 차이를 확정 미수집량이나 정확도 비율로 쓰지 않는다.

{sector_table}

공식5개 부문의 개략량 합은98800호로 브리핑의‘9만9000호 이상’과도 정밀한 동일 숫자로 제시된 것이 아니다. 부문별8월·9월·10월 마감이 다르고 공공주택16200 안에 공공택지14200·3기 신도시7300이 포함된다. 이를 별도 물량으로 더하지 않는다. 신축매입의 지역별 개략량3600+7000+2700=13300과 부문13000도 개략 발표의 특성으로 구분한다.

## 8. 이번 외부 근거 보완으로 실제 좋아진 것

| 보완 | 전후·결과 |
| --- | --- |
| 비공식 착공 채택 | 계양A16/A18 1216+왕숙2A6/A7 1063+대장A9 574=2853호, 현재 착공77031→79884 |
| 외부 단계 대장 |15개 사례를19개 기존 사업 기록에32건 근거 연결. 비공식10개 원문에 의한13개 사업별 연결도 확인 완료 |
| 고덕강일 | 담당자 공급 추정일8월31일→확인 공고일10월16일. 전체1305호 유지, 근거·구성 확보 |
| 부평 |10월19일 최초 행복주택 모집350호 추가. 공사·임대 원천의 같은350호를 한 번만 집계 |
| 대장A5/A6 | 금회 모집312/225 확인. 임대 전체314/227을 실제 모집량으로 넣었던4호 보정 |
| 공급 최종 합계 |58195+350−4=**58541호**. 연말 계획70005는 기존 계획으로 유지 |
| 장호원 | 전체620와 예비자300명 구분. 예비자 모집을 신규 실제 공급으로 분류하던 기존 근거·정례 파서 보정 |
| 계양A2/A3 입주 목표 |2027년4월 관리 추정→2026년12월 예정 확인. 두 기록은 기존 복수블록 계약 경고로 차트 집계 제외되므로 계획 보완1285호를 차트에 새로 더하지 않음 |
| 검단AA21 | LH 입주안내의 지정기간2026-10-30~2027-01-27 확보. 현재10월20일은 시작 전이므로 계획만 갱신 |
| 준공·실입주 | 이번 추가 확인분에서 실제 완료 증빙을 확보하지 않은 예정값을 완료 실적으로 만들지 않음 |

새 근거는 확인한 범위대로 채택했다. 담당자 확인은 사용자 지시에 따른 대행 검토이며 기관 담당자와 직접 통화·공문 회신을 받았다는 뜻은 아니다. 문서·연결·프로필·계획은 재실행 무변경과 API 표시까지 확인했다. [적용·재실행·API 확인 파일](evidence/review_receipts/external_events_20261020/idempotence.json).

## 9. 공개자료를 데이터셋으로 만드는 데 어려웠던 부분과 해결

| 난점 | 실제 사례 | 보정·관리 방식 |
| --- | --- | --- |
| 지구 한 줄과 개별 사업의 단위 차이 | 검단약1300 ↔국민991+영구332 | 지구→블록→유형→원문·정정판→공사 전체량 포함관계 관리 |
| 이름이 같아도 범위가 다름 | 계양A17 전체463/분양309/행복154 | 착공 전체와 유형별 공급을 구분. 임대 향후 모집을 착공 제외 사유로 쓰지 않음 |
| 전체와 금회 공급이 다름 | 대장 임대541/금회537, 성남신촌 전체227/금회116 | 표의‘총 세대수’와‘금회 공급’을 다른 필드로 추출 |
| 같은 현장의 중복 원천 | 부평 공사350·임대350·외부 공고350 | 기존 사업에 근거 연결, 같은 물량은 한 관리 묶음·상한으로 집계 |
| 별칭·블록 코드 변경 | A31/Ab31, 당수C5/B4 | 이름의 전역 치환 대신 부지면적·용적률·호수·유형·변경 고시 대조 |
| 판본별 숫자 상충 | 왕숙2 1063/1082, 대장A9 568→574 | 원문·공시·고시별 값을 보존. 변경 고시로 확인한 차이와 미해결 상충 구별 |
| 날짜 의미가 다름 | 실제 착공일·기공식·관측 상한·모집 예정·입주지정기간 | 사건 종류·정밀도·출처 게시일을 별도 관리. 원문에 없는 정확한 날짜를 만들지 않음 |
| 파일 형식·표 구조 | PDF·HWPX·DOCX·CSV·HTML | 형식별 파싱·필수 열·수량 합계 검산. 스캔·구형 파일은 원문 보관과 추출 완료를 구분 |
| 지역 표기 오류 | 인천에 서울 구 확인 문구·구 행정구역 혼재 |55개 원천 사업의 표시 지역 정비, 인천 프로그램4개 명칭 정비. 원천 표기는 이력으로 보존 |
| 전처리와 업무 판단의 차이 | 같은 공모라도 정책 귀속 명세 미확보 | 수집·파싱 뒤 정책→프로그램→사업 연결은 별도 담당자 판단·감사 기록 |

## 10. 수집 주기·자동화·자료 변경 감지

{ops_table}

현재 등록 원천의 최신 시도 상태 분포는 **{dict(source_counts)}**다. RUNNING은 진행 중인 시도 상태이고 이전 성공 범위와 구별한다. 일반 건축인허가는 이전 성공 범위724/2907개 동,2183개 동 미조회로 기록돼 있으며 최신 시도는RUNNING이다. 주택인허가의2629개 동 및 인천278개 동 조회 완료와 일반 건축인허가의 미완료를 합쳐‘전수완료’로 표현하지 않는다.

수집 단계는 등록된 목록·페이지·조건을 재조회하고 새 ID·첨부 링크·파일 기준일을 비교한다. 원문SHA-256·레코드 식별키·내용 해시가 같으면 유지하고 바뀌면 개정 이력을 남긴다. 실패하면 이전 정상 판본을 유지하며 배치 오류·대기열·재시도 상태를 기록한다. 수집 작업의 임대가 만료되면 같은 단계부터 재시도한다. 실제 간격은 설정 주기 외에 대기열·호출 제한·실패 재시도의 영향을 받는다.

PDF 텍스트는pypdf, HWPX·DOCX는ZIP 내부XML, HTML은BeautifulSoup, CSV는인코딩·열·수량·일정 규칙으로 처리한다. 스캔PDF와 구형HWP 등은 자동 추출 대기·별도 판독 보완을 표시한다. 담당자의 정책 귀속 연결과 추정 입력을 수집 자동화 완료로 포함하지 않는다.

이전 보고서의 GH 특정 등록URL HTTP410은 과거 조회 이력이다. **이번 스냅샷의 gh_supply_plan 최근 상태는{source_by['gh_supply_plan']['status']}, 현행 수집 기록은{source_by['gh_supply_plan']['record_count']}건**이다. 과거 오류를 현재 모든 GH 자료의 부재로 사용하지 않는다. 반대로 이 성공만으로 GH 전수 수집을 입증하지도 않는다.

원천별76개 전체 주기·자동/수동·발견·전처리·URL·상태는 [출처CSV](source_urls.csv)와 [원천 메타데이터](evidence/sources.json)에 있다.

## 11. 확인했지만 정책 귀속을 유보한 목록

다음9건6296호는 공모·선정·계획 등을 확보한 후보이며, 명시적9·7 귀속·기존→신규 블록 전환 관계 등의 근거가 부족해 현재 확정 정책 사업량으로 가산하지 않은 목록이다. 이는 비공식이라는 이유로 확인된 실제 착공을 유보한5개 블록2853호와 다르다. 후자는 이미 담당자 확인 완료로 반영했다.

{held_table}

[후보별 선정·공모·고시URL과 추가 확인란 CSV](held_candidates_9.csv). 별도 왕숙유보지455호·파주운정3 3200호는 공식 정책 관계의 집합 근거를 보유하지만 개별 블록·기존 사업 포함관계가 분리되지 않아 별도 착공으로 가산하지 않았다. 같은‘정책 후보’라도 정책 관계 자체의 미확인과 개별 집계 단위 미분리는 구별한다.

## 12. 주장할 수 있는 범위와 답변 예시

| 질문·주장 | 근거에 맞는 설명 |
| --- | --- |
| 데이터가 잘 구축됐다는 근거는? | 공식 명단32개 전건 구조화·관리 연결, 임대 사업량4648호 합계 일치, 명시 후속14블록8031호 대조, 지역 통계10항목 재계산 일치, 중복·판본·유형 차이를 구체적으로 검산 가능 |
|32/32니까 정확도100%인가? | 공식 명단 대응률100%다. 공급 실적·시기·독립 검증·전체 공개자료 수집률100%로 확대하지 않음 |
| 다른 기관 값과 차이는 오류인가? | 먼저 블록·유형·전체/금회·기간·사건·판본을 대조. 수십 호 개략 차이와 실제 수량 상충·집계 범위 차이를 구별 |
| 계양 임대154호를 빼야 하나? | 전체 착공 비교에는 포함. 차트의 대표 분양 범위와 전체 공사 비교량을 별도 표시하는 문제 |
| 교산은 블록이 틀렸나? |1115↔약1100은 수량상 부합. 숫자만으로 오매칭 판정하지 않으며 원천 연도와 올해 산입 기준은 별도 검토 |
| 비공식 근거는 왜 인정하나? | 원문·동일 사업·블록·호수를 확인하고 담당자 확인 완료로 채택. 출처 성격을 비공식으로 남기고 정확한 날짜 등 없는 사실은 확대하지 않음 |
| 차이가 모두 기관 미공개 때문인가? | 아니다. 원천 공란·기관 간 범위/판본·개별 범위 미분리뿐 아니라 우리 미조회·분류·연계 부족도 구체적으로 존재 |
|9.7정책에 공공 여부 미분류 사업이 들어갈 수 있나? | 공공 여부와 정책 귀속은 다른 판단이다. 정책 근거로 귀속을 확인하되 공공 여부 미분류를 공공 사업으로 임의 승격하지 않음 |
| 위치가 없으면 잘못된 사업인가? | 사업·호수·단계 근거와 지도 좌표 근거는 다르다. 위치 미확보는 별도 상태로 남기고 실제 필지·사업 경계를 추정 좌표로 꾸미지 않음 |

권장 결론은 **‘주요 공식 명세와 대조 가능한 사업 단위 관리 데이터셋을 구축했고, 확인된 범위에서 개략 발표와 부합하며 차이를 설명할 수 있다’**다. 전체98800호 부문을 전부 독립 재현했다거나 인터넷 공개자료를100% 확보했다는 결론은 이 패키지로 입증하지 않는다.

## 13. 다음 GPT가 파일을 읽는 순서

1. 이 마스터와 [2페이지 발표 원고](HOME_GPT_REPORT_2P_20261020.md)를 먼저 읽는다.
2. [비교 요약JSON](comparison.json)에서 분모·기간·최신 집계를 확인한다.
3. 필요 항목만32개 공급CSV,8개 착공CSV,지역통계CSV,5개 부문CSV로 확장한다.
4. 특정 사업은`project_id`를 기준으로`evidence/projects.json`,프로필·일정·문서·연결JSON을 조회한다. 원천451기록과 차트175묶음을 같은 사업 수로 섞지 않는다.
5. 원문URL·해시·정부PDF·담당자 적용 이력으로 검산한다. 새 웹조사를 하지 않은 항목을‘이번에 새로 확인’했다고 쓰지 않는다.

압축파일에는 DB 비밀번호·API키·인증 세션을 넣지 않았다. 수백만 건의 원시 인허가·대장을 전부 넣는 DB 덤프가 아니라 **보고서 작성·사업별 비교에 필요한 현재 원장과 근거를 추린 패키지**다. 전체 원시 자료의 유형·출처별 건수는`evidence/record_counts.json`에 있다. 일부 원문 캡처 목록의`original_file`은 HOME 보관 경로이며 해당 HTML/PDF 전부가 압축에 포함됐다는 뜻은 아니다. 정부10월 비교PDF는 직접 포함했다.

## 14. 주요 공식·비공식 참조

- [10월 정부 공식 서면자료]({OFFICIAL}) — 첨부PDF4쪽 착공,5~6쪽4분기 공급 명세. 로컬본:[PDF](evidence/official/official-october.pdf).
- [10월16일 공식 브리핑]({SPEECH}) — 올해 착공 및 사업명 발언. 서면과 발언 상충은 보존.
- [LH 개별 공모](https://www.lh.or.kr/boardDownload.es?bid=0034&list_no=727339&seq=2) — 세부 블록·계획 호수.
- [LH 기존 건설현황](https://www.lh.or.kr/boardDownload.es?bid=0007&list_no=654682&seq=14) — 공사행·공종·착공일·호수.
- [LH 계양A17 모집공고](https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?aisTpCd=39&ccrCnntSysDsCd=02&mi=1027&panId=0000061179&uppAisTpCd=39) — 전체463/분양309/행복154.
- [담당자 확인 완료 - 비공식 자료: 이투데이](https://www.etoday.co.kr/news/view/2613748) —5개 블록2853호 상반기 착공.
- [담당자 확인 완료 - 비공식 자료: 뉴시스 고덕강일](https://www.newsis.com/view/NISX20261016_0003829226) —10월16일 본청약1305호·세부 구성.
- [LH 부평 최초 모집공고](https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?aisTpCd=10&ccrCnntSysDsCd=03&mi=1026&panId=2015122300020925&uppAisTpCd=06) —10월19일350호.
- [LH 대장A5 PDF](https://apply.lh.or.kr/lhapply/lhFile.do?fileid=67822421), [A6 PDF](https://apply.lh.or.kr/lhapply/lhFile.do?fileid=67822428) — 전체 임대와 금회 모집량·가정어린이집 설명.
- [LH 검단AA21 입주안내](https://apply.lh.or.kr/lhapply/apply/noti/an/view.do?bbsSn=9102432270&ccrCnntSysDsCd=02&mi=1079) —10월30일 입주지정기간 시작 예정.
- [국토부 월별 주택통계]({MONTHLY}) — 서울39940호 등 인허가 당월/누계.

### 등록 수집처76개 전체 목록

{sources_md}
'''
    master=master.replace('未확보','미확보')
    (OUT/'HOME_GPT_REPORT_MASTER_20261020.md').write_text(master)
    slides='''---
marp: true
paginate: true
size: 16:9
---

# 1. 공식 발표를 사업 단위로 추적·검산하는 HOME

| 공식자료 기준 | HOME 데이터셋 | 검증 결과 |
| --- | --- | --- |
|4분기 공공분양19항목·10,083호 | 같은 명단 사업량10,159호 | 전건 대응·76호 차이를 사업별 분해 |
|4분기 공공임대13항목·4,648호 | 연남8호 포함4,648호 | 사업 규모 합계 일치 |
|전체32항목·14,731호 |32항목 대응·31관리묶음·14,807호 | 명단 대응100%; 독립 실적 검증률과 구별 |
|검단 공공임대 약1,300호 | 국민991+영구332=1,323호 | 유형·정정공고·공사량 중복 통제 |
|명시9·7 후속14개 블록 | 세부계획8,031호 | 해당 명세 수량 일치 |
|서울1~8월 인허가 약4만호 | 공식 통계39,940호 수집 | 지역·기간 일치 |

**현재 정책 누적 착공79,884호 · 공급58,541호.** 과거 착공·담당자 추정 포함 관리값으로 정부의 당해 수도권 전체 총계와 구별한다.

<small>근거: comparison_32.csv / comparison_start_8.csv / comparison_statistics.csv. ‘전건 대응’은 같은 명단의 관리 연결이며 시기·실적·전체 공개자료 정확도100%라는 뜻은 아니다.</small>

---

# 2. 차이를 설명할 수 있어야 신뢰할 수 있다

| 사례 | 비교 | 설명 |
| --- | --- | --- |
|창릉·계양·왕숙2·대장 착공 |2306/2342/1063/574 ↔약2300/2300/1100/600 | 개략량 부합. 계양 전체 착공에는 임대154 포함 |
|교산 착공 |1115 ↔약1100 | 수량 부합. 원천2024년과 올해 발표 산입 기준은 별도 확인 |
|흑석11 착공 |1515 ↔서면약1500 | 구두2500과의 상충도 기록 |
|분양76호 차이 | 대장A2 +50, 신길B1 +5/A6 −1/A1·A3 +22 |50+5−1+22=76. 변경 이유 미확정 부분 표시 |
|공급 근거 보완 | 부평+350, 대장 금회 모집 보정−4 | 현재 공급58,195→58,541호 |
|연남동 독립8호 | 정부8 ↔SH8 | 연희96호와 별개; 과거계획을 실제 실적으로 전환하지 않음 |
|정책 귀속 유보9건·6296호 | 사업·공모는 확인, 개별 정책 근거 부족 | 보유 후보와 확정 실적 분리 |

> **공식·비공식 확인 근거를 출처와 함께 채택하고, 블록·유형·사건·기간·판본을 구별한다. HOME는 공개자료를 재현·검산 가능한 관리 원장으로 구축했다.**

<small>신축매입·공공지원 민간임대 프로그램 연계 공백, 일반 건축인허가 미조회 범위 등은 남아 있다. 차이가 전부 기관 미공개나 시차 때문이라고 주장하지 않는다. 상세·출처는 최신 마스터 참조.</small>
'''
    (OUT/'HOME_GPT_REPORT_2P_20261020.md').write_text(slides)
    prompt='''# GPT에 붙여넣을 요청문

첨부 HOME_GPT_REPORT_PACKAGE_20261020.zip을 기준으로 한국어 발표자료와 보고서를 작성해줘.

1. 먼저 HOME_GPT_REPORT_MASTER_20261020.md와 comparison.json을 읽어 최신 기준을 파악해줘. 이전 제출본의450개 사업·연남 미연결·공급58195호 등으로 되돌아가지 마.
2. 발표1페이지는‘공식자료 기준 ↔ HOME 데이터셋 ↔ 확인 결과’,2페이지는‘차이의 이유 ↔ 검증 근거 ↔ 데이터 신뢰성’으로 작성해줘. 구체적인 사업·호수·출처를 써줘.
3. 착공8개 사업,4분기 공급32개 항목,공식 지역 통계10개 대조 결과를 구분해서 설명해줘. 블록·임대유형·정정판·금회/전체량을 추적하는 검단·계양·대장·부평 사례를 적극 활용해줘.
4. 원문 확인된 비공식 자료는‘담당자 확인 완료 - 비공식 자료: 출처’로 채택된 자료야. 다시 공식자료가 없다는 이유로 유보 처리하지 마. 확인한 범위를 넘어 예정이나 승인·기공식을 실제 착공·준공·입주로 바꾸지는 마.
5. 교산1115↔약1100은 수량상 부합으로 설명하고,원천2024년과 정부의 올해 실적 산입 기준은 별도 표시해줘. 계양 전체 착공 비교2342에는 A17임대154가 포함되며 현재 차트에154를 새로 가산한 것은 아냐.
6.32/32명단 대응률을 모든 수치·일정·공개자료 수집률100%라고 확대하지 마. 공식 통계39940·86739 등과 정책 개별 사업 누적을 섞지 마. 신축매입·공공지원민간임대 연계 공백 등 현재 한계도 구체적인 원인으로 설명해줘.
7. 확인된 강점을 선명하게 설명하되 미확인 사유를 모두 기관 미공개·수집 시차라고 단정하지 마. 유보9건6296호는 목록과 검증할 근거를 부록에 넣어줘.
8. 연남동8호는 SH2025년11월 업무보고79쪽에서 연희96호와 별개 사업으로 확인했어. 기존8호 사업에 근거를 보완했고 신규8호를 가산한 것이 아니야. 당시 월 단위 착공·준공계획을 현재 실제 실적으로 쓰지 마. HOME_YEONNAM_8_IDENTITY_REVIEW_20261020.md와 원문·회귀검증 기록을 참고해줘.
9. 결과물은2페이지 발표용 문구,발표자 설명,상세 근거표,출처URL,질의응답으로 만들어줘. 수치를 인용할 때 해당 CSV/JSON의 비교 범위와 원문 URL을 함께 달아줘.
'''
    (OUT/'GPT_REQUEST.md').write_text(prompt)
    (OUT/'README.md').write_text('''# HOME GPT 보고자료 패키지 — 2026-10-20 최신본

읽는 순서: **GPT_REQUEST.md → HOME_GPT_REPORT_MASTER_20261020.md → HOME_GPT_REPORT_2P_20261020.md → comparison.json**.

- comparison_32.csv/json: 공식4분기 공급32항목. 연남8호 연결 완료 포함. 이전 원천계획 열은 baseline_으로 구별.
- comparison_start_8.csv/json: 공식 명시8개 착공 사업. 비교용 물량과 지구 누적 구별.
- comparison_statistics.csv: 공식 지역 통계10항목과 저장 값·산술 검증.
- comparison_sector_5.csv:5개 공식 공급유형과 현재 재현 범위·한계.
- held_candidates_9.csv: 정책 귀속 유보9건6296호·추가 검증 URL.
- explicit_policy_links.csv: 명시적 정책 근거의 사업/집합 연결과 현재 상태.
- source_urls.csv: 등록 원천76개 URL·수집 주기·자동/수동·발견/전처리 방식·최근 상태.
- evidence/projects.json: 현재 원천별 사업451개(선별 필드). 같은 현장 중복 원천 포함.
- evidence/model.json: 중복 제거 정책175개 관리 묶음·이벤트·일정. 반복 차트/지형 생략.
- evidence/project_profile.json, execution_schedule.json: 담당자 채택·추정·확인값과 이력 근거.
- evidence/document_evidence.json, evidence_bridge.json: 원문 고정 판본·사업 연결·사건·검토 상태.
- evidence/review_receipts/: 실제 반영·재실행·API 표시 검증 기록. 최초 적용 로그는 당시 중간값일 수 있어 최신 요약을 우선.
- evidence/record_counts.json: 전체 현행 자료 유형·출처별 건수. 수백만 원시 행을 전부 담은 DB 덤프는 아님.
- evidence/official/official-october.pdf: 실제 비교한10월 공식 서면자료.
- HOME_YEONNAM_8_IDENTITY_REVIEW_20261020.md: 연남8호 독립사업 확인·96호 가설 철회·반영 전후 검증.
- evidence/yeonnam_sh_identity_20261020/: SH 원본 PDF·79쪽 이미지/텍스트·해시·적용/재실행/검증 기록.
- manifest.json: 모든 포함 파일의 SHA-256·현재 집계·비교 지표·생성 기준.

이전 제출 형식은 유지했지만 이전 마스터·슬라이드의 오래된 서술은 함께 넣지 않았다. MD만 사용해도 핵심 비교표·출처·설명을 읽을 수 있으며, GPT에 데이터 검산까지 요청할 때는 ZIP 전체를 첨부한다. 원문 캡처 목록의 original_file은 HOME 보관 경로이고 일부 원문 본문은 패키지에 없다. 그 경우 URL·해시로 원본을 식별한다.
''')
    for name in ['HOME_GPT_REPORT_MASTER_20261020.md','HOME_GPT_REPORT_2P_20261020.md']:
        shutil.copy2(OUT/name,ROOT/'docs'/name)
    # The loose master links target the companion folder; inside the ZIP they
    # remain relative to the established flat presentation layout.
    loose=ROOT/'docs/HOME_GPT_REPORT_MASTER_20261020.md';content=loose.read_text()
    def local_link(m):
        target=m.group(1)
        return ']('+target+')' if '://' in target or target.startswith('#') else '](analysis/gpt_report_20261020/'+target+')'
    loose.write_text(re.sub(r'\]\(([^)]+)\)',local_link,content))
    comparisons=dict(snapshot=summary,official_comparison=verified,regional_statistics_exact_matches=sum(r['match'] for r in statistics),statistics_checked=len(statistics))
    files={str(p.relative_to(OUT)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json'}
    write(OUT/'manifest.json',dict(reference_date='2026-10-20',schema='HOME_GPT_REPORT_PACKAGE_v2',source_snapshot='read-only operational DB snapshot',summary=comparisons,files=files,scope_notes=['not a full DB dump','all 32 official items linked does not mean all quantities/timings independently verified','nonofficial sources confirmed within reported scope','public collection universe completeness not established']))
    archive=ROOT/'docs/analysis/HOME_GPT_REPORT_PACKAGE_20261020.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(OUT))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name,info in files.items():assert hashlib.sha256(z.read(name)).hexdigest()==info['sha256']
    verification=dict(archive=str(archive.relative_to(ROOT)),archive_bytes=archive.stat().st_size,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),packaged_files=len(files)+1,official_32=verified,statistics_matches=len(statistics),current_metrics=summary['metrics'])
    write(ROOT/'docs/analysis/HOME_GPT_REPORT_PACKAGE_20261020.verification.json',verification)
    print(json.dumps(verification,ensure_ascii=False))


if __name__=='__main__':main()
