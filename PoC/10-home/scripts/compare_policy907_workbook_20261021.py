"""All 185 rows: compare equivalent scope or explicitly preserve uncertainty.

Never treat captured official reference values as independent HOME observations.
"""
import csv
import json
import re
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from pathlib import Path
from scripts.export_policy907_verification_20261021 import FOLDER, csvwrite, dump

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/analysis'/FOLDER
REGIONS={'서울':'서울특별시','경기':'경기도','인천':'인천광역시'}


def read(name):return json.loads((OUT/(name+'.json')).read_text())


def quantum(row):
    text=row['공식 원문표기'].replace(',','')
    for unit,multiplier in [('만',10000),('천',1000)]:
        hit=re.search(r'(\d+(?:\.(\d+))?)\s*'+unit,text)
        if hit:return Decimal(multiplier)/(10**len(hit[2] or ''))
    hit=re.search(r'[+-]?\d+(?:\.(\d+))?',text)
    return Decimal(1)/(10**len(hit[1] or '')) if hit else Decimal(1)


def precision_check(row,value):
    if value is None:return None,'미판정',None,None
    official=Decimal(row['공식 기준수치']);value=Decimal(str(value));q=quantum(row)
    rounded=(value/q).quantize(Decimal(1),rounding=ROUND_HALF_UP)*q
    truncated=(value/q).quantize(Decimal(1),rounding=ROUND_DOWN)*q
    if row['수치 정밀도']=='정확':return value==official,'원단위 비교',float(q),float(value-official)
    if row['수치 정밀도']=='이상':return value>=official,'공표 하한 비교',float(q),float(value-official)
    if rounded==official:return True,'공표 자릿수 반올림 시 부합',float(q),float(value-official)
    if truncated==official:return None,'절삭 시 부합 가능 — 공식 절삭 방식 미확인',float(q),float(value-official)
    return False,'동일 자릿수 반올림·절삭으로 설명되지 않음',float(q),float(value-official)


def pdf_starts():
    values={}; evidence={}
    for name,year in [('monthly_202602',2026),('monthly_202607',2026),('monthly_202507',2025),('monthly_202407',2024)]:
        text=(OUT/(name+'.txt')).read_text()
        section=text.split('➋ 착공',1)[1].split('➌',1)[0]
        hits=re.findall(r'^\s*\(서울\)\s+(.+)$',section,re.M)
        assert len(hits)==2,(name,hits)
        rows=[[int(n.replace(',','')) for n in re.findall(r'(?<![\d.])[\d,]+(?![\d.])',r)[:5]] for r in hits]
        for offset,index in [(0,2),(-1,4)]:
            for typ,value in [('TOTAL',rows[0][index]),('APARTMENT',rows[1][index]),('NON_APARTMENT',rows[0][index]-rows[1][index])]:
                key=(year+offset,2 if name.endswith('02') else 7,typ)
                values.setdefault(key,value);evidence.setdefault(key,name+'.pdf')
    return values,evidence


