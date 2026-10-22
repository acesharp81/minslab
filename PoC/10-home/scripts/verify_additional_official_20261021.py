"""Read-only, reproducible evidence capture for the external A01–A08 checklist.

Run from the HOME repository using Python with requests/bs4 and pdftotext.
No production writes, API secrets, or quota-consuming building-register scans.
"""
import csv
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/analysis/official_additional_checks_20261021'

def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))

def query(sql):
    result = subprocess.run(['sudo', 'docker', 'exec', 'poc10-home-db', 'psql',
        '-U', 'home', '-d', 'home', '-Atc', sql], check=True, capture_output=True, text=True)
    return [json.loads(line) for line in result.stdout.splitlines() if line]

def capture():
    OUT.mkdir(parents=True, exist_ok=True)
    # One read transaction gives all source rows a single DB snapshot.
    sql = """BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
    SELECT json_build_object('kind',kind,'source_id',source_id,'entity_id',entity_id,
        'recorded_at',recorded_at,'revision_no',revision_no,'payload',payload)
    FROM home_revision WHERE superseded_at IS NULL AND kind IN
    ('lh_notice','notice','document_evidence','lh_movein_plan','statistic',
     'statistic_reference','agency_plan','policy','project','project_profile');
    COMMIT;"""
    rows = query(sql.replace('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;', '').replace('COMMIT;', ''))
    # The SELECT is one statement and therefore one MVCC snapshot.
    dump('home_current_rows.json', rows)
    dump('capture.json', {'verified_at': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'query':sql, 'executed_query':'single SELECT / statement MVCC snapshot', 'row_count':len(rows),
        'production_mutations':0})
    from collections import Counter
    print(json.dumps(dict(Counter(r['kind'] for r in rows)), ensure_ascii=False))

def official():
    import requests
    from bs4 import BeautifulSoup
    session=requests.Session();manifest=[]
    sources={
      'G01':'https://www.korea.kr/briefing/policyBriefingView.do?newsId=156785506',
      'G02':'https://www.korea.kr/briefing/pressReleaseView.do?newsId=156785505',
      'G03':'https://www.korea.kr/news/policyNewsView.do?newsId=148973657',
      'G04':'https://www.fsc.go.kr/po010101/87948',
      'BUCHEON':'https://www.bucheon.go.kr/site/homepage/menu/viewMenu?menuid=148006005009006'}
    for name,url in sources.items():
      try:
        response=session.get(url,timeout=35);response.raise_for_status()
        response.encoding=response.apparent_encoding
        (OUT/f'{name}.html').write_text(response.text)
        soup=BeautifulSoup(response.text,'html.parser')
        (OUT/f'{name}.txt').write_text(soup.get_text('\n',strip=True))
        links=[{'text':a.get_text(' ',strip=True),'href':a.get('href')} for a in soup.select('a[href]')
               if any(x in str(a) for x in ('getFile','fileDown','attach','download','Download'))]
        dump(f'{name}_links.json',links)
        manifest.append(dict(id=name,url=url,status=response.status_code,
                             sha256=hashlib.sha256(response.content).hexdigest()))
      except Exception as exc:manifest.append(dict(id=name,url=url,error=type(exc).__name__))
    for n in (1,2,3,4):
      url=f'https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=87948&fileTy=ATTACH&fileNo={n}'
      try:
        response=session.get(url,timeout=40);response.raise_for_status()
        raw=response.content
        if raw.startswith(b'%PDF'):
          path=OUT/f'G04_attachment_{n}.pdf';path.write_bytes(raw)
          pages=subprocess.run(['pdftotext','-layout',str(path),'-'],check=True,capture_output=True,text=True).stdout.split('\f')
          if pages and not pages[-1].strip():pages.pop()
          text='\n'.join(f'\n=== PDF PAGE {i+1} ===\n'+p for i,p in enumerate(pages))
          (OUT/f'G04_attachment_{n}.txt').write_text(text)
          manifest.append(dict(id=f'G04-PDF-{n}',url=url,pages=len(pages),sha256=hashlib.sha256(raw).hexdigest()))
        else:manifest.append(dict(id=f'G04-ATTACH-{n}',url=url,content_type=response.headers.get('Content-Type'),bytes=len(raw),note='not PDF'))
      except Exception as exc:manifest.append(dict(id=f'G04-ATTACH-{n}',url=url,error=type(exc).__name__))
    dump('official_manifest.json',manifest)
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

