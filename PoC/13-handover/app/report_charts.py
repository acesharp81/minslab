"""Portable report-first SVG charts; source percentages only, accessible text alongside."""
import html
from datetime import date, timedelta

def esc(v):return html.escape(str(v),quote=True)
COLORS={'overdue':'#b34438','soon':'#bd781f','issue':'#a67b2c','complete':'#27705b','normal':'#507387'}
CSS='''
.executive{border:1px solid #cbd9d0!important;border-radius:14px;padding:22px!important;background:#f5f8f3;break-inside:avoid}.executive h2{margin:0 0 8px}.executive-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0}.executive-kpis div{background:white;padding:10px 14px;border-radius:8px;font-size:12px;color:#56665b}.executive-kpis b{font-size:27px;display:block;color:#20493c}.portfolio-chart{width:100%;table-layout:fixed;background:white;font-size:12px}.portfolio-chart th:nth-child(1){width:23%}.portfolio-chart th:nth-child(2){width:26%}.portfolio-chart th:nth-child(3){width:26%}.portfolio-chart th:nth-child(4){width:25%}.portfolio-chart td{vertical-align:top;padding:12px 9px}.portfolio-chart b{display:block}.portfolio-chart .chart-sub{font-size:11px;color:#627365;margin:5px 0}.bar-svg{width:100%;height:32px;display:block}.urgency-tag{display:inline-block;border-radius:5px;background:#f0ede5;font-size:11px;padding:3px 7px;font-weight:700;margin-top:4px}.report-timeline{border:1px solid #dae4da;border-radius:12px;padding:18px;margin:18px 0;background:#f9faf6;break-inside:avoid}.flow-nodes{display:flex;gap:10px;margin-top:12px}.flow-node{flex:1;min-width:0;position:relative;border-top:3px solid #82987d;background:white;padding:10px;font-size:12px}.flow-node:last-child{border-color:#23664d;background:#edf5e9}.flow-node:not(:last-child):after{content:'→';position:absolute;right:-11px;top:-15px;color:#537353;font-weight:bold}.flow-node b{display:block}.flow-node small{display:block;overflow-wrap:anywhere;color:#5b6c60}.flow-node p{margin:6px 0}.trend-svg{width:100%;height:110px;display:block;margin:8px 0}.latest-summary{background:#edf4e7;border-left:4px solid #3f7257;padding:14px;margin:12px 0}.latest-summary p{margin:4px 0}.match-note{font-size:11px;color:#61715e}.gantt-svg{display:block;width:100%;height:auto;min-width:660px}.gantt-wrap{overflow-x:auto;margin:18px 0}.gantt-legend{font-size:11px;display:flex;flex-wrap:wrap;gap:15px;margin:7px 0;color:#5c6f60}.gantt-legend i{display:inline-block;width:18px;height:9px;margin-right:5px}.report-chart-note{font-size:11px;color:#62705f}.report-detail-reference{font-size:12px;color:#65745f}
@media(max-width:650px){.executive{padding:12px!important}.executive-kpis{grid-template-columns:repeat(2,1fr)}.portfolio-chart{min-width:680px}.flow-nodes{flex-direction:column}.flow-node:not(:last-child):after{display:none}.executive .chart-scroll{overflow-x:auto}.executive{break-inside:auto}}
@media print{.executive{padding:12px!important;break-inside:auto}.gantt-wrap{break-inside:avoid}header{padding-bottom:8px}header h1{font-size:24px}header h2{font-size:17px}header p{margin:4px 0}.gantt-svg{min-width:0}.gantt-wrap{overflow:visible;margin:8px 0}.executive h2{font-size:18px}.executive-kpis{margin:10px 0}.executive-kpis b{font-size:21px}.portfolio-chart{font-size:10px;min-width:0}.portfolio-chart td{padding:7px}.executive .chart-scroll{overflow:visible}.report-timeline{break-inside:avoid}.flow-node{font-size:10px}.trend-svg{height:90px}}
'''

