"""Read-only reconciliation of supplied 2026-11-05 references.

Input: immutable capture directory (capture.py / source_fetch.json), never a DB
connection. Does not modify policy/business facts. Original CSV columns retained.
Run: python scripts/verify_official_20261105.py /tmp/official1105
"""
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/verification'
INPUT = OUT / '20261105_inputs'
FIELDS = ['id','공식제목','근거자료ID','원문URL','원문검증상태','공식발표일','공식집계기준','공식값','공식상한','단위','수치성격','매칭_시스템_경로','매칭_테이블_필드','시스템_조회조건','시스템_기준일','시스템값','비교연산자','차이값','판정','불일치원인','원문_증거_위치','DB_증거_위치','중복_상위하위관계','개선권고','우선순위','판정근거']


def load(path):
    return json.loads(path.read_text())


def norm(value):
    return re.sub(r'[\s,]', '', str(value))


def num(value):
    if value in (None, ''):
        return None
    value = float(value)
    return int(value) if value.is_integer() else value


def compare(official, actual, same_basis, operator='='):
    """A numerical difference is valid only for the same population and period."""
    if actual is None:
        return 'DB항목없음', None
    if not same_basis:
        return '집계기준불일치', None
    if operator == '>=':
        return ('하한충족' if actual >= official else '불일치'), actual - official
    return ('일치' if actual == official else '불일치'), round(actual - official, 6)


def csvwrite(name, rows):
    columns = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k,v in row.items()} for row in rows)


def public_payload(data):
    """Only review conclusions and official source evidence may be public."""
    fields = ['id','공식제목','근거자료ID','원문URL','원문검증상태','공식발표일','확인된_공식발표일','공식집계기준','공식값','단위','수치성격','시스템값','차이값','판정','판정근거','중복_상위하위관계','개선권고','검증정정','원문_증거_위치','원문_근거요약','원문_증거URL']
    public = {k:[{f:r[f] for f in fields if f in r} for r in data[k]] for k in ['metrics','projects']}
    public.update(counts=data['manifest']['counts'],sources=data['sources'],reconciliation=data['reconciliation'])
    return public


def refresh_public_document(data):
    path = ROOT/'docs/데이터 신뢰도 확인.html'
    html = path.read_text()
    marker = '<script type="application/json" id="official-verification-data">'
    if marker not in html:
        return
    payload = json.dumps(public_payload(data),ensure_ascii=False,separators=(',',':')).replace('<',r'\u003c').replace('>',r'\u003e').replace('&',r'\u0026')
    assert not any(k in payload for k in ['source_revision_id','payload_hash','PRO_','시스템_조회조건','매칭_사업ID'])
    start = html.index(marker)+len(marker)
    end = html.index('</script>',start)
    path.write_text(html[:start]+payload+html[end:])


