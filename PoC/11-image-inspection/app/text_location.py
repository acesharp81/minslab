"""Ground text findings to independently read detector regions, never fuzzy guesses."""
import copy
import math
import re
from .text_ocr import normalized, valid_rect
from .imaging import global_rect


def cells_for_rects(rects):
    return sorted({f'R{y+1:02}C{x+1:02}' for a,b,c,d in rects
                   for y in range(max(0,int(b*12)),min(12,math.ceil(d*12)))
                   for x in range(max(0,int(a*12)),min(12,math.ceil(c*12)))})


def verified_regions(run):
    """Reuse existing blind crop checks without spending another API call."""
    regions=[]
    for c in run.get('verification',{}).get('results',[]):
        if c.get('status')!='COMPLETED' or c.get('coverage')!='COMPLETE' or c.get('quality')!='CLEAR' or c.get('transcription_inferred',True) or not c.get('text') or not c.get('crop_rect') or not c.get('cell_ids'):continue
        cells=[]
        for cell in c['cell_ids']:
            if not re.fullmatch(r'R0[1-8]C0[1-8]',cell):break
            cells.append((int(cell[1:3]),int(cell[4:6])))
        if len(cells)!=len(c['cell_ids']):continue
        # Do not join disconnected text labels through empty space.
        reached={cells[0]}
        while True:
            expanded=reached|{p for p in cells if any(abs(p[0]-q[0])+abs(p[1]-q[1])<=1 for q in reached)}
            if expanded==reached:break
            reached=expanded
        if len(reached)!=len(set(cells)):continue
        rects=[global_rect(cell,c['crop_rect']) for cell in c['cell_ids']]
        regions.append(dict(id=c['object_id'],source_ids=[c['object_id']],rects=rects,
                            rect=[min(r[0] for r in rects),min(r[1] for r in rects),max(r[2] for r in rects),max(r[3] for r in rects)],
                            method='independent-crop-reading',assessment={'location_verified':True,'transcription_confirmed':True,'literal_text':c['text']}))
    return regions


def protect(run, rows):
    regions=[r for r in run.get('glyph_audit',{}).get('regions',[])
             if r.get('assessment',{}).get('location_verified')]
    # Prefer precise detector bounds when present, otherwise use the existing
    # independent crop reading. No OCR installation is needed for this fallback.
    if not regions:regions=verified_regions(run)
    objects={o['id']:o for o in run.get('observation',{}).get('objects',[])}
    # Exact agreement with a separately detected line grounds its position,
    # not its spelling or visual quality. Never fuzzy-match a correction.
    detector=[]
    if (run.get('pixel_text') or {}).get('status')=='COMPLETED':
        for r in run['pixel_text'].get('detector_regions',[]):
            literal=normalized(r.get('text',''))
            if r.get('source')!='paddle-detector' or r.get('recognition_score',0)<.9 or r.get('detection_score',0)<.55 or len(literal)<2 or not valid_rect(r.get('rect',[])):continue
            linked=[o['id'] for o in objects.values() if not o.get('transcription_inferred') and normalized(o.get('text',''))==literal]
            if not linked:continue
            detector.append(dict(id=linked[0] if len(linked)==1 else 'PXLOC-'+r['id'],source_ids=linked,rect=r['rect'],method='independent-detector-and-scene',
                                 assessment={'location_verified':True,'transcription_confirmed':True,'literal_text':r['text']}))
    regions=detector+regions
    if not regions:return rows
    by_id={r['id']:r for r in regions}
    for row in rows:
        if row['rule_id'] not in ('D-02-l','H-06-b') or row.get('crop_id') or row.get('document_review'):continue
        ids=row.get('evidence_ids',[])
        direct=[by_id[e] for e in ids if e in by_id and e.startswith('GLY')]
        if direct:
            rects=[r['rect'] for r in direct]
            if row.get('glyph_audit_evidence'):rects=row['glyph_audit_evidence']['assessment']['rects']
            row.update(rects=rects,cell_ids=cells_for_rects(rects),location_unresolved=False,
                       location_evidence={'status':'VERIFIED_REGION','rects':rects,'method':'independent-glyph-region'})
            continue
        literal=(row.get('official_term_check') or {}).get('literal')
        if not literal:
            original_text=' '.join(objects[e].get('text','') for e in ids if e in objects)
            quotes=re.findall(r'[“「\"‘\']([^”」\"’\']{2,40})[”」\"’\']',row.get('reason',''))
            # Only explicitly observed source strings; never locate a proposed correction.
            quotes=[q for q in quotes if normalized(q) in normalized(row.get('observation','')) or normalized(q) in normalized(original_text)]
            if len(set(quotes))==1:literal=quotes[0]
        if not literal:continue
        needle=normalized(literal)
        matches=[r for r in regions if r['assessment']['transcription_confirmed'] and needle in normalized(r['assessment']['literal_text'])]
        precise=[r for r in matches if r.get('method')=='independent-detector-and-scene']
        if precise:matches=precise
        old={'rects':copy.deepcopy(row.get('rects',[])),'evidence_ids':list(ids)}
        if len(matches)==1:
            r=matches[0]
            rects=r.get('rects') or [r['rect']]
            row.update(rects=rects,cell_ids=cells_for_rects(rects),evidence_ids=[r['id']],location_unresolved=False,
                       location_evidence={'status':'VERIFIED_REGION','literal':literal,'rects':rects,
                           'method':r.get('method','unique-independent-literal'),'previous':old})
        elif len(matches)>1 or any(set(ids).intersection(r.get('source_ids',[])) and r['assessment']['transcription_confirmed'] for r in regions):
            # Keep the finding and its prior location for audit, but don't put it on unrelated text.
            row.update(rects=[],cell_ids=[],location_unresolved=True,
                       location_evidence={'status':'UNRESOLVED','literal':literal,'rects':[],
                           'reason':'같은 문구가 여러 곳에 있습니다.' if matches else '표시 후보에서 지적한 원문을 확인하지 못했습니다.',
                           'method':'independent-literal-check','previous':old})
    return rows