def block_originals():
    import requests
    from bs4 import BeautifulSoup
    from concurrent.futures import ThreadPoolExecutor
    rows=json.loads((OUT/'home_current_rows.json').read_text())
    ids=['DOC_52c0c1cdaf32fdfe8d3e018e','DOC_2639c3a9e9d722506449af81',
         'DOC_00fd1ec215a0ef98ecbcf5f8','DOC_131a7acf5ef85e1a6d6fc9c6']
    def get(eid):
      row=next(r for r in rows if r['entity_id']==eid);a=row['payload'];url=a['evidence_url']
      try:
        response=requests.get(url,timeout=35);response.raise_for_status();response.encoding=response.apparent_encoding
        (OUT/f'{eid}.html').write_text(response.text)
        soup=BeautifulSoup(response.text,'html.parser');text=soup.get_text('\n',strip=True)
        (OUT/f'{eid}.txt').write_text(text)
        return dict(entity_id=eid,url=url,status=200,sha256=hashlib.sha256(response.content).hexdigest(),
                    original_source_date=a.get('source_date'),rechecked_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat())
      except Exception as exc:return dict(entity_id=eid,url=url,error=type(exc).__name__)
    with ThreadPoolExecutor(max_workers=4) as pool:manifest=list(pool.map(get,ids))
    dump('block_original_manifest.json',manifest);print(json.dumps(manifest,ensure_ascii=False,indent=2))

