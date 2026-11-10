"""A deterministic report from the exact confirmed revision; no new model claims."""
import html
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .engine import FIELDS
from .timeline import urgency, reported_progress, has_business_issue
from . import report_charts, practice_report, inheritance, report_interactions
from .versions import ordered


def build_report(info, revision, source_lookup):
    payload = revision["payload"]
    # Use confirmation date, not wall-clock time: both parties see the same priorities.
    confirmed_at = revision["confirmation"]["created"]
    basis = datetime.fromisoformat(confirmed_at.replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Seoul")).date()
    tasks, sources, source_ids, changes = [], [], {}, []

    def references(field):
        refs = []
        for ref in field.get("evidence", []):
            key = (ref["block_id"], ref["quote"])
            if key not in source_ids:
                source = source_lookup(ref["block_id"])
                number = len(sources) + 1
                source_ids[key] = number
                sources.append({"number": number, "path": source["path"], "location": source["location"], "quote": ref["quote"], "block_id": ref["block_id"]})
            refs.append(source_ids[key])
        return refs

    for index, item in enumerate(payload["items"], 1):
        fields = item["fields"]
        values = {key: fields.get(key, {}).get("value", "").strip() for key in FIELDS}
        provenance = {}
        for key, field in fields.items():
            provenance[key] = {"refs": references(field), "human": field.get("provenance") == "HUMAN_ENTERED", "review": field.get("review_status")}
            previous = field
            while previous.get("previous"):
                old = previous["previous"]
                changes.append({"task": values["title"], "field": FIELDS.get(key, key), "before": old["value"], "after": previous["value"], "reason": previous.get("reason", ""), "refs": references(old)})
                previous = old
        reasons, checks = [], []
        complete = item.get("business_status") == "COMPLETED"
        due = fields.get("due_date", {})
        conflict = [FIELDS[k] for k, f in fields.items() if f.get("review_status") == "CONFLICT"]
        if conflict:
            # Document discrepancies belong to review/reference, not business urgency.
            checks.append("서로 다른 " + "·".join(conflict) + " 중 적용할 값을 전임자와 대조·확정")
        if not complete and has_business_issue(values["issues"]):
            reasons.append("자료에 현안·장애 사항 기록")
        if not complete and due.get("normalized_date") and due.get("review_status") != "CONFLICT":
            delta = (date.fromisoformat(due["normalized_date"]) - basis).days
            if delta < 0:
                reasons.append("기준일 이전 기한 · 이행 여부 확인 필요")
                checks.append("기한 경과 여부와 실제 이행·연장 상태 확인")
            elif delta <= 7:
                reasons.append("기준일로부터 7일 이내 기한")
        for key in ("status", "owner", "due_date", "next_action"):
            field = fields.get(key, {})
            if not values[key] or (key in {"owner", "due_date"} and field.get("review_status") == "NEEDS_CONFIRMATION"):
                checks.append(FIELDS[key] + " 확인 후 보고서 보완")
        if not values["completed_work"]:
            checks.append("완료한 활동·산출물의 실적 확인")
        if not values["remaining_work"] and not complete:
            checks.append("남은 업무 범위 확인")
        if not values["issues"]:
            checks.append("미결 현안·장애 유무 확인 (미기재는 현안 없음이 아님)")
        flow=[]
        for event in ordered(item.get("timeline",[])):
            refs=[]
            for field in event["fields"].values():refs.extend(references(field))
            refs.extend(references({"evidence":event.get("metadata_evidence",[])}))
            flow.append({k:event.get(k) for k in ["document_id","path","reported_at","stage","progress","work_code","start_date","completed_at","report_id","revision_no","issued_at","document_state","selection_status","selection_reason"]}|{"values":{k:event["fields"].get(k,{}).get("value","") for k in FIELDS},"refs":sorted(set(refs))})
        latest=next((e for e in flow if e['document_id']==item.get('latest_document_id')), {})
        schedule={'start_date':latest.get('start_date'),'completed_at':latest.get('completed_at'),'due_date':due.get('normalized_date') if due.get('review_status')!='CONFLICT' else None}
        tasks.append({"inheritance_status":item.get("inheritance_status",""), "image_reviews": item.get("image_reviews",[]), "number": index, "values": values, "provenance": provenance, "checks": checks,
                      "priority": "우선 확인·처리" if reasons else "종료 확인" if complete else "후속 실행·보완",
                      "reasons": reasons, "complete": complete, "merge_note": item.get("merge_note", ""), "timeline": [e for e in flow if e.get("selection_status")!="excluded"], "version_history":flow, "latest_report":latest, "chronology_note":item.get("chronology_note",""), "schedule":schedule, "progress": reported_progress(item), "urgency": urgency(item,basis), "match_history": item.get("match_history",[])})
    return {"title": info["title"], "predecessor": info["predecessor"], "successor": info["successor"],
            "revision_id": revision["id"], "hash": revision["hash"], "confirmed_at": confirmed_at,
            "basis": basis.isoformat(), "generated_at": payload["generated_at"], "model": payload["model"],
            "inheritance":payload.get("inheritance"), "handover_chain":payload.get("handover_chain",[]), "tasks": tasks, "sources": sources, "changes": changes, "warnings": revision["warnings"],
            "coverage": payload.get("coverage", []), "completed": sum(t["complete"] for t in tasks)}


def esc(value):
    return html.escape(str(value), quote=True)


def render_html(report):
    return report_interactions.decorate(_render_html(report))

def _render_html(report):
    if practice_report.enabled(report):return practice_report.render_html(report)
    r = report
    priority = [t for t in r["tasks"] if t["reasons"]]

    def value(task, key, fallback="자료에 미기재 — 전임자 확인 필요"):
        p = task["provenance"].get(key, {})
        refs = report_interactions.citation(p.get("refs", []))
        mark = "전임자 입력" if p.get("human") else "원문 기록" if p.get("refs") else "미기재"
        return f'<div class="fact"><p>{esc(task["values"][key] or fallback)}</p><small>{mark} {refs}</small></div>'

    def action_rows(tasks):
        return "".join(f'<tr><td><a href="#task-{t["number"]}">{esc(t["values"]["title"])}</a><small>{esc(t["priority"])}</small></td><td>{esc(t["values"]["status"] or "미확인")}</td><td>{esc(t["values"]["next_action"] or "다음 조치를 전임자와 정할 것")}</td><td>{esc(t["values"]["owner"] or "미확인")}<br>{esc(t["values"]["due_date"] or "미확인")}</td></tr>' for t in tasks)

    content = f'''<header><div class="eyebrow">업무바통 · 확정 보고서</div><h1>업무 인수인계 보고서</h1><h2>{esc(r['title'])}</h2><p>인계자 {esc(r['predecessor'])} → 인수자 {esc(r['successor'])}</p><p>확정 시각 {esc(r['confirmed_at'])} · 현안 판단 기준일 {r['basis']} (한국 시간)</p><small>양측이 동일한 확정 판본을 열람합니다. 보고서의 완료 실적은 자료에 있는 기록만 표시합니다.</small></header>
    {inheritance.banner(r)}
    {report_charts.dashboard(r)}
    <nav><a href="#progress-overview">진행 현황판</a><a href="#overview">전체 요약</a><a href="#urgent">우선 현안</a><a href="#work">업무별 상세</a><a href="#plan">실행 계획</a><a href="#appendix">근거 부록</a></nav>
    <section id="overview"><h2>1. 전체 업무 요약</h2><div class="metrics"><div><strong>{len(r['tasks'])}</strong>인계 업무</div><div><strong>{r['completed']}</strong>전체 완료로 명시된 업무</div><div><strong>{len(r['tasks'])-r['completed']}</strong>진행·미확인 업무</div><div><strong>{len(priority)}</strong>우선 확인·처리 업무</div></div><p>이번 인계 범위는 {len(r['tasks'])}개 업무입니다. 업무별 현재 단계와 다음 조치를 아래에서 확인하고, 기한 경과·임박 업무와 진행을 막는 현안을 우선 확인하세요. 일부 활동의 완료는 전체 업무 완료로 계산하지 않습니다.</p>
    <div class="table-wrap"><table><thead><tr><th>업무 / 인계 구분</th><th>현재 어디까지 진행되었나</th><th>다음에 할 일</th><th>담당 / 기한</th></tr></thead><tbody>{action_rows(r['tasks'])}</tbody></table></div></section>
    <section id="urgent"><h2>2. 당장 확인·처리할 현안</h2><p>기한은 확정 기준일로 판정합니다. 기한 경과·기한 임박·기록된 업무 장애에 따라 확인 순서를 제안하며, 실제 긴급도와 지연 여부는 담당자가 확인해야 합니다.</p>'''
    if not priority:
        content += '<p class="notice">명시된 우선 분류 근거가 없습니다. 현안이 없다는 뜻은 아니며 업무별 미기재 항목을 확인하세요.</p>'
    for t in priority:
        content += f'<article class="issue"><h3><a href="#task-{t["number"]}">{esc(t["values"]["title"])}</a></h3><p><b>분류 근거:</b> {esc(" / ".join(t["reasons"]))}</p><p><b>기록된 현안:</b> {esc(t["values"]["issues"] or "별도 현안 기록 없음 — 기한·담당 대조 필요")}</p><p><b>다음 실행:</b> {esc(t["values"]["next_action"] or "실행 조치 미기재")}</p><p><b>확인 권고:</b> {esc(" / ".join(t["checks"]) or "기록된 현안의 해소 여부를 담당자와 확인")}</p></article>'
    content += '</section><section id="work"><h2>3. 업무별 인수인계 상세</h2>'
    sections = [("status", "현재 어디까지 진행되었나"), ("completed_work", "지금까지 완료한 일·산출물"), ("remaining_work", "앞으로 남은 업무"), ("next_action", "다음에 실행할 구체적 조치"), ("issues", "미결 현안·장애·결정 필요 사항"), ("owner", "담당"), ("collaborators", "협의·협업 부서"), ("contacts", "연락처"), ("due_date", "기한·반복 일정"), ("notes", "업무 맥락·유의 사항")]
    for t in r["tasks"]:
        content += f'<article class="task" id="task-{t["number"]}"><div class="eyebrow">업무 {t["number"]:02d} · {esc(t["priority"])}</div><h3>{esc(t["values"]["title"])}</h3>{report_charts.timeline(t)}<div class="task-grid">'
        for key, label in sections:
            content += f'<div class="task-field"><h4>{label}</h4>{value(t,key)}</div>'
        content += '</div><div class="checks"><h4>인수자가 먼저 확인할 사항 · 시스템 권고</h4><ul>' + ''.join(f'<li>{esc(c)}</li>' for c in t['checks']) + '</ul></div>'
        if t["merge_note"]:
            content += f'<small>{esc(t["merge_note"])}</small>'
        content += '</article>'
    content += f'</section><section id="plan"><h2>4. 후속 실행 계획·일정</h2><p>아래 조치는 확정 판본의 다음 행동입니다. 미확인 담당·일정은 확정된 약속이 아닙니다. 구체적 조치가 빠진 업무는 전임자가 보완해야 합니다.</p><div class="table-wrap"><table><thead><tr><th>업무 / 인계 구분</th><th>현재 단계</th><th>실행 조치</th><th>담당 / 일정</th></tr></thead><tbody>{action_rows(sorted(r["tasks"], key=lambda t: not bool(t["reasons"])))}</tbody></table></div></section>'
    content += '<section class="report-detail-reference"><details><summary>5. 참고 · 자료 검토 및 미확인 사항</summary><ul>' + ''.join(f'<li>{esc(w)}</li>' for w in r['warnings']) + '</ul><p>문서 확정과 모든 사실의 검증 완료는 다릅니다. 직접 입력한 내용은 전임자 진술이며 원문 인용과 구분됩니다.</p></details></section>'
    for t in r['tasks']:
        for v in t.get('image_reviews',[]):
            content += '<section><h2>최신본 그림 판독 참고 · 원본 대조 필요</h2><h3>'+esc(t['values']['title'])+'</h3><p>'+esc(v['path']+' / '+v['location'])+'</p><blockquote>'+esc(v['text'])+'</blockquote></section>'
    content += '<section id="appendix"><h2>부록. 원문 근거·변경 이력</h2><p class="report-detail-reference">항목별 원문 기록 확인 버튼에서 인용과 자료 위치를 볼 수 있습니다.</p><details class="source-records"><summary>원문 기록</summary>'
    for s in r['sources']:
        content += f'<div class="source" id="source-{s["number"]}"><b>[{s["number"]}] {esc(s["path"])}</b><p>{esc(s["location"])}</p><blockquote>{esc(s["quote"])}</blockquote><small>원문 블록 {esc(s["block_id"])}</small></div>'
    content += '</details><details><summary>전임자 수정 이력 펼치기</summary>'
    for c in r['changes']:
        content += f'<p><b>{esc(c["task"])} / {esc(c["field"])}</b><br>수정 전: {esc(c["before"])} → 수정 후: {esc(c["after"])}<br>사유: {esc(c["reason"])}</p>'
    content += f'</details><p class="meta">판본 {esc(r["revision_id"])}<br>내용 해시 {esc(r["hash"])}<br>자료 분석 시각 {esc(r["generated_at"])} · 모델 {esc(r["model"])}</p></section>'
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>업무 인수인계 보고서</title><style>
    *{box-sizing:border-box}body{font:15px/1.8 system-ui,sans-serif;color:#203f37;max-width:1120px;margin:auto;padding:36px 28px;background:#fff;overflow-wrap:anywhere}h1{font-size:34px;margin:8px 0}h2{font-size:23px}h3{font-size:21px}h4{font-size:14px;margin:0;color:#536c63}header{border-bottom:4px solid #205649;padding-bottom:28px}header h2{font-weight:500}.eyebrow,small{font-size:12px;color:#64786f}small{display:block}nav{display:flex;gap:22px;flex-wrap:wrap;padding:22px 0}a{color:#256551}section{margin:32px 0 46px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metrics div{background:#edf4ee;border-radius:10px;padding:18px}.metrics strong{display:block;font-size:30px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid #dde5df;padding:14px;text-align:left;vertical-align:top}th{background:#edf4ee}td{min-width:135px}.task{border:1px solid #d9e5dd;border-radius:12px;padding:24px;margin:22px 0}.task-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.task-field{border-top:1px solid #e5ebe6;padding-top:14px}.fact p{margin:8px 0;white-space:pre-wrap}.issue,.notice{background:#fff7e8;border-left:4px solid #b78d43;padding:18px 24px;margin:16px 0}.issue h3{margin:0}.checks{background:#f5f7f2;padding:16px;margin-top:20px}.checks ul{margin-bottom:0}.source{border-bottom:1px solid #dde5df;padding:16px 0}blockquote{white-space:pre-wrap;border-left:3px solid #b9cbb8;padding-left:14px;margin-left:0}details{padding:16px;background:#f5f7f2;margin:12px 0}summary{cursor:pointer}.meta{font-size:11px;color:#63766b}@media(max-width:600px){body{padding:20px 14px}h1{font-size:27px}.metrics{grid-template-columns:1fr 1fr}.task-grid{grid-template-columns:1fr}.task{padding:16px}}@media print{body{padding:0;font-size:11px;max-width:none}nav{display:none}section{margin:20px 0}h2,h3,h4{break-after:avoid}tr,.task-field{break-inside:avoid}details::details-content{content-visibility:visible}details[open]>*{display:block!important}details:not([open])>:not(summary){display:none!important}.table-wrap{overflow:visible}th,td{min-width:0;padding:8px}.metrics strong{font-size:22px}a{color:inherit;text-decoration:none}}
    ''' + report_charts.CSS + '''</style></head><body>''' + content + '</body></html>'


def render_markdown(r):
    def text(v):
        return esc(v).replace('\n', ' · ').replace('|', '&#124;')
    lines = ['# 업무 인수인계 보고서', '', '## ' + text(r['title']), '', f"- 인계자: {text(r['predecessor'])} / 인수자: {text(r['successor'])}", f"- 확정 시각: {r['confirmed_at']}", f"- 현안 판단 기준일: {r['basis']}", f"- 판본: {r['revision_id']}", f"- 내용 해시: {r['hash']}", '', '## 1. 전체 업무 요약', '', f"전체 {len(r['tasks'])}개 · 전체 완료로 명시 {r['completed']}개 · 진행·미확인 {len(r['tasks'])-r['completed']}개", '', '## 2. 당장 확인·처리할 현안', '', '분류는 확정일 기준 시스템 권고입니다. 실제 긴급도·지연 여부는 담당자 확인이 필요합니다.', '']
    overview=['## 일정·달성률 현황', '', '| 업무 | 계획 기간 | 원문 달성률 | 일정 상태 | 현안 | 다음 조치 |', '|---|---|---|---|---|---|']
    for t in r['tasks']:
        v=t['values'];sc=t['schedule'];overview.append('| '+' | '.join(text(x) for x in [v['title'],(sc['start_date'] or '미기재')+' → '+(sc['due_date'] or '미확인'),str(t['progress'])+'%' if t['progress'] is not None else '미기재',t['urgency']['label'],v['issues'],v['next_action']])+' |')
    overview+=['','간트 차트는 같은 판본의 HTML·PDF·DOCX에서 볼 수 있습니다. 달성률은 경과 시간으로 추정하지 않습니다.','']
    lines[lines.index('## 1. 전체 업무 요약'):lines.index('## 1. 전체 업무 요약')]=overview
    if r.get('inheritance'):lines[9:9]=['## 이전 인계 보고서 기반 · 인수인계 이력','',*['- '+text(line) for line in inheritance.chain_lines(r)],'']
    priority = [t for t in r['tasks'] if t['reasons']]
    for t in priority:
        lines += [f"- {text(t['values']['title'])}: {text(' / '.join(t['reasons']))}", f"  - 현안: {text(t['values']['issues']) or '별도 기록 없음'}", f"  - 다음 실행: {text(t['values']['next_action']) or '미기재'}"]
    if not priority:
        lines += ['명시된 우선 분류 근거 없음. 현안이 없다는 의미는 아닙니다.']
    lines += ['', '## 3. 업무별 인수인계 상세', '']
    for t in r['tasks']:
        if t.get('inheritance_status'):lines+=['',text(t['inheritance_status'])+' · 이전 내용 유지 항목은 최신 현황 재확인','']
        lines += ['### ' + text(t['values']['title']), '', '| 보고일 | 단계 | 달성률 | 당시 상태 | 남은 일 |', '|---|---|---|---|---|']
        for e in t['timeline']:
            lines.append('| '+' | '.join(text(x) for x in [e['reported_at'] or '미기재',e['stage'] or '미기재',str(e['progress'])+'%' if e['progress'] is not None else '미기재',e['values']['status'],e['values']['remaining_work']])+' |')
        lines.append('')
        if any(e.get('report_id') for e in t.get('version_history',[])):
            lines += ['','#### 본문 판본 선택 근거','',text(t.get('chronology_note','')),'','| 파일 | 본문 기준일 | 수정차수 / 수정일시 | 상태 / 판정 |','|---|---|---|---|']
            for e in t['version_history']:
                lines.append('| '+' | '.join(text(x) for x in [e['path'],e.get('reported_at') or '미기재',str(e.get('revision_no') or '미기재')+'차 / '+(e.get('issued_at') or '미기재'),(e.get('document_state') or '미기재')+' / '+{'selected':'현재 기준본','superseded':'이전·중복 기록','excluded':'현재 기준에서 제외','ambiguous':'확인 필요'}.get(e.get('selection_status'),'기록')])+' |')
            lines.append('')
        for key, label in FIELDS.items():
            if key in {'title','scope'}:
                continue
            p = t['provenance'].get(key, {})
            mark = '전임자 입력' if p.get('human') else '원문 기록' if p.get('refs') else '미기재'
            refs = ' '.join(f'[{n}]' for n in p.get('refs', []))
            lines += [f"- {label}: {text(t['values'][key]) or '자료에 미기재 — 전임자 확인 필요'} ({mark}) {refs}"]
        lines += ['- 인수자 확인 권고:'] + ['  - ' + text(c) for c in t['checks']] + ['']
    lines += ['## 4. 후속 실행 계획·일정', '', '| 업무 | 다음 조치 | 담당 | 일정 |', '|---|---|---|---|']
    for t in r['tasks']:
        v = t['values']
        lines += ['| ' + ' | '.join(text(v[k]) or '미확인' for k in ('title', 'next_action', 'owner', 'due_date')) + ' |']
    if practice_report.enabled(r):
        lines += practice_report.markdown_resources(r)
    lines += ['', '## 5. 인계 시 남은 확인 사항', ''] + ['- ' + text(w) for w in r['warnings']]
    lines += ['', '## 부록. 원문 근거·변경 이력', '']
    for s in r['sources']:
        lines += [f"- [{s['number']}] {text(s['path'])} / {text(s['location'])}", '  - 인용: ' + text(s['quote']), '  - 원문 블록: ' + s['block_id']]
    for c in r['changes']:
        lines += [f"- {text(c['task'])} / {text(c['field'])}: 수정 전 {text(c['before'])} → 수정 후 {text(c['after'])}; 사유: {text(c['reason'])}"]
    for t in r['tasks']:
        for v in t.get('image_reviews',[]):
            lines += ['', '## 최신본 그림 판독 참고 · 원본 대조 필요', '', text(t['values']['title'])+' / '+text(v['path']), text(v['location']), text(v['text']), '그림 SHA-256: '+v['image_sha'], '근거 블록: '+v['block_id']]
    return '\n'.join(lines) + '\n'


def render_docx(report):
    """Editable office report built from the same confirmed facts as HTML/Markdown."""
    if practice_report.enabled(report):return practice_report.render_docx(report)
    import io
    from docx import Document
    from docx.shared import Pt, Inches
    from docx.oxml.ns import qn
    doc = Document()
    style = doc.styles['Normal']; style.font.name = '맑은 고딕'; style.font.size = Pt(10)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '맑은 고딕')
    r = report
    doc.add_heading('업무 인수인계 보고서', 0)
    doc.add_heading(r['title'], 1)
    if r.get('inheritance'):
        doc.add_heading('이전 인계 보고서 기반 · 인수인계 이력',2)
        for line in inheritance.chain_lines(r):doc.add_paragraph(line)
    doc.add_paragraph(f"인계자 {r['predecessor']} → 인수자 {r['successor']}")
    doc.add_paragraph(f"확정 시각 {r['confirmed_at']} / 현안 기준일 {r['basis']} (한국 시간)")
    doc.add_paragraph('동일 확정 판본에서 출력한 편집용 사본입니다. 이 파일을 편집해도 앱의 확정본은 변경되지 않습니다. 기관 인증·전자서명이 아닌 시연용 인수인계입니다.')
    doc.add_heading('일정·달성률 한눈에 보기',1)
    doc.add_picture(report_charts.gantt_png(r),width=Inches(6.2))
    doc.add_paragraph('회색: 계획 기간 / 색 막대: 원문 달성률 / 붉은 연장: 기한 경과 / 세로선: 확정 기준일 / ◆ 실제 완료일. DONE=완료, LATE=지연 일수. 업무 번호는 아래 표와 같습니다.',style='Caption')
    chart_table=doc.add_table(rows=1,cols=4);chart_table.style='Light Shading Accent 1'
    for c,v in zip(chart_table.rows[0].cells,['번호 / 업무','달성률 / 일정','현안','남은 일 / 다음 조치']):c.text=v
    for t in r['tasks']:
        v=t['values']
        for c,value in zip(chart_table.add_row().cells,[f"{t['number']:02d} {v['title']}",(str(t['progress'])+'%' if t['progress'] is not None else '미기재')+' / '+t['urgency']['label'],v['issues'] or '미기재',v['remaining_work']+' / '+v['next_action']]):c.text=value
    doc.add_heading('1. 전체 업무 요약', 1)
    doc.add_paragraph(f"인계 업무 {len(r['tasks'])}건 · 전체 완료로 명시된 업무 {r['completed']}건. 부분 활동의 완료는 전체 업무 완료가 아닙니다.")
    table = doc.add_table(rows=1, cols=4); table.style='Light Shading Accent 1'
    for c,v in zip(table.rows[0].cells,['업무','현재 단계','다음 행동','담당 / 기한']): c.text=v
    for t in r['tasks']:
        v=t['values']
        for c,value in zip(table.add_row().cells,[v['title'],v['status'] or '미확인',v['next_action'] or '미기재',f"{v['owner'] or '미확인'} / {v['due_date'] or '미확인'}"]):c.text=value
    doc.add_heading('2. 당장 확인·처리할 현안',1)
    for t in r['tasks']:
        if t['reasons']:
            doc.add_heading(t['values']['title'],2)
            doc.add_paragraph('분류 근거: '+' / '.join(t['reasons']))
            doc.add_paragraph('현안: '+(t['values']['issues'] or '미기재 — 기한·담당 대조 필요'))
            doc.add_paragraph('다음 행동: '+(t['values']['next_action'] or '미기재'))
    doc.add_heading('3. 업무별 인수인계 상세',1)
    for t in r['tasks']:
        doc.add_heading(f"{t['number']}. {t['values']['title']}",2)
        if any(e.get('report_id') for e in t.get('version_history',[])):
            doc.add_paragraph('본문 판본 선택: '+t.get('chronology_note',''))
            latest=t.get('latest_report',{})
            if latest:doc.add_paragraph('현재 기준본: '+latest['path']+' / '+str(latest.get('reported_at'))+' / '+str(latest.get('revision_no'))+'차')
            table=doc.add_table(rows=1,cols=4);table.style='Light Shading Accent 1'
            for cell,label in zip(table.rows[0].cells,['파일','본문 기준일','차수 / 수정일시','상태 / 판정']):cell.text=label
            for e in t['version_history']:
                values=[e['path'],e.get('reported_at') or '미기재',str(e.get('revision_no') or '미기재')+'차 / '+(e.get('issued_at') or '미기재'),(e.get('document_state') or '미기재')+' / '+{'selected':'현재 기준본','superseded':'이전·중복 기록','excluded':'현재 기준에서 제외','ambiguous':'확인 필요'}.get(e.get('selection_status'),'기록')]
                for cell,value in zip(table.add_row().cells,values):cell.text=value
        if t['timeline']:
            table=doc.add_table(rows=1,cols=4);table.style='Light Shading Accent 1'
            for c,v in zip(table.rows[0].cells,['보고일 / 단계','보고 달성률','당시 실적','당시 남은 일']):c.text=v
            for e in t['timeline']:
                for c,v in zip(table.add_row().cells,[(e['reported_at'] or '미기재')+' / '+(e['stage'] or '미기재'),str(e['progress'])+'%' if e['progress'] is not None else '미기재',e['values']['completed_work'],e['values']['remaining_work']]):c.text=v
        for key,label in FIELDS.items():
            if key in {'title','scope'}:continue
            ref=t['provenance'].get(key,{})
            mark='전임자 입력' if ref.get('human') else '원문 기록' if ref.get('refs') else '미기재'
            refs=' '.join(f'[{n}]' for n in ref.get('refs',[]))
            p=doc.add_paragraph();p.add_run(label+': ').bold=True;p.add_run(t['values'][key] or '자료에 미기재 — 전임자 확인 필요')
            doc.add_paragraph(f'{mark} {refs}',style='Caption')
        for check in t['checks']:doc.add_paragraph('확인 권고: '+check)
    doc.add_heading('4. 후속 실행 계획·일정',1)
    for t in sorted(r['tasks'],key=lambda t:not bool(t['reasons'])):
        v=t['values'];doc.add_paragraph(f"{v['title']} — {v['next_action'] or '다음 조치 확인 필요'} / {v['owner'] or '담당 미확인'} / {v['due_date'] or '기한 미확인'}")
    if practice_report.enabled(r):practice_report.docx_resources(doc,r)
    doc.add_heading('5. 인계 시 남은 확인 사항',1)
    for warning in r['warnings']:doc.add_paragraph(warning)
    doc.add_heading('부록. 원문 근거·변경 이력',1)
    for source in r['sources']:
        doc.add_paragraph(f"[{source['number']}] {source['path']} / {source['location']}")
        doc.add_paragraph(source['quote'])
    for change in r['changes']:
        doc.add_paragraph(f"{change['task']} / {change['field']}: {change['before']} → {change['after']} / 사유: {change['reason']}")
    doc.add_paragraph(f"판본: {r['revision_id']}\n내용 해시: {r['hash']}\n분석 모델: {r['model']}")
    doc.core_properties.title=r['title'];doc.core_properties.author='업무바통'
    stamp=datetime.fromisoformat(r['confirmed_at'].replace('Z','+00:00')).replace(tzinfo=None)
    doc.core_properties.created=stamp;doc.core_properties.modified=stamp
    for t in r['tasks']:
        for v in t.get('image_reviews',[]):
            doc.add_heading('최신본 그림 판독 참고 · 원본 대조 필요',2)
            doc.add_paragraph(v['path']+' / '+v['location']);doc.add_paragraph(v['text'])
    buf=io.BytesIO();doc.save(buf);return buf.getvalue()