def bar(progress,color):
    if progress is None:return '<div class="chart-sub">진행률 미기재 · 수치 추정 안 함</div>'
    p=max(0,min(100,int(progress)))
    return f'<svg class="bar-svg" viewBox="0 0 220 32" role="img" aria-label="원문 보고 진행률 {p}%"><title>원문 보고 진행률 {p}%</title><rect x="0" y="8" width="164" height="14" rx="7" fill="#e4eae1"/><rect x="0" y="8" width="{1.64*p}" height="14" rx="7" fill="{color}"/><text x="173" y="21" font-size="15" font-weight="700" fill="{color}">{p}%</text></svg>'

def dashboard(r):
    tasks=r['tasks'];counts={k:sum(t['urgency']['key']==k for t in tasks) for k in COLORS}
    body='<section class="executive" id="progress-overview"><div class="eyebrow">한눈에 보는 업무 진행 현황</div><h2>지금 어디까지 왔고, 다음에 무엇을 해야 하나</h2>'
    body+=f'<p class="report-chart-note">현안 판단 기준일 {esc(r["basis"])} · 진행률은 각 업무의 최신 보고에 명시된 값입니다. 문서 수·경과 시간으로 계산하지 않습니다.</p><div class="executive-kpis">'
    for label,v in [('인계 업무',len(tasks)),('기한 경과 · 이행 확인',counts['overdue']),('7일 이내 처리 기한',counts['soon']),('전체 업무 완료',counts['complete'])]:body+=f'<div><b>{v}</b>{label}</div>'
    body+='</div>'+gantt(r)+'<div class="chart-scroll"><table class="portfolio-chart"><thead><tr><th>업무 / 현재 단계</th><th>보고 진행률 / 기한</th><th>업무 현안</th><th>남은 일 / 바로 할 일</th></tr></thead><tbody>'
    for t in tasks:
        v=t['values'];u=t['urgency'];color=COLORS[u['key']];last=t['timeline'][-1] if t['timeline'] else {}
        body+=f'<tr><td><a href="#task-{t["number"]}"><b>{esc(v["title"])}</b></a><div class="chart-sub">{esc(v["status"] or "진행 상태 확인 필요")}</div><small>{esc(last.get("stage") or "단계 미기재")} · {len(t["timeline"])}개 보고 연결</small></td><td>{bar(t["progress"],color)}<span class="urgency-tag" style="color:{color}">{esc(u["label"])}</span><div class="chart-sub">기한 {esc(v["due_date"] or "미확인")}<br>담당 {esc(v["owner"] or "미확인")}</div></td><td>{esc(v["issues"] or "원문에 현안 미기재")}</td><td><b>{esc(v["remaining_work"] or "잔여 업무 확인 필요")}</b><div class="chart-sub">다음: {esc(v["next_action"] or "담당자 확인 필요")}</div></td></tr>'
    return body+'</tbody></table></div></section>'

def version_history(t):
    history=t.get('version_history',[])
    if not history or not any(e.get('report_id') for e in history):return ''
    latest=t.get('latest_report',{})
    body='<div class="report-detail-reference">'
    if latest:body+=f'<p><b>현재 기준본:</b> {esc(latest["path"])} · 본문 기준일 {esc(latest.get("reported_at"))} · {esc(latest.get("revision_no") or "미기재")}차 · {esc(latest.get("document_state") or "상태 미기재")}</p>'
    else:body+='<p><b>최신본 자동 선택 보류</b> · 아래 원문을 대조하여 적용할 값을 확인하세요.</p>'
    body+=f'<details><summary>최신본 채택·구판 및 초안 제외 근거 ({len(history)}개 자료)</summary><p>{esc(t.get("chronology_note",""))}</p><div class="table-wrap"><table><thead><tr><th>파일 / 관리번호</th><th>본문 기준일 / 수정일시</th><th>차수 / 상태</th><th>판정 / 근거</th></tr></thead><tbody>'
    labels={'selected':'현재 기준본','superseded':'이전·중복 기록','excluded':'현재 기준에서 제외','ambiguous':'확인 필요'}
    for e in history:
        refs=' '.join(f'<a href="#source-{n}">[{n}]</a>' for n in e['refs'])
        body+=f'<tr><td>{esc(e["path"])}<br>{esc(e.get("report_id") or "미기재")}</td><td>{esc(e.get("reported_at") or "미기재")}<br>{esc(e.get("issued_at") or "미기재")}</td><td>{esc(e.get("revision_no") or "미기재")}차 / {esc(e.get("document_state") or "미기재")}</td><td>{labels.get(e.get("selection_status"),"기록")}<br>{esc(e.get("selection_reason") or "")} {refs}</td></tr>'
    return body+'</tbody></table></div></details></div>'