def csvwrite(name, rows):
    if not rows:return
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def analyze():
    import re
    from collections import defaultdict, Counter
    rows=json.loads((OUT/'home_current_rows.json').read_text())
    first={r['id']:r['first'] for r in query("""SELECT json_build_object('id',entity_id,'first',min(recorded_at))
        FROM home_revision WHERE kind IN ('notice','lh_notice','document_evidence','lh_movein_plan','agency_plan')
        GROUP BY entity_id""")}
    dump('first_collection_dates.json',first)
    def metadata(r):
        a=r['payload'];return dict(home_id=r['entity_id'],source_id=r['source_id'],name=a.get('name'),
            notice_no=a.get('notice_no'),region=a.get('region'),units=a.get('offered_units',a.get('units')),
            source_date=a.get('source_date'),source_date_label=a.get('source_date_label'),
            first_collected_at=first.get(r['entity_id']),current_revision_recorded_at=r['recorded_at'],
            source_publication_date=a.get('announcement_date',a.get('source_date')) if r['kind'] in ('notice','lh_notice') or a.get('announcement_date') else None,
            source_as_of=a.get('dataset_version'),event_or_plan_date=None,
            evidence_url=a.get('evidence_url'),notice_round=a.get('notice_round'),notice_status=a.get('notice_status'))
    in_period=lambda a:'2026-01-01'<=str(a.get('source_date') or '')<='2026-09-30'
    inventory=[]
    for r in rows:
        a=r['payload']
        if r['kind'] in ('lh_notice','notice') and in_period(a):inventory.append(metadata(r))
    csvwrite('Q1_Q3_notice_inventory.csv',inventory)
    groups=defaultdict(list)
    for r in rows:
        a=r['payload']
        if r['source_id']=='lh_notice_detail' and a.get('notice_round')=='MAIN':
            category='SALE' if '분양' in a.get('tenure','') and '임대' not in a.get('tenure','') else 'RENT'
            groups[(a.get('district'),a.get('block'),category,a.get('tenure'))].append(r)
    selected={'SALE':[],'RENT':[]};lineage=[]
    for key,versions in sorted(groups.items()):
        originals=[r for r in versions if r['payload'].get('notice_status')=='ORIGINAL']
        initial=min((r['payload']['source_date'] for r in originals),default=None)
        eligible=bool(initial and '2026-01-01'<=initial<='2026-09-30')
        available=[r for r in versions if str(r['payload'].get('source_date') or '')<='2026-09-30']
        latest=max(available,key=lambda r:(r['payload']['source_date'],r['entity_id'])) if available else None
        if eligible and latest:selected[key[2]].append(latest)
        for r in versions:
            item=metadata(r);item.update(district=key[0],block=key[1],category=key[2],tenure=key[3],
                original_notice_date=initial,selected_for_partial=bool(eligible and latest and r['entity_id']==latest['entity_id']),
                exclusion_reason='' if eligible else 'ORIGINAL_DATE_NOT_IN_PERIOD' if initial else 'ORIGINAL_NOTICE_NOT_CAPTURED')
            lineage.append(item)
    csvwrite('LH_MAIN_notice_lineage.csv',lineage)
    # This is a deliberately limited public-developer notice extract, not an assertion of the official population.
    public=[]
    for r in rows:
        a=r['payload']
        if r['kind']=='notice' and in_period(a) and any(w in a.get('developer','') for w in
            ('토지주택공사','주택도시개발공사','경기주택도시공사','인천도시공사')):
            if not any(w in a['name'] for w in ('추가','잔여','임대주택')):public.append(r)
    assert len({r['payload']['source_object_id'] for r in public})==len(public)
    # Explicit reviewed crosswalk: all other selected LH SALE blocks occur in these Cheongyak notices.
    # The one additional block absent from this extract is Wangsuk2 A1 (812 units).
    extra=next(r for r in selected['SALE'] if r['entity_id']=='DOC_382d3325d7dad7b4d69b1aee')
    crosswalk=[]
    for lhs in selected['SALE']:
        a=lhs['payload'];compact=lambda s:re.sub(r'\s+','',s)
        blocks=lambda s:{c+str(int(n)) for c,n in re.findall(r'([A-Z]+)[- ]?(\d+)',s)}
        initial=next(r['original_notice_date'] for r in lineage if r['home_id']==lhs['entity_id'])
        matches=[r for r in public if compact(a['district']) in compact(r['payload']['name']) and
            r['payload']['units']==a['offered_units'] and a['block'] in blocks(r['payload']['name']+' '+r['payload'].get('address','')) and r['payload']['source_date']==initial]
        assert (not matches and lhs['entity_id']==extra['entity_id']) or len(matches)==1, a['name']
        crosswalk.append(dict(lh_document_id=lhs['entity_id'],district=a['district'],block=a['block'],
            offered_units=a['offered_units'],cheongyak_notice_id=matches[0]['entity_id'] if matches else None,
            decision='COUNT_CHEONGYAK_ONLY' if matches else 'COUNT_LH_ONLY',
            basis='同 지구명·블록명·공고일·호수 수동 대조; 같은 공급공고를 두 번 더하지 않음'))
    csvwrite('A01_cross_source_dedup.csv',crosswalk)
    sale=public+[extra]
    assert len(public)==23 and sum(r['payload']['units'] for r in public)==13639
    assert extra['payload']['offered_units']==812
    sale_rows=[metadata(r) for r in sale];csvwrite('A01_public_sale_partial.csv',sale_rows)
    gh=next(r for r in rows if r['entity_id']=='DOC_2080da75076acc0963be7b35')
    assert gh['payload']['offered_units']==518 and gh['payload']['notice_round']=='MAIN'
    rent=selected['RENT']+[gh];csvwrite('A02_rental_partial.csv',[metadata(r) for r in rent])
    comparison=[]
    named={
        '고양창릉':(2800,[r for r in sale if '고양' in r['payload']['name'] and '창릉' in r['payload']['name']]),
        '남양주왕숙2':(1500,[r for r in sale if '왕숙2' in r['payload']['name']]),
        '인천계양':(1300,[r for r in sale if '인천계양' in r['payload']['name']]),
        '화성동탄2':(500,[r for r in sale if '화성동탄2' in r['payload']['name']]),
        '성남낙생':(900,[r for r in sale if '성남낙생' in r['payload']['name']]),
        '마곡':(400,[r for r in sale if '마곡' in r['payload']['name']])}
    for name,(official,records) in named.items():
        comparison.append(dict(parent_check_id='A01',name=name,official_approx_units=official,
            home_notice_units=sum(r['payload'].get('offered_units',r['payload'].get('units')) for r in records),
            home_ids='|'.join(r['entity_id'] for r in records),evidence_urls='|'.join(r['payload']['evidence_url'] for r in records),
            interpretation='개략량과 규모 대응; 독립 검증 항목 수에 추가하지 않음'))
    for name,official,word in [('고양창릉',300,'고양창릉'),('부천대장',500,'부천대장'),('인천검단',1300,'인천검단'),('성남금토',800,'성남금토'),('다산지금',500,'다산지금')]:
        records=[r for r in rent if word in r['payload']['name']]
        comparison.append(dict(parent_check_id='A02',name=name,official_approx_units=official,
            home_notice_units=sum(r['payload']['offered_units'] for r in records),home_ids='|'.join(r['entity_id'] for r in records),
            evidence_urls='|'.join(r['payload']['evidence_url'] for r in records),
            interpretation='일부 상세만 확보; 전체 대응 확정 불가' if name=='성남금토' else '개략량과 규모 대응; 독립 검증 항목 수에 추가하지 않음'))
    csvwrite('named_supply_subchecks.csv',comparison)
    plans=[]
    for r in rows:
        a=r['payload']
        if r['kind']=='lh_movein_plan':facts=[dict(date=a.get('move_in_plan_month'),units=a.get('units'))]
        elif r['kind']=='agency_plan':facts=[f for f in a.get('facts',[]) if f.get('stage')=='MOVE_IN' and f.get('kind')=='PLAN']
        else:continue
        for f in facts:
            d=f.get('date')
            if d and '2026-10'<=d[:7]<='2027-12':
                item=metadata(r);item.update(units=f.get('units'),event_or_plan_date=d,
                    housing_type=a.get('housing_type',a.get('tenure')),statistic_kind='PLAN',
                    scope_note='원천별 행; 다른 원천 및 사업 원장과 중복 합산 금지')
                plans.append(item)
    csvwrite('A05_movein_plan_source_rows.csv',plans)
    stats=[r for r in rows if r['kind']=='statistic' and r['payload'].get('region')=='서울특별시' and
        r['payload'].get('statistic_metric')=='착공' and r['payload'].get('statistic_period') in
        [f'{year}{month:02d}' for year in (2025,2026) for month in range(3,9)]]
    csvwrite('A04_all_housing_reference_not_comparable.csv',[metadata(r) for r in stats])
    details=[r for r in rows if r['source_id']=='lh_notice_detail' and in_period(r['payload'])]
    summary=dict(
        lh_list_period_count=sum(r['kind']=='lh_notice' and in_period(r['payload']) for r in rows),
        lh_detail_period_count=len(details),lh_detail_period_notice_ids=len({r['payload'].get('notice_entity_id') for r in details}),
        cheongyak_period_count=sum(r['kind']=='notice' and in_period(r['payload']) for r in rows),
        public_sale_partial_units=sum(r['units'] for r in sale_rows),public_sale_partial_rows=len(sale_rows),
        lh_sale_detail_partial_units=sum(r['payload']['offered_units'] for r in selected['SALE']),
        rental_partial_units=sum(r['payload']['offered_units'] for r in rent),rental_partial_scopes=len(rent),
        lh_rental_partial_units=sum(r['payload']['offered_units'] for r in selected['RENT']),
        movein_plan_by_source={sid:dict(rows=sum(r['source_id']==sid for r in plans),units=sum(r['units'] or 0 for r in plans if r['source_id']==sid)) for sid in sorted({r['source_id'] for r in plans})},
        all_housing_starts_reference={str(year):sum(r['payload']['units'] for r in stats if r['payload']['statistic_period'].startswith(str(year))) for year in (2025,2026)},
        requested_check_count=8)
    assert summary['public_sale_partial_units']==14451 and summary['rental_partial_units']==3806
    assert len(stats)==12, 'not all 12 comparison months captured'
    dump('analysis.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))

def results():
    summary=json.loads((OUT/'analysis.json').read_text());capture=json.loads((OUT/'capture.json').read_text())
    g01='https://www.korea.kr/briefing/policyBriefingView.do?newsId=156785506'
    g04='https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=87948&fileTy=ATTACH&fileNo='
    query='scripts/verify_additional_official_20261021.py capture analyze results'
    fields='check_id,official_indicator,official_value,precision,statistic_kind,geography,housing_type,period_start,period_end,official_source_url,official_source_page,home_value,home_source_ids,home_method,home_query_or_script,quantity_unit,difference,match_status,difference_reason,unresolved_requirement,evidence_urls,verified_at'.split(',')
    specs=[
      ('A01','1~3분기 공공분양 공급·공고',14800,'서면 1.48만호; 개별 호수의 정밀도 미공개','ACTUAL_NOTICE','수도권 문맥; 기관·지역별 원장 미공개','공공분양','2026-01-01','2026-09-30',g04+'3','PDF p5',None,'A01_public_sale_partial.csv',
       '청약홈 공공시행자·최초 본모집 23건 13639호 + 중복 없는 LH 왕숙2 A1 812호 = 후보 부분합 14451호. 전체 동일 모집단 아님',
       '호',None,'UNVERIFIED','목록·상세·공고 유형 및 공식 포함 범위의 완결성이 부족. 후보 부분합 차이349호를 실제 누락량으로 확정 불가',
       '공식 14800호 사업·공고 명세 및 최초/재공고 산입 기준; LH 외 기관·미보유 상세의 모집 호수'),
      ('A02','1~3분기 공공임대 입주자 모집',14700,'서면 1.47만호 확인; 발언 약15000호','ACTUAL_NOTICE','수도권 문맥; 기관·지역별 원장 미공개','공공임대','2026-01-01','2026-09-30',g04+'3','PDF p5',None,'A02_rental_partial.csv',
       'LH 정정 계보를 정리한 MAIN 10개 범위 3288호 + GH 다산지금A3 최초모집518호 = 부분합3806호. 예비·추가모집과 단지총량 별도',
       '호',None,'UNVERIFIED','상세 보유가 사업 연결 범위에 제한됨. iH 원문 본문 보유와 SH/GH 전체 실제 모집 호수의 통합 원장은 별개',
       '기관·유형별 전량 공고 상세 및 취소·정정·재모집 계보; 공식 모집 실적의 포함 명세'),
      ('A03','서울 일반주택 인허가 전년동기 증가율',84,'정수 %; 원호수는 2.7천→5.0천 개략량','ACTUAL_RATE','서울특별시','일반주택; 공식 유형코드 미제시','2026-03-01','2026-08-31',g04+'4','PDF p1',None,'molit_statistics|molit_monthly_release',
       '2025·2026 동일 3~8월, ((2026호수/2025호수)-1)*100 필요. 전체주택/사업 관리값 대입 제외',
       '%',None,'UNVERIFIED','HOME 월별 인허가 참조는 전체주택 총계이고 해당 유형별 양년도 정확 원호수는 미확보',
       '일반주택 세부 유형 코드의 공식 대응표와 양년도 월별 호 단위 값; 2700·5000으로 역산 금지'),
      ('A04','서울 일반주택 착공 전년동기 증가율',87,'정수 %; 원호수는 2.2천→4.2천 개략량','ACTUAL_RATE','서울특별시','A03과 같은 일반주택 정의 필요','2026-03-01','2026-08-31',g04+'4','PDF p1',None,'A04_all_housing_reference_not_comparable.csv',
       'HOME에 양년도 3~8월 월별 전체주택12행은 있음. 유형별 일반주택 합계와 구분하여 재산출 보류',
       '%',None,'UNVERIFIED','현재 착공 API의 부문별 총계는 아파트/일반주택 분류가 아님. 전체주택11663→16907로87% 검증 불가',
       '동일 유형코드의 양년도 호 단위 실제 착공표와 원천 기준 판본'),
      ('A05','수도권 공적주택 입주 추진계획',100000,'약10만; 제시 유형합계9.6만 + 등','PLAN','수도권','공공분양·건설임대·매입임대·전세임대·공공지원민간임대 등','2026-10-01','2027-12-31',g04+'4','PDF p2',None,'A05_movein_plan_source_rows.csv',
       '원천별 계획을 별도 계산: LH 연간입주9행3395호, LH행복1행179호(중복), REB242행149250호(민간 포함). 서로 합산하지 않음',
       '호',None,'DIFFERENT_SCOPE','공식 공적주택은 기존주택 매입·전세임대 입주 지원까지 포함. HOME 건설사업 원장과 모집단이 다름',
       '매입·전세임대 등 같은 기간·지역 계획 명세 및 공적주택 10만호의 항목별 원장'),
      ('A06','인천계양 최초 입주 예정월','2026-12','월 단위 계획','PLAN','인천계양 공공주택지구','A2 공공분양747; A3 분양359+행복179','2026-12-01','2026-12-31',g04+'4','PDF p2','2026-12',
       'PRO_325adcce78038cd49c65a01f|PRO_7dffd65ce8143bd3adcb788a|LH__ce7705d9fef9dd91a937a3df|LH__50bebc0b354e065c9a2e0d49|LH__2066d51adb3ad52d01d40955|LH__fb5585fc791b2f521b3cc4cf',
       'LH 연간 입주계획과 A3 모집공고로 월 확인. 기존 정책 연결 유지하고 공식 계획 근거 보강. 합계1285호는 블록 범위 설명이며 공식 발표 호수 아님',
       '예정월',0,'PLAN_ALIGNED','공식 월 계획과 HOME 예정월 일치. 입주 완료 실적은 검증 대상 아님',
       '향후 실제 입주개시 공고·사건 증빙 필요'),
      ('A07','8·13 후속과제 진행상황','145/48/97','행정과제 정확 건수','ADMIN_TASK_STATUS','중앙정부 부처','주택 호수 아님','2026-10-16','2026-10-16',g04+'3','PDF p5',None,'policy_813',
       '공식 합계145=완료48+추진97; 기관별 완료1+31+16=48 확인. HOME에는 정책 문서가 있으나145건 개별 과제 명부 없음',
       '과제 건',None,'UNVERIFIED','공식 집계 자체를 반복하는 것은 HOME 독립 과제 검증이 아님',
       '개별145개 과제 ID·기관·상태·완료증빙 대장'),
      ('A08','고양창릉·부천대장 후속 입주 예정','2027','10.16 발언은 연 단위; 블록별 월은 별도 자료','PLAN','고양창릉·부천대장','창릉S6 430; 대장A5 전체952/A6 전체688','2027-01-01','2027-12-31',g01,'전월세시장 안정 입주계획 문단','창릉S6 2027-12; 부천대장A5·A6 2027-11',
       'DOC_52c0c1cdaf32fdfe8d3e018e|DOC_00fd1ec215a0ef98ecbcf5f8|DOC_2639c3a9e9d722506449af81|PRO_148663cc20e9552d2c42c304|PRO_4ce4de9490cbe0a07f49c657|PRO_b880a907c24a95915be5fb6e',
       'LH 블록별 모집공고와 부천시 공식계획 대조. 창릉S6 기존월 유지, 대장A5/A6 관리 입주계획2028-05-02를2027-11로 보완. 사업 총량·실제 착공값은 불변',
       '예정연월',None,'PLAN_ALIGNED','과거 창릉A4/S6 자료와 단지별 공고를 구분. 창릉A4의 최신2028-01과 S6의2027-12는 다른 블록이므로 양립',
       '미래 실제 입주 여부는 별도 확인; 단지별 후속 계획 변경 감시')]
    output=[]
    for spec in specs:
        assert len(spec)==19
        values=dict(zip(fields[:14],spec[:14]))
        values.update(home_query_or_script=query,quantity_unit=spec[14],difference=spec[15],match_status=spec[16],
            difference_reason=spec[17],unresolved_requirement=spec[18],evidence_urls=spec[9],verified_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat())
        values['official_published_at']='2026-10-16'
        values['home_snapshot_at']=capture['verified_at']
        values['partial_home_units']=summary['public_sale_partial_units'] if spec[0]=='A01' else summary['rental_partial_units'] if spec[0]=='A02' else None
        files={'A01':'A01_public_sale_partial.csv','A02':'A02_rental_partial.csv',
               'A04':'A04_all_housing_reference_not_comparable.csv','A05':'A05_movein_plan_source_rows.csv'}
        if spec[0] in files:
            with (OUT/files[spec[0]]).open(encoding='utf-8-sig',newline='') as f:detail=list(csv.DictReader(f))
            values['home_source_ids']='|'.join(sorted({r['home_id'] for r in detail}))
            values['evidence_urls']='|'.join(sorted({spec[9]}|{r['evidence_url'] for r in detail if r.get('evidence_url')}))
        if spec[0] in ('A06','A08'):
            plan=json.loads((OUT/'plan.json').read_text())
            values['evidence_urls']='|'.join(sorted({spec[9]}|{r['url'] for r in plan if r['check_id']==spec[0]}))
            applied=json.loads((OUT/'applied.json').read_text())
            selected={r['project_id'] for r in plan if r['check_id']==spec[0]}
            docs={r['document_id'] for r in applied['results'] if r['project_id'] in selected}
            values['home_source_ids']='|'.join(sorted(set(values['home_source_ids'].split('|'))|docs))
        output.append(values)
    # Keep the user-requested field order stable, then add audit timing/partial fields.
    output=[{key:r.get(key) for key in fields+['official_published_at','home_snapshot_at','partial_home_units']} for r in output]
    assert len(output)==8 and len({r['check_id'] for r in output})==8
    assert all(r['home_value'] is None and r['difference'] is None for r in output if r['match_status'] in ('UNVERIFIED','DIFFERENT_SCOPE'))
    csvwrite('additional_check_results.csv',output);dump('additional_check_results.json',output)
    print(json.dumps(dict(__import__('collections').Counter(r['match_status'] for r in output)),ensure_ascii=False))

if __name__=='__main__':
    import sys
    if 'capture' in sys.argv:capture()
    if 'official' in sys.argv:official()
    if 'blocks' in sys.argv:block_originals()
    if 'analyze' in sys.argv:analyze()
    if 'results' in sys.argv:results()
