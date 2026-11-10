from . import inheritance, report_interactions
"""Evidence-preserving practical report; shared resources reconcile by explicit IDs."""
import html,re
from . import report_charts


def esc(v):return html.escape(str(v),quote=True)
def enabled(r):return any(t['values'].get('overview') for t in r['tasks'])
def records(value):
    lines=[]
    for line in value.splitlines():
        if lines and not re.match(r'^\s*(?:예산코드|관계자ID)[:：]',line):lines[-1]+=' '+line.strip()
        elif line.strip():lines.append(line)
    return [{m.group(1).strip():m.group(2).strip() for part in line.split('|') if (m:=re.fullmatch(r'\s*([^:：]+)[:：]\s*(.+?)\s*',part))} for line in lines]
def amount(v):
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)원',v or ''):raise ValueError('원 단위 금액 필요')
    return int(v[:-1].replace(',',''))
MONEY=['편성액','집행액','지급예정액','가용잔액']


def shared(r,key,id_key,required):
    found={};problems=[]
    for t in r['tasks']:
        raw=t['values'].get(key,'');rows=records(raw)
        if not raw:problems.append(f"{t['values']['title']}: {key} 미기재")
        for row in rows:
            if not all(row.get(k) for k in required):
                problems.append(f"{t['values']['title']}: {key} 구조 확인 필요");continue
            rid=row[id_key];entry=found.setdefault(rid,{'data':row,'works':[],'refs':[],'conflict':False,'human':False})
            if entry['data']!=row:entry['conflict']=True
            if t['number'] not in entry['works']:entry['works'].append(t['number'])
            entry['refs']=sorted(set(entry['refs']+t['provenance'].get(key,{}).get('refs',[])))
            entry['human'] |= t['provenance'].get(key,{}).get('human',False)
    for rid,e in found.items():
        if e['conflict']:problems.append(f'{rid}: 같은 식별자의 값 불일치 — 원문 대조 필요')
    return list(found.values()),problems


def resources(r):
    budgets,problems=shared(r,'budget','예산코드',['예산코드','명칭',*MONEY,'기준일','범위'])
    contacts,notes=shared(r,'contacts','관계자ID',['관계자ID','성명','소속','역할','연락','협의사항'])
    totals={k:0 for k in MONEY};valid=True
    for e in budgets:
        try:
            nums={k:amount(e['data'][k]) for k in MONEY}
            if nums['편성액']!=sum(nums[k] for k in MONEY[1:]):raise ValueError('수지 불일치')
            if e['conflict']:raise ValueError('불일치')
            e['amounts']=nums
            for k in MONEY:totals[k]+=nums[k]
        except ValueError:
            valid=False;problems.append(e['data']['예산코드']+': 금액 대조 필요·전체 합계 미확정')
    if not budgets or problems:valid=False
    if len({e['data']['기준일'] for e in budgets})>1:
        valid=False;problems.append('예산 기준일이 서로 달라 전체 합계를 확정하지 않음')
    return {'budgets':budgets,'contacts':contacts,'totals':totals if valid else None,'notes':problems+notes}


def refs(p):
    mark='전임자 입력' if p.get('human') else '원문 기록' if p.get('refs') else '근거 미기재'
    return '<small class="cite">'+mark+' '+ report_interactions.citation(p.get('refs',[]))+'</small>'
def fact(t,key,label):
    return f'<div class="fact"><h3>{esc(label)}</h3><p>{esc(t["values"].get(key) or "자료에 미기재 — 인계자 확인 필요")}</p>{refs(t["provenance"].get(key,{}))}</div>'