def timeline(t):
    events=t.get('timeline',[])
    if not events:return version_history(t)+'<p class="report-chart-note">이 판본에는 문서별 보고일 이력이 없습니다. 기존 값은 그대로 보존합니다.</p>'
    dated=all(e.get('reported_at') for e in events) and (bool(t.get('latest_report')) or len({e['reported_at'] for e in events})==len(events))
    body=version_history(t)+'<div class="report-timeline"><h4>보고 흐름 · '+('시간순 연결' if dated else '보고일 확인 필요')+'</h4>'
    points=[(i,e['progress']) for i,e in enumerate(events) if e.get('progress') is not None]
    if dated and points:
        n=max(1,len(events)-1);xy=[(50+i*500/n,86-p*.65) for i,p in points]
        desc=' → '.join(f'{e["reported_at"]} {e["progress"]}%' for e in events if e.get('progress') is not None)
        body+=f'<svg class="trend-svg" viewBox="0 0 610 115" role="img" aria-label="{esc(desc)}"><title>{esc(desc)}</title><line x1="45" y1="86" x2="560" y2="86" stroke="#d5ddd0"/><text x="12" y="90" font-size="11" fill="#687561">0</text><text x="5" y="24" font-size="11" fill="#687561">100</text>'
        if len(xy)>1:body+='<polyline points="'+' '.join(f'{x},{y}' for x,y in xy)+'" fill="none" stroke="#3e7458" stroke-width="3"/>'
        for (i,p),(x,y) in zip(points,xy):body+=f'<circle cx="{x}" cy="{y}" r="4" fill="#3e7458"/><text x="{x}" y="{max(12,y-9)}" text-anchor="middle" font-size="12" fill="#274d3b">{p}%</text><text x="{x}" y="107" text-anchor="middle" font-size="11" fill="#64725f">{esc(events[i].get("reported_at") or "미상")}</text>'
        body+='</svg>'
    body+='<div class="flow-nodes">'
    for e in events:
        v=e['values'];refs=' '.join(f'[{x}]' for x in e['refs'])
        body+=f'<article class="flow-node"><b>{esc(e.get("stage") or "단계 미기재")}보고</b><small>{esc(e.get("reported_at") or "보고일 미기재")} / {esc(str(e.get('revision_no'))+'차' if e.get('revision_no') is not None else '차수 미기재')} · {e["progress"] if e.get("progress") is not None else "미기재"}{"%" if e.get("progress") is not None else ""}</small><p>{esc(v["status"] or "진행 상태 미기재")}</p><p>실적: {esc(v["completed_work"] or "미기재")}</p><p>당시 현안: {esc(v["issues"] or "미기재")}</p><small>{esc(e["path"])} {refs}</small></article>'
    body+='</div></div>'
    v=t['values'];body+=f'<div class="latest-summary"><h4>현재 인계 요약 · 최신 보고 기준</h4><p><b>지금:</b> {esc(v["status"] or "미확인")}</p><p><b>남은 일:</b> {esc(v["remaining_work"] or "미기재")}</p><p><b>다음 조치:</b> {esc(v["next_action"] or "미기재")} / {esc(v["owner"] or "미확인")} / {esc(v["due_date"] or "미확인")}</p></div>'
    for m in t.get('match_history',[]):body+=f'<p class="match-note">담당자 확인·매칭: {esc(m["source_title"])} → {esc(m["target_title"])} · 확인 담당 {esc(m["owner"])} · 사유 {esc(m["reason"])} · {esc(m["created"])}</p>'
    return body


