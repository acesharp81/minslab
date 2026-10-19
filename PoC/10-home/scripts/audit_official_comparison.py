"""Compare frozen 2026-10-16 official/Home evidence. No network or DB writes.

Outputs stay under docs/. No public web assets are written by this script.
"""
from pathlib import Path
import csv,gzip,hashlib,json,re,zipfile
from collections import Counter
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'docs/evidence/OFFICIAL_ACCURACY_20261016'
O=ROOT/'docs/official'
DEST=ROOT/'docs/OFFICIAL_ACCURACY_REVIEW_20261016'

def read(name):
 p=E/(name+'.json')
 if p.exists():return json.loads(p.read_text())
 with gzip.open(str(p)+'.gz','rt',encoding='utf-8')as f:return json.load(f)
def rows(name):
 with (O/name).open(encoding='utf-8-sig',newline='')as f:return list(csv.DictReader(f))
def norm(v):return re.sub(r'[^가-힣A-Z0-9]','',str(v).upper())
def belongs(name,area):
 name,area=norm(name),norm(area)
 if area=='남양주왕숙':return area in name and '남양주왕숙2'not in name
 if area=='흑석11구역':return bool(re.search(r'흑석11(?![0-9])',name))
 if area=='신림2구역':return '신림2재정비촉진'in name
 return area in name
def number(v):return None if v in(None,'')else float(v)
def fmt(v):return '미확보'if v is None else f'{v:,.0f}'if float(v).is_integer()else f'{v:,}'
def compatible(actual,ref,quantum):return abs(actual-ref)<quantum/2