def table(headers,rows,cls=''):
    return f'<div class="table-wrap"><table class="{cls}"><thead><tr>'+''.join(f'<th>{esc(v)}</th>' for v in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{v}</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def plan(t,key,headers):
    value=t['values'].get(key,'');rows=[line.split('|') for line in value.splitlines() if line.strip()]
    if not rows or any(len(row)!=len(headers) for row in rows):return fact(t,key,'추후 계획' if key=='future_plan' else '추진 계획')
    return table(headers,[[esc(x.strip()) for x in row] for row in rows])+refs(t['provenance'].get(key,{}))
def metrics(t):
    out='';raw=t['values'].get('performance','');rows=records(raw)
    for row in rows:
        if not all(row.get(k) for k in ['지표','실적','목표','단위']):return fact(t,'performance','성과 지표')
        try:a=float(row['실적']);b=float(row['목표']);assert a>=0 and b>0
        except (ValueError,AssertionError):return fact(t,'performance','성과 지표')
        p=min(100,a/b*100)
        out+=f'<div class="metric"><b>{esc(row["지표"])}</b><strong>{esc(row["실적"])} / {esc(row["목표"])} {esc(row["단위"])}</strong><div class="track"><i style="width:{p:.2f}%"></i></div></div>'
    return '<div class="metric-grid">'+out+'</div><small>개별 실적 ÷ 목표를 표시합니다. 전체 업무 달성률과는 다른 지표입니다.</small>'+refs(t['provenance'].get('performance',{}))


def render_html(r):
    shared_data=resources(r);tasks=r['tasks']
    body=f'<section class="sheet cover"><div class="eyebrow">업무바통 · 상세실무편 · 동일 확정본</div><h1>업무 인수인계 보고서</h1><h2>{esc(r["title"])}</h2><p>인계자 {esc(r["predecessor"])} → 인수자 {esc(r["successor"])}<br>현안 기준일 {esc(r["basis"])} · 확정 판본 {esc(r["revision_id"][:8])}</p>'
    body+=inheritance.banner(r)+report_charts.dashboard(r)+'<p class="muted">보고 진행률은 원문 수치입니다. 기준정보·예산·연락망은 진행보고와 구분해 종합했습니다. 업무 개요 → 추진 경과 → 현안 → 실행 절차 순서로 읽으세요.</p></section>'
    body+='<nav>'+''.join(f'<a href="#task-{t["number"]}">업무 {t["number"]}</a>' for t in tasks)+'<a href="#budget">공통 예산</a><a href="#contacts">관계자</a></nav>'
    body+='<section class="sheet" id="priorities"><div class="eyebrow">인수자의 첫 업무</div><h2>우선순위와 실행 순서</h2><p>기한이 지났거나 임박한 업무, 진행을 막는 실제 현안을 먼저 처리합니다. 자료의 불일치는 마지막 참고란에서 확인합니다.</p>'
    order={'overdue':0,'soon':1,'issue':2,'normal':3,'complete':4}
    for t in sorted(tasks,key=lambda t:order.get(t['urgency']['key'],9)):
        v=t['values'];body+=f'<article class="priority {t["urgency"]["key"]}"><h3>{t["number"]:02d} {esc(v["title"])}</h3><b>{esc(t["urgency"]["label"])} · {esc(v["owner"])} · {esc(v["due_date"])}</b><p>{esc(v["issues"] or "현안 기록 없음 — 확인 필요")}</p><p><strong>바로 할 일</strong> {esc(v["next_action"] or "인계자 확인 필요")}</p>{refs(t['provenance'].get('next_action',{}))}</article>'
    body+='<div class="callout"><b>인수 당일 확인 · 시스템 권고</b><p>자료 열람 확인 → 기한 경과·임박 업무 담당과 일정 대조 → 필요한 자료 요청 → 인수 확인 기록. 향후 산출물은 이미 존재하는 문서로 처리하지 않습니다.</p></div></section>'
    for t in tasks:
        v=t['values'];body+=f'<section class="sheet" id="task-{t["number"]}"><div class="eyebrow">업무 {t["number"]:02d} / A · 맥락과 현재 위치</div><h2>{esc(v["title"])}</h2><div class="work-meta">{esc(v["owner"])} · 기한 {esc(v["due_date"])} · {esc(t["urgency"]["label"])} · 보고 달성률 {t["progress"] if t["progress"] is not None else "미기재"}%</div>'
        body+=report_charts.version_history(t)
        if t.get('inheritance_status'):body+='<p class="inheritance-task">'+esc(t['inheritance_status'])+(' · 이전 기준의 기록입니다. 최신 현황을 재확인하세요.' if t['inheritance_status']=='이전 보고서 유지' else '')+'</p>'
        for key,label in [('overview','업무 개요'),('objectives','목표')]:body+=fact(t,key,label)
        # A short timeline preserves source-stage distinction without repeating every field.
        trend=report_charts.timeline(t);a=trend.find('<svg');b=trend.find('</svg>',a)
        body+='<h3>계획에서 현재까지 · 보고 흐름</h3>'+(trend[a:b+6] if a>=0 else '')
        body+=table(['보고일 / 단계','달성률','그때까지의 실적','당시 현안'],[[esc((e['reported_at'] or '미기재')+' / '+(e['stage'] or '미기재')+(' / '+str(e['revision_no'])+'차' if e.get('revision_no') is not None else '')),esc(str(e['progress'])+'%' if e['progress'] is not None else '미기재'),esc(e['values']['completed_work']),esc(e['values']['issues'])] for e in t['timeline']])
        body+=fact(t,'status','현재 진척')+metrics(t)+fact(t,'issue_history','현안의 발생·해소·잔여 경과')
        body+='</section>'
        body+=f'<section class="sheet"><div class="eyebrow">업무 {t["number"]:02d} / B · 실행과 완료 판단</div><h2>{esc(v["title"])} · 다음 담당자의 실행서</h2><h3>추진 계획</h3>'+plan(t,'implementation_plan',['기간','단계 / 할 일','산출물'])
        body+='<h3>추후 계획 · 담당·일정·결과물</h3>'+plan(t,'future_plan',['시점','담당','구체적 조치','남길 결과물','일정의 성격'])
        for key,label in [('remaining_work','남은 업무'),('operating_steps','실무 처리 순서'),('completion_criteria','완료 판단 기준'),('deliverables','인계 산출물 · 제공 여부'),('approval_route','보고·결재 체계'),('document_locations','자료를 찾고 접근하는 방법')]:body+=fact(t,key,label)
        if t.get('match_history'):
            body+='<div class="callout"><b>동일 업무 확인 기록</b>'+''.join(f'<p>{esc(m["source_title"])} → {esc(m["target_title"])}<br>{esc(m["reason"])}</p>' for m in t['match_history'])+'</div>'
        body+='</section>'
    body+='<section class="sheet" id="budget"><div class="eyebrow">공통 운영 정보</div><h2>업무별 예산과 공동 경비</h2><p>동일 예산코드는 한 번만 합산합니다. 집행액·지급예정액·가용잔액을 구분하며, 예산 집행률은 업무 진척률을 뜻하지 않습니다.</p>'
    if shared_data['totals']:
        body+='<div class="money-grid">'+''.join(f'<div><small>{k}</small><b>{v:,}원</b></div>' for k,v in shared_data['totals'].items())+'</div>'
    else:body+='<p class="callout">전체 합계 미확정 — 아래 원문 값과 식별자·기준일을 대조하세요.</p>'
    rows=[]
    for e in shared_data['budgets']:
        d=e['data'];rows.append([esc(d['예산코드'])+'<br>'+esc(d['명칭']),*map(lambda k:esc(d[k]),MONEY),esc(', '.join(map(str,e['works'])))+refs(e)])
    body+=table(['예산 / 명칭',*MONEY,'연결 업무'],rows)
    for e in shared_data['budgets']:
        d=e['data'];n=e.get('amounts');body+=f'<h3>{esc(d["예산코드"])} · {esc(d["명칭"])}</h3>'
        if n and n['편성액']>0:
            body+='<div class="budget-bar" role="img" aria-label="'+esc(' / '.join(k+' '+d[k] for k in MONEY))+'">'+''.join(f'<span style="width:{100*n[k]/n["편성액"]:.3f}%;background:{color}"></span>' for k,color in zip(MONEY[1:],['#286852','#c28a3b','#dbe5df']))+'</div>'
        body+=f'<small>기준일 {esc(d["기준일"])} · {esc(d["범위"])}'+(' · 값 불일치' if e['conflict'] else '')+'</small>'
    body+='<p class="muted">■ 짙은 녹색: 집행 / ■ 황색: 지급 예정 / ■ 연녹색: 가용 잔액. 금액은 원문 기준이며 지급 예정은 집행 완료가 아닙니다.</p>'
    if shared_data['notes']:
        body+='<details><summary>집계 전 예산·연락처 원문</summary>'+''.join(fact(t,'budget',t['values']['title']+' 예산')+fact(t,'contacts','연락처') for t in tasks)+'</details>'
    if shared_data['notes']:body+='<details><summary>예산·연락망 대조 참고</summary>'+''.join(f'<p>{esc(n)}</p>' for n in shared_data['notes'])+'</details>'
    body+='</section><section class="sheet" id="contacts"><div class="eyebrow">공통 운영 정보</div><h2>관계자 연락망 · 누구에게 무엇을 확인할까</h2><p>같은 관계자ID는 하나로 모으고 관련 업무를 함께 표시합니다. 연락처는 원문의 기록이며 변경 시 담당자에게 재확인하세요.</p>'
    body+=table(['성명 / 소속','역할 / 협의사항','연락처','업무'],[[esc(e['data']['성명'])+'<br>'+esc(e['data']['소속']),esc(e['data']['역할'])+'<br>'+esc(e['data']['협의사항']),esc(e['data']['연락'])+('<br>⚠ 정보 불일치' if e['conflict'] else ''),esc(', '.join(map(str,e['works'])))+refs(e)] for e in shared_data['contacts']])
    body+='<h3>보고·협의 순서</h3>'+table(['업무','보고·결재 경로'],[[esc(t['values']['title']),esc(t['values'].get('approval_route','미기재'))] for t in tasks])+'</section>'
    if any(t.get('image_reviews') for t in tasks):
        body+='<section class="sheet" id="image-review"><h2>최신본 그림 판독 참고</h2><p>GPT-5.4가 채택된 최신 파일의 그림만 판독했습니다. 원본 대조가 필요한 참고이며 본문 확정 사실과 구분합니다.</p>'
        for t in tasks:
            for v in t.get('image_reviews',[]):body+='<h3>'+esc(t['values']['title'])+'</h3><p>'+esc(v['path']+' / '+v['location'])+'</p><blockquote>'+esc(v['text'])+'</blockquote>'
        body+='</section>'
    body+='<section class="appendix"><details class="source-records"><summary>원문 기록</summary>'+''.join(f'<article class="source" id="source-{s["number"]}"><b>[{s["number"]}] {esc(s["path"])}</b><small>{esc(s["location"])}</small><blockquote>{esc(s["quote"])}</blockquote></article>' for s in r['sources'])+'</details><details><summary>자료 검토 참고 · 미확인 사항·변경 이력</summary>'+''.join(f'<p>{esc(w)}</p>' for w in r['warnings'])+''.join(f'<p>{esc(c["task"])} / {esc(c["field"])}: {esc(c["before"])} → {esc(c["after"])} · {esc(c["reason"])}</p>' for c in r['changes'])+'</details></section>'
    return '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>업무바통 · 인수인계 상세실무편</title><style>'+CSS+report_charts.CSS+'</style></head><body>'+body+'</body></html>'

CSS='''
*{box-sizing:border-box}body{font:14px/1.65 "Noto Sans CJK KR",system-ui,sans-serif;color:#213e35;background:#e9eeea;margin:0;overflow-wrap:anywhere}.sheet,.appendix{max-width:1080px;margin:24px auto;padding:38px 46px;background:white;border-radius:12px}.eyebrow{font-size:12px;letter-spacing:.1em;color:#688076}h1{font-size:32px;line-height:1.3;margin:10px 0}h2{font-size:23px;line-height:1.4;margin:12px 0 18px}h3{font-size:14px;margin:14px 0 5px;color:#265c48}p{margin:7px 0;white-space:pre-wrap}small,.muted,.cite{font-size:11px;color:#677d71}small{display:block}.cite{margin:4px 0}a{color:#286b50}.fact{margin:12px 0}.fact p{margin:4px 0}.work-meta,.callout{background:#eef4ef;padding:12px 16px;border-left:3px solid #377255}.work-meta{font-weight:600}.priority{border:1px solid #dde6de;border-left:5px solid #51755c;padding:14px 20px;margin:14px 0;border-radius:7px}.priority.overdue{border-left-color:#af4239;background:#fff8f4}.priority.soon{border-left-color:#be862e}.priority h3{margin-top:0}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{text-align:left;vertical-align:top;padding:9px 8px;border-bottom:1px solid #dce5df}th{background:#edf3ee;font-weight:600}th:first-child{min-width:90px}.metric-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:12px}.metric{background:#f1f6f1;padding:10px 12px}.metric b,.metric strong{display:block}.metric strong{font-size:20px}.track,.budget-bar{height:12px;border-radius:5px;background:#dce6de;overflow:hidden;margin-top:7px}.track i{display:block;height:100%;background:#37725a}.budget-bar{height:24px;display:flex}.budget-bar span{display:block;height:100%}.money-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:20px 0}.money-grid div{background:#edf4ee;padding:12px}.money-grid b{display:block;font-size:18px}nav{max-width:1080px;margin:20px auto;display:flex;gap:22px;flex-wrap:wrap}details{margin:16px 0;padding:16px;background:#f3f6f1}summary{cursor:pointer}.source{padding:15px 0;border-bottom:1px solid #dce5df}blockquote{white-space:pre-wrap;margin:10px 0;padding-left:12px;border-left:3px solid #acc6b5}.meta{font-size:10px;color:#6e7e73}ul{padding-left:22px}.cover .executive{margin:18px 0}.trend-svg{margin:3px 0!important}.source:target{background:#fff3c9}details:has(.source:target)::details-content{content-visibility:visible}details:has(.source:target)>.source{display:block}
@media(max-width:650px){.sheet,.appendix{padding:22px 15px;margin:12px 0;border-radius:0}nav{padding:0 15px;gap:12px}.metric-grid,.money-grid{grid-template-columns:1fr 1fr}table{min-width:620px}h1{font-size:26px}.metric strong{font-size:17px}}
@page{size:A4;margin:11mm 12mm}
@media print{body{background:white;font-size:10px;line-height:1.5}.sheet{margin:0;padding:0;border-radius:0;max-width:none;break-after:page}.sheet:last-of-type{break-after:auto}.appendix{margin:0;padding:0}.appendix details:not([open]){display:none}.appendix:not(:has(details[open])){display:none}.sheet:has(+.appendix){break-after:auto}.cover>.muted{display:none}h1{font-size:24px}h2{font-size:18px;margin:7px 0 11px}h3{font-size:11px;margin:10px 0 3px}p{margin:4px 0}small,.cite,.muted{font-size:8px}.eyebrow{font-size:9px}.fact{margin:7px 0}.fact p{margin:3px 0}table{font-size:9px;min-width:0}th,td{padding:6px 5px}th:first-child{min-width:0}tr,.fact,.metric-grid,.priority{break-inside:avoid}h2,h3{break-after:avoid}.table-wrap{overflow:visible}.work-meta,.callout{padding:8px 10px}.metric-grid{margin-top:8px;gap:7px}.metric{padding:7px 9px}.metric strong{font-size:16px}.priority{margin:10px 0;padding:12px 16px}.money-grid b{font-size:14px}.money-grid{gap:5px}.money-grid div{padding:8px}nav{display:none}a{color:inherit;text-decoration:none}.cover .executive{margin:10px 0}.cover .executive-kpis b{font-size:18px}.cover .portfolio-chart{font-size:9px}.cover .portfolio-chart .chart-sub,.cover .portfolio-chart small{font-size:8px}.cover .portfolio-chart td{padding:6px}.cover .bar-svg{height:25px}.trend-svg{height:75px!important}.meta{font-size:8px}}
'''


def markdown_resources(r):
    data=resources(r);lines=['','## 공통 예산 · 동일 코드 중복 제외','']
    if data['totals']:lines+=[' / '.join(f'{k}: {v:,}원' for k,v in data['totals'].items()),'']
    lines+=['| 예산코드 | 명칭 | 편성액 | 집행액 | 지급예정액 | 가용잔액 | 기준일 |','|---|---|---|---|---|---|---|']
    for e in data['budgets']:lines+=['| '+' | '.join(esc(e['data'][k]).replace('|','&#124;') for k in ['예산코드','명칭',*MONEY,'기준일'])+' |']
    lines+=['','## 공통 연락망 · 동일 관계자ID 중복 제외','','| 관계자 | 소속 | 역할 | 연락 | 협의사항 | 업무 |','|---|---|---|---|---|---|']
    for e in data['contacts']:lines+=['| '+' | '.join(esc(e['data'][k]).replace('|','&#124;') for k in ['성명','소속','역할','연락','협의사항'])+' | '+','.join(map(str,e['works']))+' |']
    lines+=['']+['- '+esc(n) for n in data['notes']]
    return lines


def docx_resources(doc,r):
    data=resources(r);doc.add_heading('공통 예산 · 동일 코드 중복 제외',1)
    if data['totals']:doc.add_paragraph(' / '.join(f'{k}: {v:,}원' for k,v in data['totals'].items()))
    def add(headers,rows):
        tbl=doc.add_table(rows=1,cols=len(headers));tbl.style='Light Shading Accent 1'
        for c,v in zip(tbl.rows[0].cells,headers):c.text=v
        for row in rows:
            for c,v in zip(tbl.add_row().cells,row):c.text=str(v)
    add(['예산코드 / 명칭',*MONEY],[[e['data']['예산코드']+' / '+e['data']['명칭'],*[e['data'][k] for k in MONEY]] for e in data['budgets']])
    doc.add_heading('공통 관계자 연락망',1)
    add(['성명 / 소속','역할 / 협의사항','연락','업무'],[[e['data']['성명']+' / '+e['data']['소속'],e['data']['역할']+' / '+e['data']['협의사항'],e['data']['연락'],','.join(map(str,e['works']))] for e in data['contacts']])
    for note in data['notes']:doc.add_paragraph(note)


def render_docx(r):
    import io
    from datetime import datetime
    from docx import Document
    from docx.shared import Pt,Inches,Cm
    from docx.oxml.ns import qn
    doc=Document();section=doc.sections[0];section.top_margin=Cm(1.5);section.bottom_margin=Cm(1.5)
    style=doc.styles['Normal'];style.font.name='맑은 고딕';style.font.size=Pt(9)
    style.element.rPr.rFonts.set(qn('w:eastAsia'),'맑은 고딕');style.paragraph_format.space_after=Pt(4)
    def tab(headers,rows):
        tbl=doc.add_table(rows=1,cols=len(headers));tbl.style='Light Shading Accent 1'
        for c,v in zip(tbl.rows[0].cells,headers):c.text=v
        for row in rows:
            for c,v in zip(tbl.add_row().cells,row):c.text=str(v)
    def field(t,key,label):
        doc.add_heading(label,3);doc.add_paragraph(t['values'].get(key) or '자료에 미기재 — 인계자 확인 필요')
        p=t['provenance'].get(key,{});doc.add_paragraph(('전임자 입력' if p.get('human') else '원문 기록')+' '+','.join(f'[{n}]' for n in p.get('refs',[])),style='Caption')
    doc.add_heading('업무 인수인계 보고서 · 상세실무편',0);doc.add_heading(r['title'],1)
    if r.get('inheritance'):
        doc.add_heading('이전 인계 보고서 기반 · 인수인계 이력',2)
        for line in inheritance.chain_lines(r):doc.add_paragraph(line)
    doc.add_paragraph(f"인계자 {r['predecessor']} → 인수자 {r['successor']} / 기준일 {r['basis']}")
    doc.add_picture(report_charts.gantt_png(r),width=Inches(6.1))
    doc.add_paragraph('회색: 계획 기간 / 색 막대: 원문 달성률 / 붉은 연장: 기한 경과 / 세로선: 기준일. 업무 번호는 아래 표와 같습니다.',style='Caption')
    tab(['업무','달성률 / 일정','현안 / 다음 행동'],[[f"{t['number']}. {t['values']['title']}",f"{t['progress']}% / {t['urgency']['label']}",t['values']['issues']+' / '+t['values']['next_action']] for t in r['tasks']])
    doc.add_paragraph('HTML·PDF와 같은 확정 판본의 편집용 사본입니다. 외부 편집은 앱 확정본을 변경하지 않습니다.')
    for t in r['tasks']:
        doc.add_page_break();doc.add_heading(f"{t['number']}. {t['values']['title']} · 맥락과 현황",1)
        if any(e.get('report_id') for e in t.get('version_history',[])):
            doc.add_paragraph('본문 판본 선택: '+t.get('chronology_note',''))
            latest=t.get('latest_report',{})
            if latest:doc.add_paragraph('현재 기준본: '+latest['path']+' / '+str(latest.get('reported_at'))+' / '+str(latest.get('revision_no'))+'차')
            labels={'selected':'현재 기준본','superseded':'이전·중복 기록','excluded':'현재 기준에서 제외','ambiguous':'확인 필요'}
            tab(['파일','본문 기준일','차수 / 수정일시','상태 / 판정'],[[e['path'],e.get('reported_at') or '미기재',str(e.get('revision_no') or '미기재')+'차 / '+(e.get('issued_at') or '미기재'),(e.get('document_state') or '미기재')+' / '+labels.get(e.get('selection_status'),'기록')] for e in t['version_history']])
        if t.get('inheritance_status'):doc.add_paragraph(t['inheritance_status']+' · 이전 내용 유지 항목은 최신 현황 재확인')
        for k,label in [('overview','업무 개요'),('objectives','목표')]:field(t,k,label)
        doc.add_heading('보고 흐름',2)
        tab(['보고일 / 단계','달성률','실적','당시 현안'],[[str(e['reported_at'])+' / '+str(e['stage']),str(e['progress'])+'%',e['values']['completed_work'],e['values']['issues']] for e in t['timeline']])
        for k,label in [('status','현재 진척'),('performance','실적과 목표'),('issue_history','현안 경과')]:field(t,k,label)
        doc.add_page_break();doc.add_heading(t['values']['title']+' · 실행서',1)
        for k,label,headers in [('implementation_plan','추진 계획',['기간','할 일','산출물']),('future_plan','추후 계획',['시점','담당','조치','산출물','일정 성격'])]:
            rows=[line.split('|') for line in t['values'].get(k,'').splitlines()]
            if rows and all(len(row)==len(headers) for row in rows):doc.add_heading(label,2);tab(headers,rows)
            else:field(t,k,label)
        for k,label in [('remaining_work','남은 업무'),('operating_steps','실무 처리 순서'),('completion_criteria','완료 기준'),('deliverables','인계 산출물'),('approval_route','보고·결재 체계'),('document_locations','자료 위치·접근 방법')]:field(t,k,label)
        if t.get('image_reviews'):
            doc.add_heading('최신본 그림 판독 참고 · 원본 대조 필요',2)
            for v in t['image_reviews']:
                doc.add_paragraph(v['path']+' / '+v['location']);doc.add_paragraph(v['text'])
        for m in t.get('match_history',[]):doc.add_paragraph('동일 업무 확인: '+m['reason'])
    doc.add_page_break();docx_resources(doc,r)
    doc.add_page_break();doc.add_heading('원본 색인·검토 참고',1)
    grouped={}
    for s in r['sources']:grouped.setdefault(s['path'],[]).append(s['number'])
    tab(['원본 파일','본문 근거 번호'],[[c['path'],', '.join(map(str,grouped.get(c['path'],[]))) or '검색·열람용 증빙대장'] for c in r['coverage']])
    doc.add_paragraph('상세 인용과 원문 위치는 동일 판본 HTML의 근거 부록 또는 Markdown에서 대조할 수 있습니다.')
    for w in r['warnings']:doc.add_paragraph(w)
    doc.add_paragraph(f"판본 {r['revision_id']}\n내용 해시 {r['hash']}\n확정 시각 {r['confirmed_at']}\n분석 모델 {r['model']}")
    doc.core_properties.title=r['title'];doc.core_properties.author='업무바통'
    stamp=datetime.fromisoformat(r['confirmed_at'].replace('Z','+00:00')).replace(tzinfo=None)
    doc.core_properties.created=stamp;doc.core_properties.modified=stamp
    output=io.BytesIO();doc.save(output);return output.getvalue()