def gantt(r):
    """Plan dates + source progress + as-of delay, never elapsed-time-derived attainment."""
    def day(v):
        try:return date.fromisoformat(v or '')
        except (ValueError,TypeError):return None
    basis=day(r['basis']);rows=[];dates=[basis]
    for t in r['tasks']:
        last=t['timeline'][-1] if t['timeline'] else {}
        sc=t.get('schedule',{});start=day(sc.get('start_date'));end=day(sc.get('due_date'));actual=day(sc.get('completed_at'))
        if start and end and start<=end:dates.extend([start,end]);valid=True
        else:valid=False
        if actual:dates.append(actual)
        rows.append((t,start,end,actual,valid))
    lo=min(dates)-timedelta(days=2);hi=max(dates)+timedelta(days=3);span=max(1,(hi-lo).days)
    x=lambda d:220+570*(d-lo).days/span
    h=75+len(rows)*65;parts=[f'<div class="gantt-wrap"><svg class="gantt-svg" viewBox="0 0 1000 {h}" role="img" aria-label="업무별 계획 일정·달성률·지연 간트 차트"><title>계획 기간·원문 달성률·기준일 대비 기한 지연</title><desc>회색은 계획 기간, 색 막대는 보고 달성률, 붉은 연장선은 기한 이후 경과, 세로선은 확정 기준일입니다. 날짜가 없는 업무는 막대를 추정하지 않습니다.</desc><defs><pattern id="delay-hatch" patternUnits="userSpaceOnUse" width="6" height="6"><path d="M0,6 L6,0" stroke="#bf4a3d" stroke-width="2"/></pattern></defs>']
    parts+=['<text x="12" y="20" font-size="13" font-weight="700" fill="#234737">업무 / 보고 단계</text><text x="815" y="20" font-size="13" font-weight="700" fill="#234737">달성률 · 일정 상태</text>']
    for i in range(7):
        d=lo+timedelta(days=round(span*i/6));pos=x(d)
        parts.append(f'<line x1="{pos}" y1="35" x2="{pos}" y2="{h-12}" stroke="#e0e6dd"/><text x="{pos}" y="28" text-anchor="middle" font-size="11" fill="#65745e">{d.strftime("%m/%d")}</text>')
    for i,(t,start,end,actual,valid) in enumerate(rows):
        y=52+i*65;v=t['values'];label=v['title'];color=COLORS[t['urgency']['key']];progress=t['progress'];last=t['timeline'][-1] if t['timeline'] else {}
        parts.append(f'<rect x="0" y="{y-10}" width="998" height="64" fill-opacity=".55" fill="{("#ffffff" if i%2==0 else "#f3f6ef")}"/>')
        chunks=[label[:14],label[14:28]] if len(label)>14 else [label]
        for j,chunk in enumerate(chunks):parts.append(f'<text x="12" y="{y+7+j*15}" font-size="12" font-weight="700" fill="#244334">{esc(chunk)}</text>')
        parts.append(f'<text x="12" y="{y+43}" font-size="10" fill="#687660">{esc(last.get("stage") or "단계 미기재")}보고 · {esc(last.get("reported_at") or "보고일 미기재")}</text>')
        if valid:
            left=x(start);width=max(2,x(end)-left)
            parts.append(f'<rect x="{left}" y="{y+2}" width="{width}" height="19" rx="4" fill="#dce5d8"/>')
            if progress is not None:parts.append(f'<rect x="{left}" y="{y+2}" width="{width*progress/100}" height="19" rx="4" fill="{color}"/>')
            if not t['complete'] and end<basis:
                parts.append(f'<rect x="{x(end)}" y="{y+2}" width="{x(basis)-x(end)}" height="19" fill="url(#delay-hatch)" stroke="#bf4a3d"/>')
            parts.append(f'<text x="{left}" y="{y+37}" font-size="10" fill="#61745e">{start.strftime("%m/%d")} → {end.strftime("%m/%d")}</text>')
            if actual and t['complete']:
                pos=x(actual);parts.append(f'<path d="M{pos},{y-3} l5,5 -5,5 -5,-5 Z" fill="#245d45"/>')
        else:parts.append(f'<text x="230" y="{y+18}" font-size="11" fill="#74806b">계획 시작일·기한 미기재 — 일정 막대 추정 안 함</text>')
        status='완료' if t['complete'] else f'지연 {(basis-end).days}일' if end and end<basis else f'D-{(end-basis).days}' if end and end>basis else '오늘 기한' if end else '일정 확인 필요'
        if t['complete'] and actual and end and actual>end:status+=f' · {(actual-end).days}일 지연'
        parts.append(f'<text x="815" y="{y+15}" font-size="16" font-weight="700" fill="{color}">{str(progress)+"%" if progress is not None else "미기재"} · {status}</text><text x="815" y="{y+35}" font-size="10" fill="#687660">{esc(v["owner"] or "담당 미확인")}</text>')
    nowx=x(basis);parts.append(f'<line x1="{nowx}" y1="33" x2="{nowx}" y2="{h-10}" stroke="#283f35" stroke-width="1.5" stroke-dasharray="4 3"/><text x="{nowx}" y="{h-1}" text-anchor="middle" font-size="10" fill="#283f35">기준일 {basis.strftime("%m/%d")}</text></svg></div>')
    parts.append('<div class="gantt-legend"><span><i style="background:#dce5d8"></i>계획 기간</span><span><i style="background:#507387"></i>원문 보고 달성률</span><span><i style="background:#bf4a3d"></i>미완료 업무의 기한 경과</span><span>◆ 원문 실제 완료일</span></div><p class="report-chart-note">달성률은 기간 경과율이 아닙니다. 지연은 확정 기준일에 기한이 지났고 최신 보고상 미완료인 업무의 경과 일수이며 실제 이행 여부는 담당자가 확인합니다.</p>')
    return ''.join(parts)