def main(capture):
    raw = load(capture/'db/raw.json') + load(capture/'extra.json')
    projects = load(capture/'db/projects.json')
    screen = load(capture/'db/screen.json')
    live = load(capture/'live-screen.json')
    snapshot = load(capture/'db/snapshot.json')
    fetched = {r['자료ID']: r for r in load(capture/'source_fetch.json')}
    candidates = load(capture/'numeric_candidates.json')
    inputs = {name: list(csv.DictReader((INPUT/(name+'.csv')).open(encoding='utf-8'))) for name in ['공식발표목록','성과검증기준','사업별검증기준','20261016_성과_선행기준','20261016_사업_선행기준']}
    stamp = snapshot['snapshot_at']
    scope = ', '.join(snapshot['kinds'] + ['official_observation','external_benchmark'])
    evidence = {}
    corpus = [(r, norm(json.dumps(r['payload'],ensure_ascii=False))) for r in raw]

    def dbref(rows, fields):
        return [dict(id=r['id'], kind=r['kind'], source_id=r['source_id'], revision_no=r['revision_no'], payload_hash=r['payload_hash'], fields={k:r['payload'].get(k) for k in fields}) for r in rows]

    def source_location(rid, snippet):
        meta = fetched[rid]
        for a in meta.get('attachments',[]):
            if not a.get('verified'): continue
            for page,text in enumerate((capture/'sources'/rid/a['text_file']).read_text().split('\f'),1):
                if snippet in norm(text):
                    return dict(url=a['url'],sha256=a['sha256'],location=f"{rid} · {a['file']} PDF {page}쪽",excerpt=snippet)
        if snippet in norm((capture/'sources'/rid/'text.txt').read_text()):
            return dict(url=meta['final_url'],sha256=meta['sha256'],location=rid+' · 공식 게시물 본문/제목',excerpt=snippet)
        return dict(url=meta['final_url'],sha256=meta['sha256'],location=rid+' · 원문 재확인 필요',excerpt=snippet)

    def locate_metric(r):
        rid, id = r['근거ID'],r['검증ID']
        snippets = candidates[id]
        if id == 'K014': snippet = '21.8~23.5만호'
        elif id == 'K023': snippet = '연말까지3기신도시약2천호를포함해1만호규모공공분양주택을분양공고할예정'
        elif id == 'K025': snippet = next(x for x in snippets if '공공임대주택의경우' in x and '3분기' in x)
        elif id == 'K035': snippet = next(x for x in snippets if '정례브리핑은월2회' in x)
        elif id in ('K033','K034'): snippet = next(x for x in snippets if '21개과제중12개과제' in x)
        else: snippet = snippets[0]
        return source_location(rid,snippet)

    def base(original, id, title, rid, url, value, period, nature, related):
        row = dict(original)
        # Preserve every original column; normalized comparison fields are additional.
        for k in FIELDS: row.setdefault(k,'')
        row.update(id=id,공식제목=title,근거자료ID=rid,원문URL=url,원문검증상태='원문 수치·문맥 확인',공식발표일=original.get('발표일'),공식집계기준=period,공식값=value,단위=original['단위'],수치성격=nature,시스템_기준일=stamp,시스템값=None,차이값=None,판정='DB항목없음',비교연산자='비교보류',매칭_시스템_경로='운영 DB 현재 유효 리비전 → 정책 추진현황 조회 모델',매칭_테이블_필드='Revision.payload / Mapping / ProgramMapping',시스템_조회조건='superseded_at IS NULL; '+scope,DB_증거_위치='20261105_evidence.json#'+id,중복_상위하위관계=related,개선권고='공식 대조 기준으로 보관. 집계 정의·기준일이 같은 운영 필드를 확보한 뒤 대사.',우선순위='P2',판정근거='조회한 관리 필드에서 동일 단위·지역·기간의 독립 집계값을 찾지 못함. 원문/검색 결과의 숫자는 사업 실적으로 대입하지 않음.',불일치원인='해당 관리지표 또는 동일 범위의 집계 항목 미확보')
        return row

    def setvalue(row, value, basis, condition, note, dbrows=(), fields=(), operator='='):
        result,diff = compare(num(row['공식값']), value, basis,operator)
        row.update(시스템값=value,판정=result,차이값=diff,비교연산자=operator if basis else '비교보류',시스템_조회조건=condition,판정근거=note,불일치원인='' if result in ('일치','하한충족') else note,우선순위='P1' if result=='불일치' else 'P2')
        evidence[row['id']]['database'] = dbref(dbrows,fields)

    metrics=[]
    targetrows=[r for r in raw if r['kind']=='policy_delivery_plan']
    actual = screen['portfolio_comparisons']['policy']['metrics']['CONSTRUCTION']['actual_points'][-1]
    cases={r['id']:r for r in screen['official_alignment']['cases']}
    stat2026=[r for r in raw if r['kind']=='statistic' and r['payload'].get('region')=='서울특별시' and r['payload'].get('statistic_metric')=='착공' and r['payload'].get('statistic_frequency')=='MONTH' and '202601'<=r['payload'].get('statistic_period','')<='202607']
    stat2025=[r for r in raw if r['kind']=='statistic' and r['payload'].get('region')=='서울특별시' and r['payload'].get('statistic_metric')=='착공' and r['payload'].get('statistic_frequency')=='MONTH' and '202501'<=r['payload'].get('statistic_period','')<='202507']
    assert len(stat2026)==7 and len(stat2025)==7
    refs=[r for r in raw if r['kind']=='statistic_reference' and r['payload'].get('region')=='서울특별시' and r['payload'].get('statistic_period')=='202608']
    fields=['region','statistic_metric','statistic_frequency','statistic_period','units','source_date','evidence_url']
    for r in inputs['성과검증기준']:
        id=r['검증ID']; row=base(r,id,r['공식성과지표'],r['근거ID'],r['출처URL'],r['공식값'],r['집계기간'],r['수치성격'],r['관련·중복관계'])
        src=locate_metric(r);row['원문_증거_위치']=src['location'];row['원문_근거요약']=src['excerpt'];row['원문_증거URL']=src['url'];row['원문_SHA256']=src['sha256']
        evidence[id]={'source':src,'database':[],'searched_kinds':scope,'query_scope':'current revisions only; no historical knowledge-time restoration'}
        if '재확인' in src['location']:row.update(원문검증상태='원문재확인필요',판정='원문재확인필요')
        if id=='K001':
            setvalue(row,screen['target_units'],True,'policy_delivery_plan[POL_2025_0907].target_units; 원안 2026~2030', '9·7 원안의 동일 착공목표 1,350,000호. 원문은 총 135만호 규모이므로 입력표의 목표하한 분류를 정액 목표로 해석해 비교.',targetrows,['policy_id','target_units','announced_at','period_start','period_end'])
            row['검증정정']='입력 분류 목표하한 → 원문 총 135만호 규모. 원본 수치성격 컬럼 보존.'
        elif id=='K002':
            setvalue(row,screen['target_units'],False,'policy_delivery_plan[POL_2025_0907].target_units; 9·7 원안','현재 정책은 9·7 원안 135만호, 비교 기준은 1·29·8·13을 포함한 후속 통합 150만호 이상. 버전이 달라 차감·가산하지 않음.',targetrows,['policy_id','target_units','announced_at'])
        elif id=='K011':
            setvalue(row,screen['annual'][0]['units'],False,'policy_delivery_plan annual(year=2026).target_units; 원안','현재 원안 연간 목표 269,000호와 10월 통합 발표 268,000호는 목표 버전이 다름. 원안 목표를 교체하지 않음.',targetrows,['annual','announced_at'])
        elif id=='K013':
            setvalue(row,actual['units'],False,'policy-delivery/view → portfolio_comparisons.policy.metrics.CONSTRUCTION.actual_points[-1]','현재 연결 사업의 누적 단계 도달량 81,131호(관측일 기반 추정 69,986호 포함)와 정부 부문별 8·9·10월 혼합 기준 99,000호 이상은 모수·시점·측정 방식이 다름. 숫자 차이를 미수집 실적으로 단정하지 않음.')
            evidence[id]['projection']=dict(actual)
            row['원문_기간정정']='R13 PDF 3~4쪽: 민간정비 9월, 기타주택 8월, 나머지 부문별 마감일 일부 미제시'
        elif id in ('K061','K062','K063'):
            if id=='K061':
                val={r['payload']['statistic_frequency']:r['payload']['units'] for r in refs};setvalue(row,val['YTD']-val['MONTH'],True,'statistic_reference 서울 202608 인허가 YTD - MONTH; 39,940 - 11,306','같은 공식 월간 통계의 1~8월 누계에서 8월 단월을 제외하여 1~7월 28,634호 재현. 발표값을 DB에 대입하지 않음.',refs,fields)
            elif id=='K062':setvalue(row,sum(r['payload']['units'] for r in stat2026),True,'statistic 서울/착공/MONTH/202601~202607; 월별 중복 키 없음','7개월 원천 통계 합계 19,507호. 정책 연결사업 집계와 별개인 지역 공식통계 대사.',stat2026,fields)
            else:
                growth=round((sum(r['payload']['units'] for r in stat2026)/sum(r['payload']['units'] for r in stat2025)-1)*100,1)
                setvalue(row,growth,True,'statistic 서울/착공/MONTH; (2026년 1~7월 19,507 / 2025년 동기 13,631 - 1) × 100; 소수 첫째 자리','현재 보유 월별 통계로 43.1%, 발표는 44.4%: -1.3%p. 같은 기간 비교이나 통계 개정/발표 분모 차이는 미확인. 기존 실적을 임의 수정하지 않고 발표 당시 분모·개정 이력 확인 필요.',stat2026+stat2025,fields)
                row['개선권고']='서울시 발표 당시 전년도 동기 분모와 국토부 수정통계 이력을 확보해 재검증.'
        elif id=='K069':
            plan=screen['plan']; regions=plan.get('regions',{})
            profile=next(x for x in raw if x['kind']=='policy_profile')
            val=profile['payload'].get('overrides',{}).get('region:경기도',{}).get('value')
            setvalue(row,val,False,'policy_profile.overrides[region:경기도].value; 9·7 정책 기간별 배분','숫자는 800,000호로 같지만 지자체 2030 주거종합계획과 9·7 착공목표 배분은 사업종류·집계축이 같다는 근거가 없어 일치로 판정하지 않음.',[profile],['policy_id','base_date'])
        elif id in ('K058','K059','K060'):
            matches=[p for p in projects if p['id'] in ['PRO_29bf4cef6fb4606948bb3b48','PRO_bc01f01ac015b15530c7e35b']]
            evidence[id]['project_candidates']=[dict(id=p['id'],name=p['name'],units=p.get('planned_units'),source_id=p['source_id']) for p in matches]
            if id=='K058':
                setvalue(row,1057,False,'project district=고양창릉, block=S-02; 동일 블록 두 원천을 합산하지 않음','S-2BL 규모는 DB 1,057호와 발표 1,057세대가 수치상 대응. 단위와 모집계획 범위의 동일성은 미확인하여 직접 일치 판정을 유보.',[r for r in raw if r['kind']=='project' and r['id'] in {p['id'] for p in matches}],['name','district','block','planned_units','unit_basis','evidence_url'])
            else:row['판정근거']='S-2 전체 규모는 보유하나 해당 블록의 지분적립형 284세대/초기 지분 25% 관리 필드를 찾지 못함. 광교 지분적립형은 다른 사업이므로 제외.'
        # Locate documents by specific subject names, never by a common number alone.
        search_terms={ 'K036':['서울강서','남양주도심','광주역세권'],'K037':['김포아라','구리건원'],'K038':['신규택지'],'K039':['김포아라'],
            'K040':['김포아라'],'K041':['구리건원'],'K042':['하남미사'],'K043':['하남감일2'],'K044':['의정부다락원'],'K045':['고양대곡'],
            'K048':['동자동'],'K049':['동자동'],'K050':['동자동'],'K055':['329-32'],'K056':['329-32']}.get(id,[])
        if search_terms:
            found=[x for x,t in corpus if any(norm(term) in t for term in search_terms)]
            evidence[id]['document_or_project_candidates']=dbref(found,['name','title','planned_units','project_id','url','evidence_url'])
            if row['시스템값'] is None and found:row['판정근거']+=' 관련 문서/사업 '+str(len(found))+'건은 존재하나 동일 범위의 확정 관리지표는 미확보.'
        corrections={
            'K014':'21.8만~23.5만호는 연말 전망 범위의 하단. 확정 실적 아님.',
            'K015':'21.8만~23.5만호는 연말 전망 범위의 상단. 확정 실적 아님.',
            'K020':'R13 서면 PDF 4쪽 민간정비 ~9월 표기. 입력표의 일괄 10월2주 집계기간을 직접 대사 기준으로 사용하지 않음.',
            'K021':'R13 서면 PDF 4쪽 기타주택 ~8월 표기. 발언록 총괄 기준과 세부 집계기준을 구분.',
            'K025':'R14 공공임대 약 1만5천호; R13 서면 1.47만호. 개략/정밀 표기 차이이며 확정 300호 오류로 판정하지 않음.',
            'K031':'R13 서면 PDF 5쪽에 나머지 97건 정상추진중을 직접 명시. 145−48 산식도 맞지만 추산만 있는 값은 아님. 완료 실적으로 사용 금지.',
            'K038':'27,200+76,700=103,900. 표제 약 104,000과 100호 차이는 천 호 단위 반올림.',
            'K075':'R23 공식 게시물 등록일 2025-11-27 확인. 2032년까지 약 23만 세대 도시개발 계획으로 9·7 착공실적과 분리.'}
        if id in corrections:row['검증정정']=corrections[id]
        if id=='K020':row['공식집계기준']='2026년 1~9월 · 공식 서면 세부 기준'
        if id=='K021':row['공식집계기준']='2026년 1~8월 · 공식 서면 세부 기준'
        if id=='K013':row['공식집계기준']='명목 10월 2주 · 부문별 8월/9월/10월 혼합'
        if id=='K075': row['확인된_공식발표일']='2025-11-27'
        if id in ('K012','K016','K018','K020','K021'):
            # Existing comparison constants repeat a briefing: they cannot validate it independently.
            row['판정근거']+=' 화면 official_alignment의 동일 발표 기준 상수는 존재하나 독립 DB 실적 대사로 세지 않음.'
        row['DB_검색완료']=True
        metrics.append(row)

    project_rows=[]
    metric_by_id={r['id']:r for r in metrics}
    for r in inputs['사업별검증기준']:
        id=r['사업 검증ID'];n=int(id[1:]);rid=r['근거자료ID']
        row=base(r,id,r['사업지 / 블록'],rid,r['공식 URL'],r['공식 발표물량'],r['기준시점/주요일정'],r['성격(실적/계획)'],r['중복·검증 주의'])
        if n<=16:
            term={1:'고양창릉',2:'인천계양',3:'하남교산',4:'왕숙2',5:'중계본동',6:'흑석11',7:'신림2',8:'고양창릉',9:'부천대장',10:'남양주왕숙',11:'고덕강일',12:'광교',13:'과천지식',14:'인천계양',15:'고양창릉',16:'부천대장'}[n]
            text=norm((capture/'sources'/rid/'text.txt').read_text())
            needle={'P006':'흑석11구역약2500호','P014':'내년말','P015':'고양창릉','P016':'부천대장'}.get(id,term)
            # Include all matching contexts; annual plan statements are not current completions.
            phrases={
                1:'고양창릉과인천계양에서각각2300호',2:'고양창릉과인천계양에서각각2300호',
                3:'하남교산과남양주왕숙2에서각각1100호',4:'하남교산과남양주왕숙2에서각각1100호',
                5:'중계본동약3100호',6:'흑석11구역약2500호',7:'신림2구역약1400호',
                8:'고양창릉1100호부천대장500호남양주왕숙400호',9:'고양창릉1100호부천대장500호남양주왕숙400호',10:'고양창릉1100호부천대장500호남양주왕숙400호',
                11:'고덕강일에서1300호',12:'광교에서600호',13:'과천지식정보타운1400호',
                14:'올해12월인천계양에서처음으로입주를시작합니다.',15:'내년에는고양창릉부천대장에서속도감있게입주를진행하겠습니다.',16:'내년에는고양창릉부천대장에서속도감있게입주를진행하겠습니다.'}
            snippet=phrases[n]
            assert snippet in text, (id,snippet)
            src=source_location(rid,snippet)
        else:
            mid={17:40,18:41,19:42,20:43,21:44,22:45,23:58,24:59,25:48,26:49,27:50,28:55}[n]
            src=evidence[f'K{mid:03}']['source']
        row.update(원문_증거_위치=src['location'],원문_근거요약=src['excerpt'],원문_증거URL=src['url'],원문_SHA256=src['sha256'])
        evidence[id]={'source':src,'database':[],'searched_kinds':scope}
        if n<=16:
            case=cases[f'S{n:02}'];ids=set(case['source_project_ids']);matches=[x for x in raw if x['kind']=='project' and x['id'] in ids]
            val=case['managed_capacity'] if row['공식값'] else None
            if val is not None:
                setvalue(row,val,False,'official_alignment.cases[S%02d] → linked project IDs; canonical dedup managed_capacity'%n,'같은 지구의 연결사업은 식별했지만 발표의 일부 블록·해당 단계·기준시점과 현재 보유 전체 규모가 다름. 개략값 차이를 누락 또는 오류로 단정하지 않음.',matches,['name','district','block','planned_units','start_actual_date','unit_basis','evidence_url'])
            else:
                row.update(판정='집계기준불일치',시스템_조회조건='official_alignment.cases[S%02d].source_project_ids; quantity not announced'%n,판정근거='지구 내 사업은 식별했으나 입주계획의 대상 블록·실제 입주일과 동일성 미확인. 공식 물량 미제시이므로 0 또는 지구 전체값으로 채우지 않음.')
                evidence[id]['database']=dbref(matches,['name','district','block','planned_units','completion_plan_date','evidence_url'])
            evidence[id]['case']=dict(id=case['id'],source_project_ids=case['source_project_ids'],canonical_members=case['members'],comparison_eligible=case['comparison_eligible'])
            row['매칭_사업ID']='; '.join(case['source_project_ids'])
            if n==6:
                row.update(판정='원문재확인필요',원문검증상태='공식자료간차이',우선순위='P1',판정근거='R13 서면 PDF 4쪽 흑석11 0.15만호(약1,500), R14 발언록 PDF 5쪽 약2,500호. DB는 1,515호. 공식 원문 간 차이가 있어 어느 값도 임의 채택하지 않음.',개선권고='발표기관 정오표/정정 공지 또는 사업 인가·착공 원문으로 발표 물량의 차이를 확인.',불일치원인='공식 서면과 발언록의 물량 차이')
                evidence[id]['source_conflict']=[source_location('R13','흑석11구역(0.15만호)'),source_location('R14','흑석11구역약2500호')]
        elif n in (23,24):
            template=metric_by_id['K058' if n==23 else 'K059'];
            for k in ['시스템값','판정','차이값','시스템_조회조건','판정근거','불일치원인']:row[k]=template[k]
            evidence[id]['database']=evidence['K058']['database']; row['매칭_사업ID']='PRO_29bf4cef6fb4606948bb3b48; PRO_bc01f01ac015b15530c7e35b'
        else:
            terms={17:['김포아라'],18:['구리건원'],19:['하남미사'],20:['감일2'],21:['다락원'],22:['고양대곡'],25:['동자동'],26:['동자동'],27:['동자동'],28:['329-32']}[n]
            found=[x for x,t in corpus if any(norm(term) in t for term in terms)]
            matches=[x for x in found if x['kind']=='project']
            evidence[id]['database']=dbref(found,['name','title','project_id','planned_units','url','evidence_url'])
            row['시스템_조회조건']='현재 유효 리비전 이름/본문 검색 '+', '.join(terms)+'; '+scope
            row['매칭_사업ID']='; '.join(x['id'] for x in matches)
            row['판정근거']=('동일 위치 사업은 존재하나 목표물량·일정 필드가 미확보.' if matches else '동일 사업/지구의 운영 project 레코드를 찾지 못함.')+' 관련 문서 '+str(sum(x['kind']=='document_evidence' for x in found))+'건 검색됨. 문서 등장만으로 등록·연결·실적 반영을 확정하지 않음.'
            row['우선순위']='P1';row['개선권고']='공식 지구지정/후보지 공고와 동일 사업 식별을 확인하여 등록·목표 보강 절차에서 검토. 현재 발표는 미래 계획이므로 착공실적에 가산 금지.'
        row['DB_검색완료']=True
        project_rows.append(row)

    sources=[]
    for r in inputs['공식발표목록']:
        rid=r['자료ID'];meta=fetched[rid];good=[a for a in meta.get('attachments',[]) if a.get('verified')]
        row=dict(r,원문검증상태='공식 게시물 확인 · PDF '+str(len(good))+'개 검증' if good else '공식 게시물 본문/제목 확인 · HWP 미검증',확인시각=meta['checked_at'],HTTP상태=meta['status'],최종URL=meta['final_url'],HTML_SHA256=meta['sha256'],PDF증거=[{k:a[k] for k in ['text','url','sha256','file']} for a in good],확인된_발표일='2025-11-27' if rid=='R23' else r['발표일'],원문_검증범위='접속·공식 도메인·제목·게시일·해당 지표 문맥/수치; HWP 전체 및 모든 첨부의 완전성 검증 아님',관련항목=[x['id'] for x in metrics+project_rows if x['근거자료ID']==rid],주의사항='')
        if rid in ('R13','R14'):row['주의사항']='흑석11구역 서면 약1,500호/발언록 약2,500호 상충. K020 민간정비9월·K021 기타8월 기준.'
        if rid=='R12':row['주의사항']='214·168은 공식 게시물 제목으로 확인. HWP 본문의 사업별 범위는 미검증.'
        sources.append(row)

    checks=[
        ('V01','목표 버전 분리','135만 원안 / 150만 이상 통합. 현재 DB 135만; 추가 가산 없음. K001 일치, K002 집계기준불일치.'),
        ('V02','목표·실적·모수 분리','268,000 목표 / 99,000 이상 공식 실적 / 81,131 연결사업 누계는 별도. 민간8·9월 혼합 기준; 독립 모수 미확보. 원안 연간목표269,000 유지.'),
        ('V03','전망 구간','218,000~235,000호 연말 전망을 상·하단으로 보관. 확정실적·부족분으로 계산하지 않음.'),
        ('V04','공공주택 부분집합','공식 문장에 3기 신도시7,300호를 포함한 공공주택16,200호 명시. 가산 금지.'),
        ('V05','서울 부분집합','13,000 전체 신축매입 중 서울3,600. 포함관계 확인, 가산 금지.'),
        ('V06','6개 후보지 합계','37,000+14,600+12,000+6,500+2,600+4,000=76,700. 원문 산술 일치. 미래 후보지 계획, 운영 사업 미등록은 P017~P022 참조.'),
        ('V07','발표 정밀도','27,200+76,700=103,900 → 천 호 단위 반올림104,000. 100호를 일반 오류로 처리하지 않음.'),
        ('V08','동자동 유형 분할','1,000임대+1,150분양=2,150전체. 전체와 하위 유형 중복 합산 금지.'),
        ('V09','S-2 부분집합','1,057세대 중284세대 지분적립형. DB 블록규모1,057호는 존재; 284 유형관리 미확보, 호/세대 동일성 검증 전 비교보류.'),
        ('V10','과제 진행 상태','145−48=97. 입력표의 추산과 달리 R13 PDF5쪽에97건 정상추진중을 명시. 완료는48건이며97건 가산 금지.'),
        ('V11','경기도 집계축','170,000공공+630,000민간=800,000. 공공임대265,000은 건설·매입·전세임대 포함한 별도 축. 9·7 경기도 배분800,000과 숫자 같아도 동일지표 아님.'),
        ('V12','선행표 계승','K→M 및 P→S의 ID·물량을 전수 대조. 원본 CSV 보존; 미기재값은 미검증으로 처리. source_conflict는 숫자 덮어쓰기 없이 기록.'),
        ('V13','공급·입주 단계 분리','Q4분양10,000 및 임대5,000이상은 같은 분기의 서로 다른 모집 유형; 총모집15,000이상 문구와 산술 정합. 중복 없는 사업 단위 실적은 미확보, 운영 합산 안 함. 입주100,000은 별도 기간·단계.'),
        ('V14','지구·블록 구분','창릉 착공2,300 / Q4분양1,100 / S-2규모1,057 별도 행 유지. 동일지구 이름/근사 물량만으로 블록 확정하지 않음.'),
        ('V15','지역통계 별도 대사','서울1~7월 인허가28,634·착공19,507 일치. 증가율44.4% 대 DB43.1% 불일치(-1.3%p), 개정 분모 재확인. 지자체계획을 중앙 실적에 합산 안 함.')]
    # Preserve the cross-version relationships and report genuine value changes.
    previous=[]
    for table,ref,key,current in [('20261016_성과_선행기준','10월16일 기존표ID','검증ID',metrics),('20261016_사업_선행기준','10.16 사업표 ID','사업 검증ID',project_rows)]:
        old=inputs[table]
        for row in current:
            oldid=row.get(ref)
            if not oldid:continue
            matches=[x for x in old if oldid in x.values()]
            previous.append(dict(id=row['id'],previous_id=oldid,previous=matches[0] if matches else None,current_official_value=row['공식값']))
    for p in previous:
        old=p['previous'] or {}; vals=[v for k,v in old.items() if k in ('공식값','공식 발표물량','공식 발표치(호)','값','공식값/하한','값(하한·단일)','발표물량')]
        p['comparison']='선행표 원본 필드 확인' if not vals else ('동일' if str(vals[0])==str(p['current_official_value']) else '버전 차이 확인 필요')
    live_check=dict(target_equal=screen['target_units']==live['target_units'],map_reconciliation_equal=screen['map_reconciliation']==live['map_reconciliation'],construction_equal=actual['units']==live['portfolio_comparisons']['policy']['metrics']['CONSTRUCTION']['actual_points'][-1]['units'],target_units=live['target_units'],construction_units=actual['units'])
    assert all(live_check[k] for k in ['target_equal','map_reconciliation_equal','construction_equal'])
    counts=dict(Counter(r['판정'] for r in metrics+project_rows))
    manifest=dict(version='20261105-v1',verified_at_kst='2026-11-05',snapshot=snapshot,input_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in INPUT.glob('*.csv')},live_screen_check=live_check,counts=counts,metrics=len(metrics),projects=len(project_rows),sources=len(sources),business_writes=0,automatic_refresh=False,limitations=['현재 유효 리비전 대사이며 발표 당시 인지시점 스냅샷을 복원한 것은 아님','원문 수치 확인과 운영 실적 일치는 별개','DB항목없음은 명시한 조회 범위 내 동일 기준 필드 미확보이며 자료 자체 부재를 뜻하지 않음','원문PDF 일부·HTML 확인; HWP 본문과 모든 첨부 전수검증 아님'])
    payload=dict(manifest=manifest,metrics=metrics,projects=project_rows,sources=sources,reconciliation=[dict(id=i,title=t,result=d) for i,t,d in checks])
    refresh_public_document(payload)
    (OUT/'20261105_verification.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')))
    (OUT/'20261105_evidence.json').write_text(json.dumps(dict(manifest=manifest,evidence=evidence,previous=previous),ensure_ascii=False,indent=2))
    csvwrite('20261105_metrics.csv',metrics);csvwrite('20261105_projects.csv',project_rows);csvwrite('20261105_sources.csv',sources)
    (OUT/'20261105_reconciliation.md').write_text('# 2026-11-05 포함관계·산식 검증\n\n운영 DB 수정 없음. 아래 판정은 원문 구조·검증표 적용 결과이며 모든 지표의 운영 실적 일치를 뜻하지 않습니다.\n\n'+'\n\n'.join('## '+i+' · '+t+'\n\n'+d for i,t,d in checks)+'\n\n입력표에 명시된 M/S 연결 40건의 값은 모두 선행표와 동일합니다. 나머지 선행 항목까지 포함한 원본 53행은 `20261105_inputs/`에, 명시 연결 결과는 `20261105_evidence.json`의 `previous`에 보존했습니다.\n')
    summary=f'''# 9·7 및 후속 주택공급 발표 — 공식자료 대조 결과\n\n검증일 2026-11-05 · DB 읽기 전용 스냅샷 {stamp} · 운영 사업 데이터 수정 0건\n\n24개 공식 게시물과 성과지표77개·사업지표28개를 대조했습니다. 원문 확인과 운영 DB의 동일 기준 일치를 구분합니다. 이 검증표는 정책실적의 신규 입력자료가 아닙니다.\n\n## 판정\n\n'''+ '\n'.join(f'- {k}: {v}건' for k,v in counts.items())+'''\n\n`DB항목없음`은 현재 조회 범위에서 동일 기준의 관리 필드를 찾지 못한 경우입니다. 문서만 보유한 경우와 사업 등록·실적 반영을 구분했습니다. 숫자를 비교할 수 없는 경우 시스템값·차이는 빈칸으로 보존합니다.\n\n## 실제 대사 결과\n\n|항목|공식|시스템|판정|\n|---|---:|---:|---|\n|원안 착공목표|1,350,000호|1,350,000호|일치|\n|후속 통합 목표|1,500,000호 이상|원안1,350,000호|버전 다름|\n|2026 연간 착공목표|268,000호|원안269,000호|버전 다름|\n|10월 발표 착공|99,000호 이상|연결사업 누계81,131호|모수·기간·측정 방식 다름|\n|서울1~7월 인허가|28,634호|39,940−11,306=28,634호|일치|\n|서울1~7월 착공|19,507호|7개월 합19,507호|일치|\n|서울 착공 전년비|44.4%|19,507÷13,631−1=43.1%|불일치, 분모 개정 확인 필요|\n|흑석11|서면약1,500/발언록약2,500|1,515호|공식자료간차이|\n|창릉S-2|1,057세대 중284세대|전체1,057호, 유형별284 미확보|범위·단위 검증 필요|\n|신규택지|27,200+76,700=103,900|발표표제104,000|천 호 반올림, 운영실적 아님|\n\n81,131호에는 관측일 기반 추정값69,986호가 포함됩니다. 정부99,000호와의 차이를 누락량 또는 오류로 단정하지 않았습니다. 현재 화면 API의 목표·지도대사·착공누계를 읽기 전용 산출 모델과 비교해 일치함을 확인했습니다.\n\n## 우선 확인할 사항\n\n- P006: 흑석11 공식 서면(PDF4쪽)과 발언록(PDF5쪽) 수치 상충. 기존1,515호 변경 없음.\n- K063: 발표44.4%와 현재 월별통계43.1% 차이. 당시 분모/통계개정 이력 미확인.\n- P017~P022: 신규6개 후보지는 관련 수집문서가 있으나 현재 운영사업 레코드 미확인. 후보계획76,700호를 착공실적에 가산하지 않음.\n- P025~P028: 동자동은 관련 문서가 있지만 동일 운영사업 미확인, 불광329-32는 사업 존재하나 목표물량 미확보. 정식 등록·목표 보강 검토 대상으로 제시.\n- K020/K021: 민간정비9월·기타주택8월의 혼합 마감. 일괄10월2주 기준 대사 금지.\n- K031:97건은 단순 추산만이 아니라 공식 서면에 정상추진중이라고 직접 명시. 완료는48건.\n- R23: 공식 게시물 등록일2025-11-27 확인.\n\n## 재현·근거·범위\n\n원본 CSV5개는 `20261105_inputs/`에 행·컬럼을 보존하고 SHA256을 JSON에 기록했습니다. `20261105_evidence.json`에 원문 URL·파일해시·페이지/문맥, DB 리비전ID·해시·값, 검색 범위, 선행M/S표를 보존했습니다. 무조건적인 신뢰도 점수는 산정하지 않습니다.\n\n검증은 PostgreSQL REPEATABLE READ READ ONLY 트랜잭션에서 현재 유효 리비전11,731행과 455개 사업을 읽었습니다. 추가 official_observation/external_benchmark 조회는0행입니다. 발표 기준일 당시 인지 상태를 복원하지 않았으며 비교 시점을 명시했습니다. 정부 표를 반복 저장한 official_alignment 상수는 독립 실적 일치로 세지 않았습니다.\n\n공식 게시물24건은 HTTP200으로 확인했습니다. 성공한 PDF만 검증 첨부로 표시했고 HWP 전체는 검증하지 않았습니다. R12의214/168은 공식 제목에서 확인했습니다.\n\n운영사업·매핑·목표·실적·수집설정 변경 및 ETL 실행은 없습니다. 화면은 저장한 검증표만 표시하므로 열람 시 DB 재집계나 외부 원문 재수집을 수행하지 않습니다.\n\nCSV3종·요약·포함관계 검증서·상세증거 JSON은 관리자 인증 후 화면에서 내려받을 수 있습니다. 공개 화면에는 내부 리비전·사업ID를 제외한 검증 요약만 표시합니다.\n'''
    (OUT/'20261105_summary.md').write_text(summary)
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__': main(Path(sys.argv[1]))
