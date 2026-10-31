"""Deterministic checks complement, never fabricate, visual model observations."""
import json
import re
import copy
from pathlib import Path
from .rules import PACK,validate_batch

TERMS=json.loads((Path(__file__).resolve().parents[1]/'rules/official-terms.json').read_text())


def general_text_rules(steps, ids):
    """Do not apply national-name spelling checks to every arbitrary text line."""
    return [rid for rid in ids if re.search('오자|오탈자|비정상 문자|철자',steps[rid]['objective'])
            and not re.search('국가명|국호',steps[rid]['objective'])]


def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1):nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=nxt
    return row[-1]


def protect(run,rows,ids):
    pack=run.get('rule_pack') or PACK;steps={s['rule_id']:s for s in pack['steps']}
    originals=run.get('observation',{}).get('objects',[])
    checks=run.get('verification',{}).get('results',[])
    for obj in originals:
        for term in TERMS['terms']:
            scoped_source=any(r.get('status')=='APPROVED' and r.get('kind')=='source-data' and term['canonical'] in r.get('content','') for r in run['reference_snapshot'])
            if not any(k in obj['label'] for k in term['context']) and not scoped_source:continue
            if term.get('identity_context') and not any(k in obj.get('description','') for k in term['identity_context']):continue
            words=re.findall(r'[가-힣]+',obj.get('text',''));canonical=term['canonical']
            # Near-match is a candidate only, not a global spell-correction rule.
            stems=[]
            for word in words:
                suffix=word[len(canonical):]
                stem=word[:len(canonical)] if suffix in ('은','는','이','가','의','을','를','와','과','에서','으로','로','께서') else word
                if stem!=canonical and len(stem)>=4 and distance(stem,canonical)==1:stems.append(stem)
            candidates=list(dict.fromkeys(stems))
            if term.get('aliases'):candidates=[a for a in term['aliases'] if a in obj.get('text','').upper()]
            for literal in candidates:
                readings=[c for c in checks if c.get('status')=='COMPLETED' and c.get('object_id')==obj['id'] and c.get('text')]
                confirmed=bool(readings) and obj.get('quality')=='CLEAR' and not obj.get('transcription_inferred') and all(c.get('quality')=='CLEAR' and not c.get('transcription_inferred') and re.sub(r'\s','',c['text'])==re.sub(r'\s','',obj['text']) for c in readings)
                status='FAIL' if confirmed else 'REVIEW'
                for rid in ids:
                    if rid not in general_text_rules(steps,ids):continue
                    selected=[r for r in rows if r['rule_id']==rid and obj['id'] in r.get('evidence_ids',[])]
                    if not selected:
                        selected=validate_batch({'results':[dict(rule_id=rid,instance_id=obj['id'],status='REVIEW',observation=obj['label']+': '+obj['text'],reason='기관명 대조',evidence_quality='UNCERTAIN',cell_ids=obj['cell_ids'],reference_ids=[],recommended_action='공식 명칭과 원문을 대조하세요.')]},[rid],run['reference_snapshot'],None,'system/official-term-check',pack=pack)
                        for row in selected:row.update(evidence_ids=[obj['id']],target_presence='PRESENT',vision_model=run.get('observation_model'))
                        rows.extend(selected)
                    for row in selected:
                        row['official_term_check']={'literal':literal,'canonical':canonical,'sources':term['sources'],'independent_reading_agrees':confirmed,'version':TERMS['version']}
                        if row['status']=='ERROR':continue
                        row.update(status='FAIL' if row['status']=='FAIL' else status,error_type='FACT_OR_STYLE_ISSUE',review_basis='OBSERVED_ANOMALY',visual_issue=True,document_review=False,
                            reason=f'원문 명칭 “{literal}”는 공식 명칭 “{canonical}”와 다릅니다. '+('원본 관찰과 독립 재판독이 같은 원문을 확인했습니다.' if confirmed else '독립 재판독은 미확정이며 원본 글자 확인이 필요합니다.'),
                            recommended_action=f'기관을 가리키는 명칭이면 “{canonical}”로 수정하세요.')
    # A territorial-scope concern must remain visible even if the analysis only
    # assesses the map title, or another part of the map is occluded.
    by_id={o['id']:o for o in originals}
    from .verification import direct_comparisons
    for check in checks:
        obj=by_id.get(check.get('object_id'))
        if not obj or check.get('status')!='COMPLETED':continue
        for cmp in check.get('comparisons',[]):
            if cmp.get('aspect')!='TERRITORIAL_SCOPE' or cmp.get('status')!='MISMATCH':continue
            for rid in set(ids).intersection(cmp['rule_ids']):
                if 'official-map' not in steps[rid]['reference_requirements']:continue
                selected=[r for r in rows if r['rule_id']==rid and obj['id'] in r.get('evidence_ids',[])]
                if not selected:
                    selected=validate_batch({'results':[dict(rule_id=rid,instance_id=obj['id'],status='REVIEW',observation=obj['label']+': '+obj['description'],reason=cmp['evidence'],evidence_quality='UNCERTAIN',cell_ids=obj['cell_ids'],reference_ids=[cmp['reference_id']],recommended_action='제목·범례·영역 강조 범위를 함께 수정 검토하세요.')]},[rid],run['reference_snapshot'],None,'system/map-scope-check',pack=pack)
                    for row in selected:row.update(evidence_ids=[obj['id']],target_presence='PRESENT',vision_model=run.get('observation_model'))
                    rows.extend(selected)
                proof=direct_comparisons(run,rid,[obj['id']],[cmp['reference_id']])
                for row in selected:
                    if row['status']=='ERROR':continue
                    row.update(status='FAIL' if row['status']=='FAIL' or proof and all(p['status']=='MISMATCH' for p in proof) else 'REVIEW',reason='지도 강조 범위 대조: '+cmp['evidence'],review_basis='CONTEXT_CONFLICT',error_type='FACT_OR_STYLE_ISSUE',visual_issue=True,document_review=False,
                        map_scope_check={'highlighted_landmasses':check.get('highlighted_landmasses',''),'territorial_context':check.get('territorial_context',''),'coverage':check.get('coverage'),'event_id':check.get('event_id')})
    for check in run.get('symbol_geometry',{}).get('checks',[]):
        if not check['mirrored']:continue
        for row in rows:
            action=steps.get(row['rule_id'],{}).get('objective','')
            if check['object_id'] not in row.get('evidence_ids',[]) or not ('태극' in action and '방향' in action):continue
            row['symbol_geometry']=check
            if row['status'] in ('FAIL','ERROR'):continue
            row.update(status='REVIEW',review_basis='OBSERVED_ANOMALY',error_type='FACT_OR_STYLE_ISSUE',visual_issue=True,document_review=False,
                reason='중앙 태극의 적·청 영역이 공식 정면 도안보다 좌우 반전 도안에 더 가깝습니다. 색상만 맞다는 이유로 정상 판정할 수 없습니다. 깃면 뒷면·회전인지 중앙 문양만 반전인지 확인이 필요합니다.',
                recommended_action='4괘와 깃면 방향을 함께 대조하고 중앙 태극의 좌우 곡선을 확인하세요.',rects=[check['rect']])
    return rows


