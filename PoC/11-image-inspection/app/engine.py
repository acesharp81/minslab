import copy
import hashlib
import io
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import deque
from PIL import Image
from .config import ROOT
from .storage import now
from .rules import PACK, STEPS, placeholder, validate_batch, rollup, redact
from .providers import Provider
from .usage import Usage
from .imaging import labeled
from .observations import clean_inventory, legacy_inventory, Decisions, required_object_checks
from . import taegeukgi, rule_editor, verification, text_ocr, symbol_geometry, evidence_guards


def resized(raw):
    im=Image.open(io.BytesIO(raw));im.thumbnail((1536,1536));b=io.BytesIO();im.save(b,format='PNG');return b.getvalue()


def checklist_batches(ids,steps,max_rules=40):
    """Keep original questions intact; bound context without one call per rule."""
    by_parent={}
    for rid in ids:by_parent.setdefault(steps[rid]['parent_id'],[]).append(rid)
    batches=[];batch=[];parents=0
    for group in by_parent.values():
        if batch and (len(batch)+len(group)>max_rules or parents>=6):
            batches.append(batch);batch=[];parents=0
        batch.extend(group);parents+=1
    if batch:batches.append(batch)
    return batches


class Engine:
    def __init__(self,s,store):
        self.s,self.store=s,store;rule_editor.initialize(store);self.usage=Usage(s,store);self.provider=Provider(s,self.usage)
        self.pool=ThreadPoolExecutor(max_workers=1);self.lock=threading.RLock()
        # Interrupted jobs keep completed batches, unfinished steps are explicit errors.
        for job in store.jobs():
            if job.get('state') in ('QUEUED','RUNNING'):
                job['state']='INTERRUPTED'
                for r in job['runs'][-1]['results']:
                    if r['status']=='NOT_RUN':r.update(status='ERROR',reason='서버 재시작으로 중단됨 · 선택 재검사 가능')
                store.save(job)
    def submit(self,jid,options):
        with self.lock:
            job=self.store.get(jid)
            if job['state'] in ('QUEUED','RUNNING'):raise ValueError('이미 검사 중입니다.')
            if sum(x.get('state') in ('QUEUED','RUNNING') for x in self.store.jobs())>=4:raise ValueError('검사 대기열이 가득 찼습니다.')
            pack=rule_editor.current(self.store)['pack'];steps={r['rule_id']:r for r in pack['steps']}
            source=None
            if options.get('reuse_observation_run_id'):
                source=next((r for r in job['runs'] if r['id']==options['reuse_observation_run_id']),None)
                if not source:raise ValueError('재사용할 검사 버전이 없습니다.')
                if source['options']['mode']!='live' or source.get('scope')=='CROP':raise ValueError('전체 이미지의 실제 관찰 기록만 재사용할 수 있습니다.')
                observation=copy.deepcopy(source.get('observation')) or legacy_inventory(source)
                if not set(options.get('recheck_object_ids') or [])<={o['id'] for o in observation['objects']}:raise ValueError('재판독 대상이 저장된 관찰에 없습니다.')
            selected=options['rule_ids'] or list(steps)
            if any(x not in steps for x in selected):raise ValueError('알 수 없는 규칙')
            selected=list(dict.fromkeys(selected))
            if options.get('crop_id') and not options['rule_ids']:raise ValueError('확대 재검사는 점검할 규칙을 선택하십시오.')
            refs=[r for r in self.store.references() if r['status']=='APPROVED' and (not r.get('effective_to') or r['effective_to']>=now()[:10]) and (not r.get('effective_from') or r['effective_from']<=now()[:10])]
            cache_data={'image':job['image']['normalized_sha256'],'metadata':job['metadata'],'rules':selected,'pack':pack,
                        'refs':refs,'options':{k:v for k,v in options.items() if k not in ('force','consent')},
                        'effort':self.s.get('REASONING_EFFORT','low'),'detail':self.s.get('IMAGE_DETAIL','high'),'prompt_version':'original-checklist-v30-crop-origin','ocr_settings':{k:self.s.get(k) for k in ('OCR_ENABLED','OCR_MAX_REGIONS','OCR_VISION_MAX_REGIONS','VERIFICATION_REASONING_EFFORT','OCR_REASONING_EFFORT','OCR_HIGH_EFFORT_RECHECK','NAVER_OCR_ENABLED')}}
            cache_key=hashlib.sha256(json.dumps(cache_data,sort_keys=True).encode()).hexdigest()
            inherited=copy.deepcopy(job['runs'][-1]['results']) if job['runs'] else [placeholder(r) for r in steps]
            # Crops are supplementary: preserve the whole-image result and mark the scope.
            if not options.get('crop_id'):inherited=[r for r in inherited if r['rule_id'] not in selected]
            results=inherited+[placeholder(r) for r in selected]
            run={'id':uuid.uuid4().hex,'created_at':now(),'options':options,'selected':selected,'results':results,'reviews':[],
                 'reference_snapshot':refs,'rule_pack':copy.deepcopy(pack),'cache_key':cache_key,'calls':[],'analysis':[],
                 'progress':0,'total':len(selected),'reused_from':None,'elapsed_seconds':0,'scope':'CROP' if options.get('crop_id') else 'FULL_IMAGE'}
            if job['runs'] and not options.get('crop_id') and job['runs'][-1].get('structural_checks'):
                run['structural_checks']=copy.deepcopy(job['runs'][-1]['structural_checks'])
            if source:
                run['options']['text_sensitivity']=source['options'].get('text_sensitivity','standard')
                run['observation']=observation
                run['observation_reused_from']={'job_id':jid,'run_id':source['id']}
                run['observation_model']=source.get('observation_model',source['options']['vision_model'])
                run['verification']=copy.deepcopy(source.get('verification',{'results':[],'deferred':[],'reused_without_verification':True}))
                if source.get('text_ocr'):run['text_ocr']=copy.deepcopy(source['text_ocr'])
                # A previous comparison only applies to the exact approved reference snapshot.
                valid_hashes={r['id']:r.get('image_hash') for r in refs}
                action_hashes={r['rule_id']:hashlib.sha256(r['objective'].encode()).hexdigest() for r in pack['steps']}
                for result in run['verification'].get('results',[]):
                    result['comparisons']=[{**c,'rule_ids':[rid for rid in c['rule_ids'] if result.get('rule_hashes',{}).get(rid)==action_hashes.get(rid) and rid in action_hashes]} for c in result.get('comparisons',[]) if result.get('reference_hashes',{}).get(c['reference_id'])==valid_hashes.get(c['reference_id']) and c['reference_id'] in valid_hashes]
                    result['comparisons']=[c for c in result['comparisons'] if c['rule_ids']]
            if not options.get('force'):
                for old in self.store.jobs():
                    for prior in reversed(old.get('runs',[])):
                        if prior['cache_key']==cache_key and prior.get('finished_at') and not any(r['status'] in ('ERROR','NOT_RUN') for r in prior['results']):
                            run.update(results=copy.deepcopy(prior['results']),analysis=copy.deepcopy(prior['analysis']),observation=copy.deepcopy(prior.get('observation')),observation_model=prior.get('observation_model'),verification=copy.deepcopy(prior.get('verification',{})),analysis_observation=copy.deepcopy(prior.get('analysis_observation')),text_coverage=copy.deepcopy(prior.get('text_coverage')),text_ocr=copy.deepcopy(prior.get('text_ocr')),structural_checks=copy.deepcopy(prior.get('structural_checks')),progress=len(selected),finished_at=now(),reused_from={'job_id':old['id'],'run_id':prior['id']})
                            job['runs'].append(run);job['state']='COMPLETED';self.store.save(job);return job
            job['runs'].append(run);job['state']='QUEUED';self.store.save(job)
            self.pool.submit(self.execute,jid,run['id']);return job
    def checkpoint(self,jid,run):
        with self.lock:
            job=self.store.get(jid);job['runs'][-1]=copy.deepcopy(run);self.store.save(job)
    def execute(self,jid,run_id):
        started=time.monotonic();job=self.store.get(jid);run=job['runs'][-1];options=run['options']
        job['state']='RUNNING';self.store.save(job)
        grid=next((x for x in job['crops'] if x['id']==options.get('crop_id')),None)
        try:
            if options['mode']=='live':
                self.inspect(job,run,grid,started)
            else:
                found=self.mock(job,run['selected'],grid) if options['mode']=='mock' else [placeholder(r,'NOT_RUN','외부 전송 차단: 자동 검사는 실행하지 않았습니다.') for r in run['selected']]
                self.replace_results(run,run['selected'],found)
                run['progress']=run['total']
        except Exception as exc:
            if getattr(exc,'call_meta',None):run['calls'].append(exc.call_meta)
            reason=str(exc)[:400] if isinstance(exc,(ValueError,RuntimeError)) else '검사 처리 오류 · 저장된 관찰은 재분석에 사용할 수 있습니다.'
            failure_model=(getattr(exc,'call_meta',None) or {}).get('model') or options.get('vision_model' if run.get('phase') in ('READING','VERIFYING','TEXT_OCR') else 'analysis_model')
            run['failed_phase']=run.get('phase');run['stopped_reason']=reason
            run['analysis'].append({'error':reason,'model':failure_model,'phase':run.get('phase')})
            for r in run['results']:
                if r['rule_id'] in run['selected'] and r['status']=='NOT_RUN':r.update(status='ERROR',reason=reason)
        finally:
            run['finished_at']=now();run['elapsed_seconds']=round(time.monotonic()-started,2);run['phase']='DONE'
            for r in run['results']:r.setdefault('id',uuid.uuid4().hex)
            with self.lock:
                job=self.store.get(jid);job['runs'][-1]=run
                job['state']='COMPLETED_WITH_ERRORS' if any(x['status']=='ERROR' for x in run['results']) or any(x.get('error') for x in run['analysis']) else 'COMPLETED'
                self.store.save(job)

    def replace_results(self,run,ids,found):
        run['results']=[r for r in run['results'] if not (r['rule_id'] in ids and r.get('instance_id')=='unresolved' and r['status']=='NOT_RUN')]
        for r in found:r['id']=uuid.uuid4().hex
        run['results'].extend(found)

    def inspect(self,job,run,grid,started):
        options=run['options'];jid=job['id'];pack=run['rule_pack'];steps={r['rule_id']:r for r in pack['steps']}
        if not grid and any(r in run['selected'] for r in ('H-04-h','H-04-i')):
            run['phase']='STRUCTURE';self.checkpoint(jid,run)
            run['structural_checks']=taegeukgi.inspect((self.s.data/jid/'image.png').read_bytes())
            self.checkpoint(jid,run)
        if not run.get('observation'):
            run['phase']='READING';self.checkpoint(jid,run)
            raw=(self.s.data/jid/(grid['id']+'.png' if grid else 'image.png')).read_bytes()
            images=[resized(raw),labeled(raw,8 if grid else 12,8 if grid else 12)]
            payload={'metadata':job['metadata'],'text_quality_policy':{'sensitivity':options.get('text_sensitivity','strict'),'instruction':'문자 전사 성공과 획/외형 품질을 각각 검사. 읽을 수 있는 뭉개진 글자도 별도 기록.'},'grid':{'rows':8 if grid else 12,'cols':8 if grid else 12,'origin':'좌상단 R01C01; 가로 열, 세로 행; 이미지 전체를 균등 분할한 가상 격자'},
                     'scope':'첫 이미지는 확대 원본, 두 번째는 위치 참고용 8x8 격자' if grid else '첫 이미지는 전체 원본, 두 번째는 위치 참고용 12x12 격자',
                     'inspection_checklist':[{'id':p['id'],'title':p['title'],'original':p['original']} for p in pack['parents']], 'reviewer_guidance':pack.get('guidance','')}
            for attempt in range(2):
                try:
                    data,meta=self.provider.call(options['vision_model'],json.dumps(payload,ensure_ascii=False),images,workload='image-observation')
                    break
                except Exception as exc:
                    failed=getattr(exc,'call_meta',None)
                    if attempt or not failed or not failed.get('retryable'):raise
                    # Each HTTP attempt has its own shared-budget reservation and event.
                    # Never refund unknown usage or loop on provider errors.
                    run['calls'].append(failed)
                    run['reading_retry']={'attempt':2,'reason':str(exc)[:400]}
                    self.checkpoint(jid,run);time.sleep(2)
            run['calls'].append(meta);run['observation']=clean_inventory(data,grid);run['observation_model']=options['vision_model']
            run['observation_created_at']=now()
            run['elapsed_seconds']=round(time.monotonic()-started,2);self.checkpoint(jid,run)
        if not grid and not run.get('observation_reused_from') and self.s.flag('OCR_ENABLED',False):
            run['phase']='TEXT_OCR';self.checkpoint(jid,run)
            text_ocr.run_text_ocr(self,job,run,(self.s.data/jid/'image.png').read_bytes())
        if not grid and (not run.get('observation_reused_from') or options.get('recheck_object_ids')):
            run['phase']='VERIFYING';self.checkpoint(jid,run)
            verification.run_verification(self,job,run,(self.s.data/jid/'image.png').read_bytes())
        run['analysis_observation']=verification.effective_observation(run)
        run['text_coverage']=verification.coverage(run['analysis_observation'],run.get('verification',{}))
        if not grid:run['symbol_geometry']=symbol_geometry.inspect((self.s.data/jid/'image.png').read_bytes(),run['analysis_observation'],run['reference_snapshot'],self.s.data)
        if not grid:text_ocr.attach_observations(run)
        run['phase']='ANALYZING';self.checkpoint(jid,run)
        model=options.get('analysis_model') or options['vision_model']
        remaining=run['selected']
        batches=deque((ids,0) for ids in checklist_batches(remaining,steps,24 if len(run['analysis_observation']['objects'])>6 else 40))
        def request(ids):
            parent_ids={steps[r]['parent_id'] for r in ids}
            analysis_observation=text_ocr.analysis_observation(run,ids)
            prompt={'observation':analysis_observation,'text_ocr':text_ocr.compact_evidence(run) if parent_ids.intersection({'H-06','D-02'}) else None,'verification':run.get('verification',{}),'text_coverage':run.get('text_coverage',{}),'text_quality_policy':{'sensitivity':options.get('text_sensitivity','standard')},'original_checklist':[p for p in pack['parents'] if p['id'] in parent_ids],'structural_checks':run.get('structural_checks') if 'H-04' in parent_ids else None,'reviewer_guidance':pack.get('guidance',''), 'metadata':job['metadata'],
                    'rules':[{'rule_id':rid,'parent_id':steps[rid]['parent_id'],'action':steps[rid]['objective'],'required_references':steps[rid]['reference_requirements']} for rid in ids],
                    'approved_references':[{k:v for k,v in r.items() if k!='image_file'} for r in run['reference_snapshot'] if parent_ids.intersection(r['parent_ids'])]}
            prompt['required_object_checks']=required_object_checks(analysis_observation,prompt['rules'])
            return self.provider.call(model,json.dumps(prompt,ensure_ascii=False),workload='checklist-analysis')
        # Two concurrent text requests; each batch keeps whole parent questions intact.
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending={}
            def enqueue():
                while batches and len(pending)<2:
                    ids,depth=batches.popleft();pending[pool.submit(request,ids)]=(ids,depth)
            enqueue();enqueue();stopped=False
            while pending:
                done,_=wait(pending,return_when=FIRST_COMPLETED)
                for future in done:
                    ids,depth=pending.pop(future)
                    try:
                        data,meta=future.result();run['calls'].append(meta)
                        found=self.decisions(run,grid,model,ids,data)
                        self.replace_results(run,ids,found);run['progress']+=len(ids)
                    except Exception as exc:
                        if getattr(exc,'call_meta',None):run['calls'].append(exc.call_meta)
                        if getattr(exc,'output_truncated',False) and len(ids)>1 and depth<3:
                            midpoint=len(ids)//2
                            batches.appendleft((ids[midpoint:],depth+1));batches.appendleft((ids[:midpoint],depth+1))
                            run.setdefault('analysis_retries',[]).append({'reason':'출력 한도: 규칙 묶음을 절반으로 분할','rule_ids':ids,'depth':depth+1,'event_id':getattr(exc,'call_meta',{}).get('event_id')})
                            self.checkpoint(jid,run)
                            if not stopped:enqueue()
                            continue
                        reason=str(exc)[:400] if isinstance(exc,(ValueError,RuntimeError)) else '규칙 분석 처리 오류'
                        run['analysis'].append({'error':reason,'model':model});stopped=True
                        self.replace_results(run,ids,[placeholder(r,'ERROR',reason) for r in ids])
                    run['elapsed_seconds']=round(time.monotonic()-started,2);self.checkpoint(jid,run)
                    if not stopped:enqueue()
            if stopped:
                for r in run['results']:
                    if r['status']=='NOT_RUN' and r['rule_id'] in run['selected']:r.update(status='ERROR',reason='앞선 분석 오류로 후속 호출 중단 · 관찰 재사용 가능')

    def decisions(self,run,grid,model,ids,data):
        pack=run.get('rule_pack',PACK);steps={r['rule_id']:r for r in pack['steps']}
        groups=Decisions.model_validate(data).model_dump()['results']
        decisions=[]
        for group in groups:
            if not group['rule_ids']:continue
            # The provider requires one verdict per rule; reject mixed-present
            # results here too for alternate providers and imported responses.
            if group['target_presence']!='ABSENT' and len({steps[r]['parent_id'] for r in group['rule_ids'] if r in steps})>1:
                raise ValueError('서로 다른 원문 항목에 같은 분석 의견이 배정되었습니다.')
            decisions.extend({**{k:v for k,v in group.items() if k!='rule_ids'},'rule_id':rid} for rid in group['rule_ids'])
        returned=[r['rule_id'] for r in decisions]
        if not returned or not set(returned)<=set(ids):raise ValueError('분석 결과에 빈 응답 또는 알 수 없는 규칙이 있습니다. 관찰을 재사용해 재분석할 수 있습니다.')
        unique={}
        for d in decisions:
            if d['target_presence']=='ABSENT':d.update(status='NOT_APPLICABLE',evidence_ids=[],reference_ids=[])
            key=(d['rule_id'],tuple(sorted(set(d['evidence_ids']))))
            if key not in unique:unique[key]=d;continue
            old=unique[key]
            if old['status']!=d['status'] or old['target_presence']!=d['target_presence']:
                old.update(status='REVIEW',target_presence='UNCERTAIN',reason='같은 대상에 대한 모델 의견이 상충합니다: '+old['reason']+' / '+d['reason'],recommended_action='상충하는 관찰 근거를 직접 확인하세요.')
            elif old['reason']!=d['reason']:old['reason']=(old['reason']+' / '+d['reason'])[:1500]
            old['reference_ids']=list(dict.fromkeys(old['reference_ids']+d['reference_ids']))
        decisions=list(unique.values())
        objects={o['id']:o for o in run.get('analysis_observation',run['observation'])['objects']};rows=[]
        # A recorded identity conflict must not disappear because a batch only
        # assessed another landmark. Preserve it as an explicitly unadjudicated
        # observation, never fabricate an automatic FAIL or a model conclusion.
        import re
        contextual=[{'rule_id':rid,'action':steps[rid]['objective']} for rid in ids]
        for rid,targets in required_object_checks({'objects':list(objects.values())},contextual).items():
            covered={oid for d in decisions if d['rule_id']==rid for oid in d['evidence_ids']}
            for oid in targets:
                if oid in covered:continue
                obj=objects[oid]
                conflict=bool(re.search('충돌|오인 소지',steps[rid]['objective']))
                decisions.append(dict(rule_id=rid,target_presence='PRESENT',status='REVIEW',evidence_ids=[oid],reference_ids=[],
                    reason=('관찰에 기록된 맥락 충돌 우려가 규칙 분석에서 누락되어 확인이 필요합니다: '+(obj.get('first_visual_concerns') or obj.get('visual_concerns',''))) if conflict else '대상은 관찰됐지만 이 행동에 대한 모델 판정이 누락됐습니다. 정상·오류 모두 미확정입니다.',
                    recommended_action='누락된 대상에 대해 해당 행동을 다시 검사하세요.',error_type='FACT_OR_STYLE_ISSUE' if conflict else 'NONE',review_basis='CONTEXT_CONFLICT' if conflict else 'READING_LIMIT',coverage_fallback=True))
        for d in decisions:
            if d['target_presence']=='ABSENT':d.update(status='NOT_APPLICABLE',evidence_ids=[],reference_ids=[])
            elif d['target_presence']=='UNCERTAIN' and d['status'] in ('PASS','FAIL'):d['status']='REVIEW'
            if d['status']=='FAIL' and d.get('error_type')=='NONE' and d.get('review_basis')=='NONE':
                d.update(status='REVIEW',decision_conflict=True,
                    reason='모델 응답의 오류 판정과 결함 없음 표기가 상충합니다. 원래 설명: '+d['reason'],
                    review_basis='READING_LIMIT',recommended_action='같은 대상의 판정과 근거를 재확인하세요.')
            if any(e not in objects for e in d['evidence_ids']):raise ValueError('분석 모델이 저장된 관찰 이외의 객체를 사용했습니다.')
            evidence=[objects[e] for e in dict.fromkeys(d['evidence_ids'])]
            quality='CLEAR' if evidence and all(o['quality']=='CLEAR' for o in evidence) else 'UNCERTAIN' if evidence else 'DOCUMENT'
            scoped=verification.direct_comparisons(run,d['rule_id'],d['evidence_ids'],d['reference_ids']) if evidence else []
            # Quality belongs to the action being judged. An uncertain trigram
            # cannot erase a clear, independently compared colour reversal.
            if scoped and d['target_presence']=='PRESENT':
                if d['status']=='REVIEW' and steps[d['rule_id']]['review_policy']!='HUMAN_REQUIRED' and all(p['status']=='MISMATCH' for p in scoped):
                    d.update(status='FAIL',review_basis='OBSERVED_ANOMALY',reason='해당 행동의 공식 도안 직접 비교: '+' / '.join(p['evidence'] for p in scoped),recommended_action='확인된 도안 차이를 수정하고 제작 의도는 별도로 검토하세요.')
                expected='MATCH' if d['status']=='PASS' else 'MISMATCH' if d['status']=='FAIL' else None
                if expected and all(p['status']==expected for p in scoped):quality='CLEAR'
            row=dict(rule_id=d['rule_id'],instance_id='|'.join(o['id'] for o in evidence) or 'document',status=d['status'],
                observation=' / '.join(o['label']+': '+o['description'] for o in evidence)[:5000],reason=d['reason'],
                evidence_quality=quality,cell_ids=list(dict.fromkeys(c for o in evidence for c in o['cell_ids'])),
                reference_ids=[x for x in d['reference_ids'] if x in {ref['id'] for ref in run['reference_snapshot']}],recommended_action=d['recommended_action'])
            if len(row['reference_ids'])!=len(d['reference_ids']):
                row['status']='REVIEW';row['reason']+=' · 제공되지 않은 기준자료를 인용하여 근거 재확인 필요'
            if any(k in steps[d['rule_id']]['reference_requirements'] for k in ('official-symbols','official-map','official-emblems')) and row['status'] in ('PASS','FAIL'):
                proof=verification.direct_comparisons(run,d['rule_id'],d['evidence_ids'],d['reference_ids'])
                expected='MATCH' if row['status']=='PASS' else 'MISMATCH'
                if not proof or (expected=='MATCH' and any(p['status']!='MATCH' for p in proof)) or not any(p['status']==expected for p in proof):
                    row['status']='REVIEW';row['reason']+=' · 해당 객체·항목의 공식 도안 직접 비교 근거가 미확정입니다.'
            rows.append(row)
        found=validate_batch({'results':rows},ids,run['reference_snapshot'],grid,model,pack=pack)
        for result,d in zip(found,decisions):
            result['evidence_ids']=d['evidence_ids'];result['error_type']=d.get('error_type','NONE')
            result['review_basis']=d.get('review_basis','UNASSESSED')
            result['visual_issue']=result['status']=='FAIL' or result['status']=='REVIEW' and result['review_basis'] in ('OBSERVED_ANOMALY','CONTEXT_CONFLICT')
            if d.get('coverage_fallback'):result.update(model='system/observation-coverage',coverage_fallback=True)
            if d.get('decision_conflict'):result['decision_conflict']=True
            requirements=set(steps[result['rule_id']]['reference_requirements'])
            available={r['kind'] for r in run['reference_snapshot'] if r['id'] in result['reference_ids'] and result['parent_id'] in r['parent_ids']}
            proof=verification.direct_comparisons(run,result['rule_id'],d['evidence_ids'],result['reference_ids'])
            official=bool(requirements.intersection({'official-symbols','official-map','official-emblems'}))
            eligible={r['kind'] for r in run['reference_snapshot'] if result['parent_id'] in r['parent_ids'] and (not official or r.get('image_file'))}
            result['evidence_status']='NOT_REQUIRED' if not requirements or result['status']=='NOT_APPLICABLE' else 'VERIFIED' if requirements<=available and (not official or proof) and result['parent_id']!='D-03' else 'UNAVAILABLE' if official and requirements<=eligible else 'REQUIRED'
            result['direct_comparisons']=proof
            if not grid and d['evidence_ids'] and all(objects[e].get('rects') for e in d['evidence_ids']) and result['rects']:
                result['rects']=[rect for e in d['evidence_ids'] for rect in objects[e]['rects']]
            result['location_unresolved']=bool(d['evidence_ids']) and not result['rects']
            result['vision_model']=run['observation_model'];result['target_presence']=d['target_presence']
            # Document/approval checks do not create visual defect markers.
            result['document_review']=result['status']=='REVIEW' and (bool(steps[result['rule_id']]['reference_requirements']) and not result['reference_ids'] or result['evidence_quality']=='DOCUMENT' or steps[result['rule_id']]['review_policy']=='HUMAN_REQUIRED' and d['status']=='PASS')
        if not grid:found=evidence_guards.protect_glyphs(run,found,ids)
        found=verification.protect_transcription_conflicts(run,found,ids,model)
        if not grid:found=evidence_guards.protect(run,found,ids)
        return text_ocr.protect_rows(run,found,ids,model) if not grid else found

    def mock(self,job,ids,grid):
        # Only our own synthetic fixture has scripted observations; arbitrary uploads get REVIEW.
        demo=job.get('demo',False);out=[]
        for rid in ids:
            r=placeholder(rid,'REVIEW','데모: 실제 AI를 호출하지 않았습니다.');r.update(instance_id='demo-scene',observation='실제 이미지 판정이 아닌 기능 시연입니다.',evidence_quality='UNCERTAIN',model='mock-fixture')
            if demo and not grid:
                if rid=='D-02-e':
                    for instance,cells,state,obs in [('hand-left',['R07C03','R07C04'],'FAIL','합성 시연: 손가락 6개 도형'),('hand-right',['R07C08'],'REVIEW','합성 시연: 가려진 손 도형')]:
                        f={**r,'instance_id':instance,'status':state,'cell_ids':cells,'evidence_quality':'CLEAR' if state=='FAIL' else 'OCCLUDED','observation':obs}
                        from .imaging import cell_rect
                        f['rects']=[cell_rect(c) for c in cells];out.append(f)
                    continue
                if rid=='D-02-l':
                    from .imaging import cell_rect
                    r.update(status='PASS',cell_ids=['R02C03','R02C04'],rects=[cell_rect(c) for c in ['R02C03','R02C04']],observation='합성 시연: SAMPLE 문구 판독',evidence_quality='CLEAR')
                if rid=='H-04-i':
                    from .imaging import cell_rect
                    r.update(cell_ids=['R04C09'],rects=[cell_rect('R04C09')],reason='공식 태극기 도안이 등록·승인되지 않아 REVIEW')
            out.append(r)
        return out