def main():
    book=read('workbook_extracted');model=read('model');projects=read('policy_linked_projects');cohorts=model['portfolio_cohorts']
    supporting=read('supporting_rows');byid={r['id']:r for r in supporting};ps={p['id']:p for p in projects}
    extra_a17=byid.get('DOC_228ee5bf959cb31f204647e0')
    extra_magok=byid.get('DOC_f41c9141fb144b2598f6f8cb')
    supplement=read('supplement_plan');pdf={};pdf_source={}
    for r in supplement['permit']:
        key=(r['year'],r['month'],r['type']);pdf.setdefault(key,r['units']);pdf_source.setdefault(key,r['source_pdf'])
    pdf_start,start_sources=pdf_starts()
    typed=json.loads((ROOT/'docs/analysis/official_followup_sources_20261021/molit_5387_seoul_2025_2026.json').read_text())+read('typed_starts_jan_feb')+read('typed_starts_history')
    def start_type(year,typ):
        rows=[r for r in typed if str(year)+'01'<=r['date']<=str(year)+'07']
        total=sum(r['착공실적'] for r in rows if r['대분류']=='계(다가구동수기준)')
        apt=sum(r['착공실적'] for r in rows if r['대분류']=='아파트')
        return {'TOTAL':total,'APARTMENT':apt,'NON_APARTMENT':total-apt}[typ]
    def stat(metric,regions,first,last):
        periods=[f'{year}{month:02d}' for year in range(int(first[:4]),int(last[:4])+1) for month in range(1,13) if first<=f'{year}{month:02d}'<=last]
        found={};ids=[]
        for r in supporting:
            if r.get('sample_kind')!='statistic' or r.get('statistic_frequency')!='MONTH' or r.get('statistic_metric')!=metric or r.get('region') not in regions or r.get('statistic_period') not in periods:continue
            key=(r['region'],r['statistic_period'])
            if key in found:assert found[key]==r['units'],('conflicting current statistical values',key)
            found[key]=r['units'];ids.append(r['id'])
        if len(found)!=len(periods)*len(regions):return None,ids
        return sum(found.values()),ids
    def amount(c,stage,first=None,last='2026-10-21'):
        es=[e for e in c['events'] if e['stage']==stage and e.get('status','ACTUAL')=='ACTUAL' and e.get('event_date') and e['event_date']<=last and (not first or e['event_date']>=first)]
        return min(c['units'],max([e.get('units') or 0 for e in es]+[0]))
    def partial(stage,region=None,first=None,last='2026-10-21'):
        return sum(amount(c,stage,first,last) for c in cohorts if region is None or c['region']==region)
    source_urls={r['자료ID']:r['공식 URL'] for r in book['공식출처목록']}
    with (ROOT/'docs/analysis/official_additional_checks_20261021/named_supply_subchecks.csv').open(encoding='utf-8-sig') as f:
        named=list(csv.DictReader(f))
    rows=[]
    for original in book['공식수치_대조입력']:
        rid=original['지표ID'];n=int(rid[1:]);region=REGIONS.get(original['지역·사업지']);indicator=original['지표']
        r=dict(original);r.update(HOME_동일범위비교값=None,HOME_정책사업부분값=None,HOME_참고값=None,
            HOME_과거공표판본값=None,비교기준='9·7 매핑 사업 원장',판정='검증유보',수량표현부합=None,
            반올림단위=float(quantum(original)),수량차이=None,표현비교='미판정',
            사유='동일 기간·유형·지역·실적/계획의 완결된 원장 미확보',필요자료='동일 모집단의 사업·공고·과제 명세',
            HOME_근거ID='',HOME_출처='',독립검증여부='아니오 — 범위 확인 필요',공식출처검토='원문 확보; 수치별 아래 근거 참조')
        if '착공' in indicator:r['HOME_정책사업부분값']=partial('CONSTRUCTION',region,'2026-01-01' if '2026' in original['실적·계획 기준기간'] else None)
        if '공고' in indicator or '모집' in indicator:r['HOME_정책사업부분값']=partial('SUPPLY',region,'2026-01-01','2026-09-30')
        if n==1:
            r.update(HOME_동일범위비교값=model['target_units'],판정='비교가능',비교기준='9·7 원안 정책목표 보관값',
                사유='정책 목표를 수집·보관한 결과. 독립 사업 실적 합계가 아님',HOME_출처=model['plan']['evidence_url'],독립검증여부='아니오 — 목표 원문 재현')
        elif n in list(range(2,24))+list(range(32,42))+list(range(45,51)):
            r.update(판정='범위다름',사유='공식은 전체 공공택지·통합정책·전체 공급유형 또는 행정과제이며 9·7 식별 사업의 부분합과 다름',
                필요자료='공식 포함 명세 및 같은 기간·유형의 전량 실적/계획',비교기준='정책 원장 부분값은 참고만; 공식 전체와 직접 비교 금지')
        elif n in [24,25,26,27,28,42,43,44,115,116,117,185]:
            selections={24:('고양창릉',['S03','S04']),25:('인천계양',['A17','A6','A16','A18']),26:('하남교산',['A2']),
                27:('남양주왕숙2',['A6','A7']),28:('부천대장',['A9'])}
            if n in selections:
                name,blocks=selections[n]
                selected=[c for c in cohorts if name in c['name'] and re.sub(r'([A-Z]+)0*([0-9]+)',lambda m:m[1]+str(int(m[2])),re.sub(r'[^A-Z0-9]','',c.get('block') or '').upper()) in [re.sub(r'([A-Z]+)0*([0-9]+)',lambda m:m[1]+str(int(m[2])),b) for b in blocks]]
            else:
                word='흑석11' if n in [42,115,185] else '중계본동' if n in [43,117] else '신림2'
                selected=[c for c in cohorts if word in c['name']]
            value=sum(c['units'] for c in selected)
            urls={e.get('evidence_url') for c in selected for e in c['events'] if e['stage']=='CONSTRUCTION' and e.get('evidence_url')}
            r.update(HOME_동일범위비교값=value if selected else None,HOME_근거ID='|'.join(c['id'] for c in selected),
                HOME_출처='|'.join(sorted(urls)),판정='비교가능',비교기준='발표 지구·개별 사업 대응 범위',
                사유='수량과 착공 시점을 분리. 개략량과 사업 규모 대응은 정부 산입 블록 확정과 다름')
            if n==25:
                r.update(HOME_참고값=2342,판정='부분범위',사유='관리 범위 2,188호. A17 전체463호와 분양309호 차이154호 포함 시 후보2,342호로 반올림2,300호. 임대 구성·산입 블록 미확정이므로 자동 가산하지 않음',필요자료='A17 임대154호 구성과 10월 착공 산입 블록 확정')
                if extra_a17:
                    assert extra_a17['scope_breakdown']=={'공공분양':309,'행복주택':154}
                    r.update(사유='LH9월30일 공식PDF로 A17전체463=분양309+향후행복154 구성 확정. 임대154는 향후 별도 모집이며 현재 모집실적 아님. 전체 후보2,342는2,300으로 반올림 양립하나 정부 착공 산입블록·현재 관리범위2,188와의 차이는 별도 확인 필요',
                        필요자료='정부 착공 산입블록 명세 및 혼합단지의 전체 건설규모와 유형별 관리범위 대응',
                        HOME_출처=r['HOME_출처']+'|'+extra_a17['evidence_url'])
            if n==26:r.update(판정='시점다름',사유='A2 1,115호는 1,100호에 반올림 부합하나 원천 착공일은2024년. 2026년 정부 산입 여부 미확정')
            if n in [27,28]:r.update(사유='담당자 확인 - 비공식 자료: 이투데이 2026-08-12. 상반기 착공 확인, 6월30일은 기간 상한. 정부 산입 블록 확정과 구분',독립검증여부='담당자 비공식 확인과 공식 발표의 규모 대응')
            if n in [43,117]:r.update(사유='서울시 공식 발표로3,178호 기착공 확인. 9월7일은 관측 상한이며 정확한 착공일·월은 미확인',판정='수량비교_시점유보')
            if n==185:r.update(판정='공식자료상충',사유='동일 회차 구두약2,500호와 서면약1,500호 상충. HOME1,515호를 구두값으로 덮어쓰지 않음')
        elif n in [29,30,31]:
            word={29:'수원당수2',30:'부천역곡',31:'노후청사'}[n]
            selected=[c for c in cohorts if word in c['name']]
            r.update(HOME_참고값=sum(c['units'] for c in selected) if selected else None,
                HOME_근거ID='|'.join(c['id'] for c in selected),사유='발표 사업의 포함 블록·실제 착공 원장 미확정. 보유 계획규모를 해당 연도 착공 실적으로 대입하지 않음')
            if n==29 and 'DOC_d434d2066efaf0c9142e5a57' in byid:
                r.update(사유='기존5블록 계획3,553호와 별개로 A2통합공공임대664호 입찰 재게시 추가 확인. 계약·입찰은 실착공과 다름. 정부3,400호 산입블록은 미확정',
                    HOME_출처=byid['DOC_d434d2066efaf0c9142e5a57']['evidence_url'],
                    필요자료='블록별 실제 착공 원장 및 정부3,400호 구성명세. A2는 9·7 귀속도 별도 검토')
            if n==30 and 'DOC_8a670d0ed212959af7fd608d' in byid:
                r.update(HOME_참고값=1160,
                    사유='조달청 공식 입찰설명서의 A1통합공공임대1,160호가 약1,200호와 반올림 양립하는 신규 후보. 기존 A2분양976호와 별개. 시공사 공사기간은2026-06-30~2029-08-18이나 실제 착공일·정부 산입·9·7 귀속은 미확정',
                    HOME_출처=byid['DOC_8a670d0ed212959af7fd608d']['evidence_url']+'|'+byid['DOC_b07e4706bed828b41f846c6c']['evidence_url'],
                    필요자료='A1실제 착공 증빙, 정부1,200호 대상블록·9·7 프로그램 귀속. A2에1,160호 가산 금지')
        elif n in [51,59]:
            r.update(HOME_참고값=14451 if n==51 else 4260,판정='부분범위',
                사유='중복·정정 계보를 정리한 원문 부분합. 공식 총계와 같은 모집단의 완결성이 미확정',
                HOME_출처='../official_followup_sources_20261021/rental_partial_notices.csv' if n==59 else '../official_additional_checks_20261021/A01_public_sale_partial.csv')
            if n==59 and extra_magok:
                r.update(HOME_참고값=4461,사유='기존 공식 모집 부분합4,260+강서구 마곡도전숙 최초모집201=4,461. 정책 미확정 원천 포함 공개 공고 부분합이며 정부14,700의 동일 모집단 완결성은 미확정',
                    HOME_출처='../additional_mapping_review_20261021/rental_partial_notices_updated.csv|'+extra_magok['evidence_url'])
        elif 53<=n<=58 or 61<=n<=65:
            name=original['지역·사업지'].replace('서울','');parent='A01' if n<=58 else 'A02'
            match=next((m for m in named if m['parent_check_id']==parent and m['name']==name),None)
            if match:
                r.update(HOME_동일범위비교값=int(match['home_notice_units']),HOME_근거ID=match['home_ids'],HOME_출처=match['evidence_urls'],
                    판정='비교가능',비교기준='최초 실제 모집 공고·유형별 금회 공급 호수',사유=match['interpretation'],독립검증여부='개별 공고 원천으로 대조')
                if n==64:r.update(판정='부분범위',HOME_참고값=822,사유='A2국민438+A4행복384=822호는 임대 전체. 금회 모집은219+187=406호. 순환용411호·별도 어린이집5호 제외. 정부800호 산입 범위 미공개')
        elif n in [52,60,66,67,68,69]:
            r.update(판정='계획범위유보',사유='공식 계획과 HOME 계획·실제 모집은 구분. 통합공고·정정·유형을 포함한 같은 범위 명세가 필요')
            if n==66 and extra_magok:
                r.update(판정='사업특정유보',HOME_참고값=201,HOME_근거ID=extra_magok['id'],
                    HOME_출처=extra_magok['evidence_url'],
                    사유='강서구5월4일 공식 최초모집201호를 신규 확보.200호 개략량과 양립하지만 마곡17 임대196호와 별개이며 정부 서울마곡의 대상공고·9·7 귀속은 미확정',
                    필요자료='정부 서울마곡0.2천호의 사업명·공고번호와 정책 프로그램 귀속 근거')
            if n in [67,68,69]:
                word={67:'과천지식',68:'구리갈매역세권',69:'인천부평'}[n]
                selected=[c for c in cohorts if word in c['name']]
                values=[]
                for c in selected:
                    plans=[s for s in c['schedules'] if s['stage']=='SUPPLY' and '2026-10-01'<=s.get('due_date','')<='2026-12-31']
                    if plans:values.append(min(c['units'],max(s.get('units') or 0 for s in plans)))
                r.update(HOME_참고값=sum(values) if values else None,HOME_근거ID='|'.join(c['id'] for c in selected))
                if n==67 and 'COL_f6d8ddba0dcbc8db5917e486' in byid:
                    p=ps['PRO_6a66b31b8f84244d491514e6']
                    assert sum(i['units'] for i in p['rows'])==1424
                    assert all(i['supply_month']=='2026-10' and i['tenure']=='행복주택' for i in p['rows'])
                    r.update(HOME_동일범위비교값=1424,판정='계획부합',비교기준='4분기 공공임대 모집계획; 실제 모집실적 아님',
                        사유='LH S12 행복주택 면적별420+288+716=1,424호,10월 공급계획.1.4천호에 반올림 부합',
                        HOME_출처=p['evidence_url'],필요자료='향후 실제 모집공고로 계획 이행 여부 추적',
                        독립검증여부='기관 공급계획과 정부 계획 대조; 실제 공급 실적 검증과 구분')
                if n==68 and 'COL_478ecda8cc32b044bdbd4ca9' in byid:
                    r.update(HOME_참고값=896,
                        HOME_근거ID='PRO_b0f7e7ded4e31142e5b39d02|PRO_2dfb63f2826a3d14481c2fb4',
                        HOME_출처=ps['PRO_b0f7e7ded4e31142e5b39d02']['evidence_url'],
                        사유='과거 LH 임대계획 A1행복609+A3 6년임대287=896은900에 반올림 양립. A3는 최신 원천목록에 없음. 전체 공사량·유형 미확인 추정을 섞은1,258을 비교값으로 쓰지 않음',
                        필요자료='A3 모집계획 존속·변경 및 정부 산입블록 확인')
        elif n in [70,71,72]:
            r.update(판정='행정명부미수집',사유='145개 행정과제와 완료 증빙 명부 없음. 사업 수·호수로 대체 검증하지 않음')
        elif n in [73,74,75,76,77,78,79,80,81,82]:
            if n in [73,77,78]:
                ids=['STA_28b9d99f45c14fd2ec949c59'] if n==73 else ['STA_d83270b0ed182b769aecde0e'] if n==77 else ['STA_d83270b0ed182b769aecde0e','STA_384d1dc374e1b207f2519842','STA_afee5e449ef73927862c86df']
                val=sum(byid[i]['units'] for i in ids)
            elif n==75:
                val=(39940/28441-1)*100;ids=['STA_28b9d99f45c14fd2ec949c59']
            else:
                metric='준공' if n==82 else '분양승인' if n in [80,81] else '착공'
                regions=['서울특별시'] if n in [74,76,81] else list(REGIONS.values())
                val,ids=stat(metric,regions,'202601' if n in [74,76] else '202608','202608')
                if n==76:
                    prev,pids=stat('착공',['서울특별시'],'202501','202508');ids+=pids;val=(val/prev-1)*100 if prev and val else None
            r.update(HOME_동일범위비교값=val,HOME_근거ID='|'.join(ids),판정='비교가능',
                비교기준='HOME 별도 보유 서울/수도권 전체 공식 통계. 9·7 사업 합계와 구분',
                사유='기간·지역·단위가 같은 공식 통계. 공통 생산기관의 통계여서 독립적인 정책사업 전수 검증은 아님',
                HOME_출처='https://stat.molit.go.kr/portal/api/apiList.do',독립검증여부='보유 지역 통계와 대조; 9·7 사업 검증 아님')
            if n==76 and val is not None:
                r.update(HOME_과거공표판본값=(20679/14654-1)*100,
                    판정='공표판본차이' if round(val)!=41 else '비교가능',
                    사유='당시8월 PDF의2025년 누계14,654호와 최신 API 전년값을 구분. 2026년 실적20,679호는 유지')
        elif 83<=n<=110:
            metric='인허가' if n<=97 else '착공'
            typ='TOTAL' if n<=87 or 98<=n<=102 else 'APARTMENT' if n<=92 or 103<=n<=105 else 'NON_APARTMENT'
            ids=[]
            def q(year):
                if metric=='인허가':return pdf[(year,7,typ)]
                return start_type(year,typ)
            current=q(2026);previous=q(2025);average=sum(q(y) for y in [2023,2024,2025])/3 if n not in [103,104,105] else None
            mode='previous' if n in [84,89,94,99,104,107] else 'average' if n in [85,90,95,100,108] else 'growth' if n in [86,91,96,101,105,109] else 'avg_growth' if n in [87,92,97,102,110] else 'current'
            val={'current':current,'previous':previous,'average':average,'growth':(current/previous-1)*100,'avg_growth':(current/average-1)*100 if average else None}[mode]
            historical=None
            if metric=='착공':
                hc=pdf_start[(2026,7,typ)];hp=pdf_start[(2025,7,typ)]
                ha=(q(2023)+q(2024)+hp)/3 if mode in ['average','avg_growth'] else None
                historical={'current':hc,'previous':hp,'average':ha,'growth':(hc/hp-1)*100,'avg_growth':(hc/ha-1)*100 if ha else None}[mode]
            raw_value=val
            if mode=='average':
                val=float(Decimal(str(val)).quantize(Decimal(1),rounding=ROUND_HALF_UP))
                if historical is not None:historical=float(Decimal(str(historical)).quantize(Decimal(1),rounding=ROUND_HALF_UP))
            r.update(HOME_동일범위비교값=val,HOME_반올림전값=raw_value,HOME_과거공표판본값=historical,판정='비교가능',
                비교기준='서울 전체 유형별 통계; 원문 월별 PDF와 최신 API를 구분',
                사유='인허가 월별 API 부족은 공식 PDF 유형별 누계로 보완. 착공 전년값은 최신 API 확정·개정치를 사용',
                HOME_출처='monthly_202607.pdf|monthly_202507.pdf|monthly_202407.pdf|typed_starts_jan_feb.json',
                독립검증여부='공식 원천 경로 교차 대조; 같은 생산통계 파생값 중복 계상 금지')
            if metric=='착공' and historical is not None and abs(val-historical)>1e-8:
                historical_fit=precision_check(original,historical)[0]
                r.update(판정='공표판본차이' if historical_fit else '과거평균판본미확정',
                    사유='당시 월간 PDF와 현재 API의 과거값이 다름. 당시 판본으로 발표치 재현 가능; 최신 값으로 무조건 맞추지 않음' if historical_fit else
                    '원문 연도별 값과 최신 API 값은 확보했으나 발표의3년 평균과 해당 공표판본을 완전히 재현하지 못함. 판본 차이만으로 단정하지 않음')
        elif 111<=n<=114:
            r.update(판정='세부원장미확보',사유='정비사업 하위 집계와 분모 명세 부족. 시도 전체 통계에서 단순 추정하지 않음')
        elif n>=118:
            r.update(판정='범위다름',사유='시도 전체 장래목표·구역 수·누적 공급·금융지원 또는 개별 선정계획. 9·7 연결 사업의 단계 호수와 직접 비교 불가')
            if n in [180,181]:r.update(사유='굴포천역 남측 공식 계획은 확인했으나 3080+ 기존 사업. 이 원문만으로9·7 정책 귀속을 추가하지 않음')
            if n in [182,183,184]:
                c=next(c for c in cohorts if c['id']=='PRO_30970726b72b0633c3d177fd')
                r.update(HOME_동일범위비교값=c['units'] if n==182 else None,판정='비교가능' if n==182 else '부분집합또는예산',
                    HOME_참고값=80 if n==183 else 38.2,HOME_근거ID=c['id'],HOME_출처=source_urls['I03'],
                    사유='전체1,006호 중 특화80호는 부분집합. 38.2억원은 예산. 착공·입주 실적으로 가산하지 않음',독립검증여부='기존 사업계획과 공식 선정자료 대조')
        if n in [85,87,90,92,95,97]:
            r.update(판정='평균공표기준유보',사유='확보한2023~2025 월간 PDF 판본으로 평균을 재계산하면 발표 평균과 다름. 같은 확정·개정 기준의 과거 유형별 원표 미확보; 단순 반올림 차이로 설명 불가')
        compatible,method,unit,diff=precision_check(original,r['HOME_동일범위비교값'])
        r.update(수량표현부합=compatible,표현비교=method,반올림단위=unit or float(quantum(original)),수량차이=diff)
        if r['판정']=='비교가능':r['판정']='부합' if compatible else '절삭가능_확인유보' if compatible is None and r['HOME_동일범위비교값'] is not None else '수치차이' if compatible is False else '자료미확보'
        if r['HOME_과거공표판본값'] is not None:
            r['과거판본표현부합']=precision_check(original,r['HOME_과거공표판본값'])[0]
        r['원본_입력검증상태']=original.get('검증결과(자동)')
        r['내부 수집값(입력)']=r['HOME_동일범위비교값']
        r['수치 차이(자동)']=r['수량차이']
        r['검증결과(자동)']=r['판정']
        rows.append(r)
    assert len(rows)==185 and len({r['지표ID'] for r in rows})==185
    csvwrite(OUT/'official_185_comparison.csv',rows)
    dump(OUT/'official_185_comparison.json',rows)
    issues=[]
    for item in book['교차검증_쟁점']:
        value=Decimal(item['비교 A 수치'])-Decimal(item['비교 B 수치'])
        issues.append(dict(item,재계산차이=float(value),HOME_판정='공식자료 내부 산식·정밀도 점검; 독립 HOME 검증 개수에 합산하지 않음'))
    csvwrite(OUT/'official_18_crosscheck_issues.csv',issues)
    dump(OUT/'comparison_summary.json',dict(indicators=185,status_counts=dict(Counter(r['판정'] for r in rows)),
        independent_policy_accuracy_percentage=None,reason='분모·기간·계획·과제·파생 지표가 달라 전체 일치율 산출 금지'))
    print((OUT/'comparison_summary.json').read_text())


if __name__=='__main__':main()