def protect_glyphs(run, rows, ids):
    """Readable text is not proof of intact glyphs; preserve localized QA evidence."""
    from .imaging import global_rect
    pack=run.get('rule_pack') or PACK
    steps={s['rule_id']:s for s in pack['steps']}
    text_rules=general_text_rules(steps,ids)
    objects={o['id']:o for o in run.get('observation',{}).get('objects',[])}
    for check in run.get('verification',{}).get('results',[]):
        obj=objects.get(check.get('object_id'))
        if not obj or check.get('status')!='COMPLETED' or check.get('coverage')=='MISSING':continue
        issues=[copy.deepcopy(g) for g in check.get('glyph_checks',[]) if g['quality'] in ('DEFECT','UNCERTAIN') and g['evidence'].strip() and g['cell_ids']]
        for glyph in issues:
            # Older records have no origin. A partial transcription with an
            # explicitly clipped glyph still cannot establish source damage.
            legacy_clip=check.get('coverage')=='PARTIAL' and re.search('잘려|잘림|잘린|crop|크롭',glyph['evidence'],re.I)
            if glyph.get('origin') in ('CROP_EDGE','UNRESOLVED') or legacy_clip:
                glyph['quality']='UNCERTAIN'
                glyph['source_defect_unconfirmed']=True
        if not issues or not check.get('crop_rect'):continue
        rects=[global_rect(c,check['crop_rect']) for g in issues for c in g['cell_ids']]
        status='FAIL' if any(g['quality']=='DEFECT' for g in issues) else 'REVIEW'
        reason=' / '.join(f"{g['literal'] or '문자 영역'}: {g['evidence']}" for g in issues)
        for rid in text_rules:
            selected=[r for r in rows if r['rule_id']==rid and obj['id'] in r.get('evidence_ids',[])]
            if not selected:
                selected=validate_batch({'results':[dict(rule_id=rid,instance_id=obj['id'],status='REVIEW',observation=obj['label']+': '+obj.get('text',''),reason=reason,evidence_quality='UNCERTAIN',cell_ids=obj['cell_ids'],reference_ids=[],recommended_action='표시한 음절의 원본 획을 확인하세요.')]},[rid],run['reference_snapshot'],None,'system/glyph-evidence',pack=pack)
                for row in selected:row.update(evidence_ids=[obj['id']],target_presence='PRESENT',vision_model=check.get('model'))
                rows.extend(selected)
            for row in selected:
                row['glyph_evidence']={'checks':issues,'event_id':check.get('event_id'),'model':check.get('model'),'crop_rect':check['crop_rect']}
                if row['status']=='ERROR':continue
                independent_fail=row['status']=='FAIL' and row.get('error_type') not in ('VISUAL_TEXT_DEFECT','OCR_UNCERTAIN','OCR_MISMATCH')
                prior_type=row.get('error_type');prior_quality=row.get('evidence_quality')
                if row['status']=='FAIL' and row.get('error_type')=='VISUAL_TEXT_DEFECT' and all(g.get('source_defect_unconfirmed') for g in issues):
                    row['status']='REVIEW'
                # Keep an independent spelling FAIL's explanation as well as glyph evidence.
                if row['status']=='FAIL' and row.get('reason') and row['reason'] not in reason:
                    row['reason']+=' · 획 품질 추가 관찰: '+reason
                else:row['reason']='문자 획 품질: '+reason
                row.update(status='FAIL' if row['status']=='FAIL' else status,visual_issue=True,document_review=False,
                    evidence_quality=prior_quality if independent_fail and prior_quality else 'CLEAR' if status=='FAIL' else 'UNCERTAIN',review_basis='OBSERVED_ANOMALY',
                    error_type=prior_type if independent_fail and prior_type else 'VISUAL_TEXT_DEFECT' if status=='FAIL' else 'OCR_UNCERTAIN',
                    recommended_action='판독 문구와 별도로 표시한 글자의 끊김·융합·모음 획을 원본에서 확인하고 재조판하세요.' if status=='FAIL' else '전체 원본과 확대 경계를 대조해 실제 손상인지 먼저 확인하세요.')
                if row.get('evidence_ids')==[obj['id']] and not independent_fail:row['rects']=rects
    return rows