def gantt_png(r):
    """DOCX uses a portable bitmap; numbered rows map to the adjacent editable Korean table."""
    import io
    from PIL import Image, ImageDraw, ImageFont
    def day(v):
        try:return date.fromisoformat(v or '')
        except (ValueError,TypeError):return None
    basis=day(r['basis']);dates=[basis];rows=[]
    for t in r['tasks']:
        latest=t.get('schedule',{});start=day(latest.get('start_date'));end=day(latest.get('due_date'));actual=day(latest.get('completed_at'))
        valid=bool(start and end and start<=end)
        if valid:dates.extend([start,end])
        if actual:dates.append(actual)
        rows.append((t,start,end,actual,valid))
    lo=min(dates)-timedelta(days=2);hi=max(dates)+timedelta(days=3);span=(hi-lo).days
    x=lambda d:150+740*(d-lo).days/span
    im=Image.new('RGB',(1200,100+len(rows)*85),'#f7f9f4');d=ImageDraw.Draw(im);font=ImageFont.load_default(size=20);small=ImageFont.load_default(size=16)
    d.text((15,10),'WORK',font=font,fill='#244334');d.text((930,10),'PROGRESS / STATUS',font=small,fill='#244334')
    for i in range(7):
        dt=lo+timedelta(days=round(span*i/6));pos=x(dt);d.line((pos,45,pos,im.height-25),fill='#dce5d8');d.text((pos-23,25),dt.strftime('%m/%d'),font=small,fill='#64725f')
    for i,(t,start,end,actual,valid) in enumerate(rows):
        y=68+i*85;color=COLORS[t['urgency']['key']];p=t['progress'];d.text((25,y),f'{t["number"]:02d}',font=font,fill='#244334')
        if valid:
            left=x(start);right=max(left+2,x(end));d.rectangle((left,y,right,y+23),fill='#dce5d8')
            if p is not None and p>0:d.rectangle((left,y,left+(right-left)*p/100,y+23),fill=color)
            if not t['complete'] and end<basis:
                d.rectangle((right,y,x(basis),y+23),fill='#f3b7ad',outline='#b34438',width=2)
            if actual and t['complete']:
                pos=x(actual);d.polygon([(pos,y-7),(pos+6,y-1),(pos,y+5),(pos-6,y-1)],fill='#245d45')
            d.text((left,y+30),start.isoformat()+' - '+end.isoformat(),font=small,fill='#64725f')
        else:d.text((160,y),'Schedule not specified',font=small,fill='#64725f')
        status='DONE' if t['complete'] else f'LATE {(basis-end).days}d' if end and end<basis else f'D-{(end-basis).days}' if end else 'UNKNOWN'
        if t['complete'] and actual and end and actual>end:status+=f' +{(actual-end).days}d'
        d.text((930,y),(str(p)+'%' if p is not None else 'N/A')+' / '+status,font=font,fill=color)
    pos=x(basis);d.line((pos,45,pos,im.height-25),fill='#244334',width=2);d.text((pos-50,im.height-23),'AS OF '+basis.strftime('%m/%d'),font=small,fill='#244334')
    b=io.BytesIO();im.save(b,format='PNG');b.seek(0);return b