def workbook():
 ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
 with zipfile.ZipFile(O/'jutaekpadong_briefing_comparison_20261016.xlsx')as z:
  ss=[''.join(x.itertext())for x in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',ns)]if'xl/sharedStrings.xml'in z.namelist()else[]
  sheets=[]
  for p in sorted(x for x in z.namelist()if re.fullmatch(r'xl/worksheets/sheet[0-9]+.xml',x)):
   data=[]
   for row in ET.fromstring(z.read(p)).findall('s:sheetData/s:row',ns):
    a=[]
    for c in row:
     idx=0
     for x in re.match('[A-Z]+',c.attrib['r'])[0]:idx=idx*26+ord(x)-64
     while len(a)<idx:a.append('')
     v=c.find('s:v',ns);inline=c.find('s:is',ns)
     value=v.text if v is not None else ''.join(inline.itertext())if inline is not None else''
     a[idx-1]=ss[int(value)]if c.get('t')=='s'else value
    data.append(a)
   sheets.append(data)
  return sheets

def main():
 ms=rows('jutaekpadong_metric_compare_20261016.csv');ss=rows('jutaekpadong_project_mapping_20261016.csv')
 projects=read('projects_p1')['items']+read('projects_p2')['items'];assert len(projects)==read('projects_p1')['total']==len({p['id']for p in projects})
 d,db=read('delivery'),read('selected_database');raw=db['targeted_raw'];cohorts=d['portfolio_cohorts'];wb=workbook()
 for index,data in[(1,ms),(2,ss)]:
  wd={r[0]:r for r in wb[index]if r and re.fullmatch('[MS][0-9]{2}',r[0]or'')};assert set(wd)=={r['번호']for r in data}
  for r in data:assert wd[r['번호']][:len(r)]==list(r.values()),r['번호']
 def starts(area):
  found=[];prior=[]
  for c in cohorts:
   if not belongs(c['name'],area):continue
   es=[e for e in c['events']if e.get('stage')=='CONSTRUCTION'and e.get('status')=='ACTUAL']
   approved=[e for e in es if e.get('origin')=='MANUAL'and e.get('review_status')=='CONFIRMED']
   if approved:es=approved
   cur=[e for e in es if'2026-01-01'<=str(e.get('event_date')or'')<='2026-10-16']
   picked=cur or[e for e in es if str(e.get('event_date')or'')<'2026-01-01']
   if not picked:continue
   v=dict(project_id=c['id'],name=c['name'],units=min(c['units'],max(e.get('units')if e.get('units')is not None else c['units']for e in picked)),dates=sorted({e['event_date']for e in picked}),source_ids=c['source_ids'])
   (found if cur else prior).append(v)
  return dict(known_units=sum(x['units']for x in found)if found else None,records=found,prior=prior)
 def plans(area,stage,start='2026-10-01',end='2026-12-31'):
  result=[]
  for c in cohorts:
   if not belongs(c['name'],area):continue
   ids=set(c['source_ids'])|{c['id']}
   gs=[g for g in d['goal_comparisons']if g['scope_kind']=='project'and g['scope_id']in ids and g['stage']==stage and start<=g['due_date']<=end]
   if gs:result.append(dict(project_id=c['id'],name=c['name'],units=min(c['units'],max(g['units']for g in gs)),dates=sorted({g['due_date']for g in gs})))
  return result
 seoul=next(r for r in read('annual_supply')['rows']if r['year']==2026)['metrics']['착공']
 annual=next(r['units']for r in d['plan']['annual']if r['year']==2026);metro=d['regional_start_months'][-1]
 # Each item explicitly records why a quantity is or is not comparable.
 config={
 'M01':('MATCH_EXACT',d['plan']['target_units'],'2026~2030 · 9·7 최초목표','plan.target_units','발표 하한 135만과 동일. 후속 통합 목표와 별도 버전으로 유지.','유지'),
 'M02':('VERSION_MISSING',None,'통합 목표 버전 미등록','plan.target_units=1350000 (기존 목표)','150만 이상은 후속 통합 목표. 기존 135만에 더하지 않고 포함관계·통합 버전으로 추가.','P0 · 통합 목표 버전'),
 'M03':('VERSION_DIFFERENCE',annual,'2026 · 승인된 기존 9·7 목표','plan.annual[2026].units','기존 269000과 최신 발표 268000의 목표 버전 차이. 승인값 오류로 단정하지 않음.','P0 · 연간 목표 변경 이력'),
 'M04':('PERIOD_GAP',metro['cumulative_units'],'2026-01~2026-08','regional_start_months[-1].cumulative_units','발표는 10월 둘째 주, 보유 통계는 8월까지. 차이는 최신성 대사이며 정확도 오차가 아님.','P0 · 최신 관측 추가'),
 'M05':('NOT_REGISTERED',None,'정부 전망 범위 미등록','미발견','218000~235000 전망을 실제 착공 및 자체 사업 전망과 별도 관리.','P1 · 전망 구간'),
 'M06':('SCOPE_GAP',None,'기존 공공택지 등 목표','plan.programs[PUBLIC_LAND].annual[2026]=52000','공공택지 52000은 공공주택 전체 62000과 같은 모집단이 아니므로 대체 비교 제외.','P0 · 공공주택 통합 범위'),
 'M07':('NOT_REGISTERED',None,'공공주택 전체 실적 미집계','미발견','정책뉴스 16200을 대표값으로 사용. 속기 16000은 반올림 표현. 일부 LH 사업 합계로 전수 대체 불가.','P0 · 공공주택 실적 관측'),
 'M08':('SCOPE_GAP',None,'선별 지구·블록 자료 존재','portfolio_cohorts; S01~S04','3기 전체 7300의 해당연도·블록 구성이 미확보. 선별 합계를 정확도로 부르지 않음.','P0 · 지구·블록 명세'),
 'M09':('NOT_REGISTERED',None,'관련 도심사업 후보 존재','projects; plan.programs','노후청사 등 2000호의 대상 명세가 없어 기존 전체 프로그램과 직접 비교 불가.','P1 · 대상 사업 명세'),
 'M10':('NOT_REGISTERED',None,'신축매입 전체 착공 미등록','미발견','매입약정·재고를 착공 13000호와 혼용하지 않음.','P1 · 신축매입 착공 원장'),
 'M11':('NOT_REGISTERED',None,'서울 신축매입 실적 미등록','미발견','전체 13000의 부분집합인 서울 3600. 중복 합산 금지.','P1 · 서울 부분집합'),
 'M12':('NOT_REGISTERED',None,'접수 건/월 미등록','미발견','주택 호수·공고 건수로 18000건/월을 대체하지 않음.','P1 · 접수 시계열'),
 'M13':('NOT_REGISTERED',None,'접수 비교 분모 미등록','미발견','63%의 기준기간인 8월과 4~7월 평균의 원천이 필요.','P1 · 분모·기간'),
 'M14':('SCOPE_GAP',None,'민간정비 전체 착공 미집계','targeted_raw; S05~S07','중계본·흑석11·신림2 원천이 있으나 전체 17000 실적 집계에 연결되지 않음.','P0 · 민간정비 관리 연결'),
 'M15':('SCOPE_GAP',None,'일반·민간 전체 착공 미집계','미발견','공공·정비사업과 경계가 맞는 분류 없이 47000과 비교하지 않음.','P1 · 사업 분류 대사'),
 'M16':('SCOPE_GAP',None,'선택 정책의 공급 확인량 존재','policy_monitor.actual_supply_annual_units','발표는 공공분양 전체 1~3분기 14800. 9·7 일부 사업 공급량과 직접 비교 제외.','P1 · 공공분양 전체·분기 집계'),
 'M17':('SCOPE_GAP',None,'사업별 예정 존재','goal_comparisons[SUPPLY]','Q4 공공분양 전체 10000과 기존 승인 일정의 동일 모집단이 확인되지 않음.','P1 · 분기·유형 집계'),
 'M18':('SCOPE_GAP',None,'왕숙 등 Q4 후보 존재','S08~S10','발표 1100+500+400=2000. 공식 블록과 기존 블록 대응은 미공표.','P1 · Q4 블록 대사'),
 'M19':('SCOPE_GAP',None,'임대 계획·공고 존재','projects; lh_rent/lh_notice','전체 공공임대 1~3분기 모집 15000과 연결 범위가 다름.','P1 · 임대 모집 전체 집계'),
 'M20':('SCOPE_GAP',None,'과천지식 S12 Q4 후보 존재','S13','1424호 후보 하나로 전체 5000 이상 모집을 대체할 수 없음.','P1 · 임대 Q4 범위'),
 'M21':('SCOPE_GAP',None,'Q4 통합 모집 미집계','M17+M20','분양 10000+임대 5000이상의 합. 하위 항목과 중복 합산 금지.','P1 · 모집 통합 관계'),
 'M22':('SCOPE_GAP',None,'시장 전망·개별 입주 일정 존재','plan.occupancy_outlook; goal_comparisons','기존 2026 수도권 아파트 전망112000과 신규 2026Q4~2027 공적주택100000은 대상·기간이 다름.','P1 · 공적주택 입주 목표'),
 'M23':('NOT_REGISTERED',None,'후속과제 원장 미발견','미발견','145는 과제 건수이며 사업 수·호수와 별도 관리.','P1 · 제도 과제 원장'),
 'M24':('NOT_REGISTERED',None,'완료 과제 관측 미등록','미발견','48건 완료는 주택 공급 실적이 아님.','P1 · 과제 완료 근거'),
 'M25':('NOT_REGISTERED',None,'미완료 과제 미집계','미발견','97=145-48로 계산되는 값. 직접 관측과 산술값을 구분.','P1 · 과제 상태'),
 'M26':('NOT_REGISTERED',None,'PF 관리 사업장 미등록','미발견','300여 사업장과 주택 공급 호수는 단위가 다름.','P2 · PF 사업장 관계'),
 'M27':('QUALITATIVE',None,'기관 설치·운영 계획','수치 정확도 제외','개설일·담당기관·가동 상태로 점검하는 정성 과제.','P2 · 운영 과제'),
 'M28':('NOT_REGISTERED',None,'브리핑 빈도 미등록','미발견','월2회는 주택 호수가 아닌 발표 빈도.','P2 · 수집 일정'),
 'M29':('QUALITATIVE',None,'정부 상황판 구축 계획','수치 정확도 제외','HOME의 현재 기능을 정부 상황판 완료로 간주하지 않음.','P2 · 과제 상태'),
 'M30':('NOT_REGISTERED',None,'2026 서울 인허가 1~8월 미확보','annual_supply[2026].인허가.units=null','허가 원장 행 수나 연간 통계로 같은 기간 40000호를 대체하지 않음.','P0 · 월별 인허가'),
 'M31':('MATCH_ROUNDED',seoul['units'],'2026-01~2026-08 · 서울','annual_supply[2026].착공.units','20679를 천호 단위로 반올림하면21000. 차이321호, 발표 대비1.5286%.','유지'),
 'M32':('NOT_REGISTERED',None,'소규모 일반주택 미집계','미발견','전체 인허가 증감률과 최근6개월 세부유형84%는 다른 지표.','P1 · 유형별 기간 비교'),
 'M33':('NOT_REGISTERED',None,'소규모 일반주택 착공 미집계','미발견','전체 착공 증감률로 최근6개월 세부유형87%를 대체하지 않음.','P1 · 유형별 기간 비교'),
 'M34':('NOT_REGISTERED',None,'소비심리지수 미등록','미발견','132.5→130.8은8월·9월 두 시점 값. 하한/상한이나 가격지수로 해석하지 않음.','P2 · 별도 지수 원천'),
 'M35':('VERSION_MISSING',None,'보편형 임대 목표 미등록','미발견','2030까지190000 공급을 착공·모집 목표와 중복 합산하지 않음.','P1 · 신규 프로그램 버전'),
 'M36':('NOT_REGISTERED',None,'장기 민간임대 제도 미등록','미발견','20은 임대 기간(년)이며 공급 호수가 아님.','P2 · 제도 항목'),
 'M37':('QUALITATIVE',None,'계획 분포로 후속 분석 가능','수치 정확도 제외','연말 집중 리스크는 정성 발언. 일정 분포와 별도 평가.','P1 · Q4 집중도')}
 metric=[]
 for r in ms:
  status,value,period,field,note,action=config[r['번호']];ref=number(r['값(하한·단일)']);gap=value-ref if value is not None and ref is not None else None
  metric.append(dict(id=r['번호'],name=r['성과항목'],official_value=ref,official_upper=number(r['값(상한)']),unit=r['단위'],official_period=r['기준시점·지역'],actual_value=value,actual_scope=period,status=status,evidence_field=field,difference=gap,difference_pct=100*gap/ref if gap is not None and ref else None,accuracy_eligible=r['번호']in('M01','M31'),explanation=note,action=action,official_url=r['1차 근거 URL']))
 site=[]
 for r in ss:
  key,area=r['번호'],r['지구·사업명'];managed=[p for p in projects if belongs(p['name'],area)];refs=[x for x in raw if belongs(x['payload'].get('name',''),area)];st=starts(area);ref=number(r['발표물량'])
  actual=st['known_units']if key in('S01','S02','S03','S04')else None;eligible=False
  if key=='S01':status='MATCH_ROUNDED';eligible=True;note='S03 1282+S04 1024=2306호, 승인 착공일은2026년3~4월. 발표2300과6호 차이로 백호 표시 정밀도에 부합. 공식 블록ID 직접 검증과 구별.'
  elif key=='S02':status='PARTIAL_SCOPE';note='현재 관리한2026 착공 A17 309+A6 663+A9 317=1289호. 발표2300 대비56.04%의 대응량. A17 전체463과 부분309를 더하지 않음. 남은1011호는 범위 대사 대상.'
  elif key=='S03':status='PERIOD_GAP';note='A2 1115호의 승인 착공일2024-10-30. 발표1100과 가까워도2026 착공으로 세지 않음.'
  elif key=='S04':status='PERIOD_GAP';note='A01 812+A03 686의 승인 착공일2025-12-31. 발표2026 착공1100의 신규 블록·사건 대사 필요.'
  elif key in('S05','S06','S07'):
   status='RAW_ONLY';inv=[x for x in refs if x['kind']=='renewal_inventory'];actual=inv[0]['payload']['planned_units']if inv else None
   note={'S05':'원천 중계본동3178호·관리처분 및 착공예정 자료 존재. 관리 목록 중계1단지1370호는 다른 사업이라 제외.','S06':'흑석11 정비·허가 원천1515호와 기존 착공 단계 존재. 발표2500과985호 차이. 최신 변경계획·총량/순증·범위 대사 우선.','S07':'신림2 정비1430호와 획지별 허가 존재. 발표1400과30호 차이로 백호 정밀도 부합하나 실제2026 착공 연결 미완료.'}[key]
  elif key=='S08':status='PLAN_SCOPE_GAP';note='기존 창릉 관리 공급일정은 주로상반기. Q4 1100 대응 블록 묶음이 고정 관리일정에서 미확인.'
  elif key=='S09':status='PLAN_SCOPE_GAP';note='대장 A2 548호는 기존9월 공급일정. 발표Q4 500과 수치만 비슷하다고 같은 물량으로 확정하지 않음.'
  elif key=='S10':status='CANDIDATE_ONLY';note='A17 379호·2026-10-31은 발표400의 후보. 같은 지구에 다른Q4 계획도 있어 공식 블록 명세 필요.'
  elif key=='S11':status='PLAN_SCOPE_GAP';actual=1305;note='고덕강일3단지1305호는 발표1300과5호 차이이나 기존 승인 공급일8월31일과 발표Q4가 다름. 신규회차·범위·목표변경 대사.'
  elif key=='S12':status='RAW_ONLY';actual=600;note='광교 A17 공공주택 허가600호 존재. 관리 사업과Q4 분양일정에는 미연결. 호수 일치만으로 공급 일정 일치 판정 제외.'
  elif key=='S13':status='CANDIDATE_MATCH';actual=1424;note='S12 1424호·2026-10-31 임대 공급계획이 발표1400·Q4와 호환. 공식 블록 미공표로 정확도 분모 제외.'
  elif key=='S14':status='PLAN_SCOPE_GAP';note='발표2026-12 첫입주에 대응하는 승인 블록 일정 미확인. 기존 A2/A3 관리 입주목표2027-04-13. 대상 블록·일정 대사 필요.'
  elif key=='S15':status='PLAN_CANDIDATE';note='창릉 S6 승인 입주목표2027-12-31 존재. 발표2027과 기간 호환. 물량·블록 미공표로 수치 정확도 제외.'
  else:status='PLAN_CANDIDATE';note='대장 A5/A6 승인 입주목표2027-11-30 존재. 발표2027과 기간 호환. 수량 미발표로 정확도 제외.'
  future=plans(area,'MOVE_IN'if key in('S14','S15','S16')else'SUPPLY','2026-12-01'if key=='S14'else'2027-01-01'if key in('S15','S16')else'2026-10-01','2027-12-31'if key in('S15','S16')else'2026-12-31')
  gap=actual-ref if actual is not None and ref is not None else None
  site.append(dict(id=key,name=area,stage=r['단계'],official_value=ref,official_period=r['발표 기준 기간'],actual_value=actual,difference=gap,difference_pct=100*gap/ref if gap is not None and ref else None,status=status,accuracy_eligible=eligible,managed_name_found=bool(managed),raw_name_found=bool(refs),managed_project_ids=[x['id']for x in managed],raw_entity_ids=[x['entity_id']for x in refs],starts=st,matching_schedules=future,explanation=note,official_url=r['공식 속기 URL']))
 comparable=[r for r in metric+site if r['accuracy_eligible']]
 for r in comparable:r.update(rounding_quantum={'M01':1,'M31':1000,'S01':100}[r['id']]);r['display_compatible']=compatible(r['actual_value'],r['official_value'],r['rounding_quantum'])
 summary=dict(metric_rows=len(ms),numeric_metric_rows=sum(bool(r['값(하한·단일)'])for r in ms),site_rows=len(ss),numeric_site_rows=sum(r['official_value']is not None for r in site),unique_areas=len({r['name']for r in site}),project_records=len(projects),confirmed_projects=sum(p['mapping']['status']=='CONFIRMED'for p in projects),raw_lookup_rows=len(raw),direct_numeric_count=len(comparable),exact_matches=sum(r['difference']==0 for r in comparable),display_compatible=sum(r['display_compatible']for r in comparable),managed_site_rows=sum(r['managed_name_found']for r in site),raw_site_rows=sum(r['raw_name_found']for r in site),managed_unique_areas=len({r['name']for r in site if r['managed_name_found']}),raw_unique_areas=len({r['name']for r in site if r['raw_name_found']}),metro_latest_period=metro['month'],metro_known_units=metro['cumulative_units'],annual_target_old=annual,annual_target_new=268000,metric_status_counts=dict(Counter(r['status']for r in metric)),site_status_counts=dict(Counter(r['status']for r in site)),workbook_csv_identical=True)
 assert summary['numeric_metric_rows']==34 and summary['numeric_site_rows']==13
 assert len(comparable)==3 and all(r['display_compatible']for r in comparable)
 assert summary['managed_site_rows']==12 and summary['managed_unique_areas']==8
 assert summary['raw_site_rows']==16 and summary['raw_unique_areas']==12
 assert starts('고양창릉')['known_units']==2306 and starts('인천계양')['known_units']==1289
 assert not belongs('중계1단지','중계본동')and not belongs('흑석2','흑석11구역')and not belongs('대우신림2차푸르지오','신림2구역')and not belongs('남양주왕숙2 A3','남양주왕숙')
 result=dict(as_of_date='2026-10-16',read_only=True,summary=summary,comparable=comparable,metrics=metric,sites=site,database_capture=db['capture'],methodology={'approval':'담당자 승인값·연결은 정확한 확정값','rounding':'분석자의 표시 정밀도 비교이며 공식 오차 허용치 아님','exclusion':'기간·모집단·버전·블록 대응이 다른 항목은 정확도 분모 제외'})
 DEST.with_suffix('.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 for suffix,data in[('metrics',metric),('sites',site)]:
  fields=['id','name']+(['stage']if suffix=='sites'else[])+['official_value','actual_value','difference','difference_pct','status','accuracy_eligible','official_period','explanation','official_url']
  with (DEST.parent/(DEST.name+'_'+suffix+'.csv')).open('w',encoding='utf-8-sig',newline='')as f:
   w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(data)
 write_report(result)
 manifest={'date':'2026-10-16','read_only':True,'inputs':{},'outputs':{}}
 for p in sorted(list(O.glob('*'))+list(E.iterdir())):
  if p.is_file():manifest['inputs'][str(p.relative_to(ROOT))]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 for suffix in['.md','.json','_metrics.csv','_sites.csv']:
  p=DEST.parent/(DEST.name+suffix);manifest['outputs'][p.name]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 (DEST.parent/(DEST.name+'.manifest.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(summary,ensure_ascii=False,indent=2))


def write_report(result):
 template=(ROOT/'docs/OFFICIAL_ACCURACY_REVIEW_20261016.template.md').read_text()
 direct=['| ID | 항목 | 공식 발표 | HOME | 차이 | 상대 차이 | 판정 |','| --- | --- | ---: | ---: | ---: | ---: | --- |']
 for r in result['comparable']:direct.append(f"| {r['id']} | {r['name']} | {fmt(r['official_value'])} | {fmt(r['actual_value'])} | {r['difference']:+,.0f} | {r['difference_pct']:+.4f}% | {'완전 일치'if r['difference']==0 else'표시 정밀도 부합'} |")
 table=['| ID | 사업·단계 | 공식 물량·기간 | 보유 대응값 | 관리 목록 | 판정·사유 |','| --- | --- | --- | --- | --- | --- |']
 for r in result['sites']:table.append(f"| {r['id']} | {r['name']} · {r['stage']} | {fmt(r['official_value'])} · {r['official_period']} | {fmt(r['actual_value'])} | {'있음'if r['managed_name_found']else'미연결'} | `{r['status']}` · {r['explanation']} |")
 mt=['| ID | 항목 | 공식 값·단위 | 시스템 대응값·범위 | 판정 | 다음 조치 |','| --- | --- | --- | --- | --- | --- |']
 details=[]
 for r in result['metrics']:
  official=fmt(r['official_value'])+((' → 'if r['id']=='M34'else' ~ ')+fmt(r['official_upper'])if r['official_upper']is not None else'')
  mt.append(f"| {r['id']} | {r['name']} | {official} {r['unit']} | {fmt(r['actual_value'])} · {r['actual_scope']} | `{r['status']}` | {r['action']} |")
  details.append(f"- **{r['id']} {r['name']}**: {r['explanation']} 근거 필드: `{r['evidence_field']}`.")
 trace=[]
 for r in result['sites']:
  trace+=['',f"### {r['id']} {r['name']} · {r['stage']}",'',r['explanation'],'',f"- 관리 사업 ID: {', '.join('`'+x+'`'for x in r['managed_project_ids'])or'없음'}",f"- 관련 원천 ID: {', '.join('`'+x+'`'for x in r['raw_entity_ids'])or'없음'}"]
  for v in r['starts']['records']:trace.append(f"- 2026 착공 대응: {v['name']} · {v['units']:,}호 · {', '.join(v['dates'])}")
  for v in r['starts']['prior']:trace.append(f"- 이전 연도 착공: {v['name']} · {v['units']:,}호 · {', '.join(v['dates'])}")
  for v in r['matching_schedules']:trace.append(f"- 기간 내 승인 일정: {v['name']} · {v['units']:,}호 · {', '.join(v['dates'])}")
 body=template.replace('{{DIRECT}}','\n'.join(direct)).replace('{{SITES}}','\n'.join(table)).replace('{{METRICS}}','\n'.join(mt)).replace('{{DETAILS}}','\n'.join(details)).replace('{{TRACE}}','\n'.join(trace)).replace('{{CAPTURE}}',str(result['database_capture'])).replace('{{RAWCOUNT}}',str(result['summary']['raw_lookup_rows']))
 assert not re.search(r'{{[A-Z]+}}',body)
 DEST.with_suffix('.md').write_text(body)

if __name__=='__main__':main()
